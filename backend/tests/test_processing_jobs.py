from __future__ import annotations

import threading
import unittest
import httpx
from types import SimpleNamespace
from unittest.mock import patch

from app.services.processing_jobs import (
    MAX_JOB_ATTEMPTS,
    RETRY_MAX_SECONDS,
    RETRYABLE_HTTP_STATUSES,
    ProcessingJobError,
    claim_next_processing_job,
    classify_processing_error,
    enqueue_meeting_processing_job,
    finish_processing_job_failure,
    retry_delay_seconds,
)
from app.worker import (
    _load_storage_path,
    _log_claim_rpc_error_response,
    process_claimed_job,
)


class _FakeRpc:
    def __init__(self, client: "_FakeSupabase", name: str, params: dict) -> None:
        self.client = client
        self.name = name
        self.params = params

    def execute(self) -> SimpleNamespace:
        self.client.calls.append((self.name, self.params))
        value = self.client.responses.get(self.name)
        if callable(value):
            value = value(self.params)
        return SimpleNamespace(data=value)


class _FakeSupabase:
    def __init__(self, responses: dict | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict]] = []

    def schema(self, _schema: str) -> "_FakeSupabase":
        return self

    def rpc(self, name: str, params: dict) -> _FakeRpc:
        return _FakeRpc(self, name, params)


class _ConcurrentQueue:
    def __init__(self, jobs: list[dict]) -> None:
        self.jobs = {job["job_id"]: {**job, "status": "pending"} for job in jobs}
        self.lock = threading.Lock()

    def claim(self, params: dict) -> list[dict]:
        with self.lock:
            for job in self.jobs.values():
                if job["status"] == "pending" or job.get("lease_expired"):
                    job["status"] = "running"
                    job["lease_expired"] = False
                    job["attempt_count"] = job.get("attempt_count", 0) + 1
                    job["lease_token"] = f"lease-{job['attempt_count']}"
                    job["lease_owner"] = params["p_worker_id"]
                    return [{key: value for key, value in job.items() if key != "lease_expired"}]
            return []

    def expire_lease(self, job_id: str) -> None:
        with self.lock:
            self.jobs[job_id]["lease_expired"] = True


class ProcessingJobPolicyTests(unittest.TestCase):
    def test_claim_sends_the_live_rpc_signature_arguments(self) -> None:
        worker_id = "00000000-0000-4000-8000-000000000001"
        client = _FakeSupabase(
            {
                "claim_next_meeting_processing_job": [
                    {"job_id": "job-1", "meeting_id": "meeting-1"}
                ]
            }
        )

        result = claim_next_processing_job(
            client,
            worker_id,
            lease_seconds=120,
        )

        self.assertEqual(result["job_id"], "job-1")
        name, params = client.calls[0]
        self.assertEqual(name, "claim_next_meeting_processing_job")
        self.assertEqual(
            params,
            {
                "p_worker_id": worker_id,
                "p_lease_seconds": 120,
            },
        )
        self.assertIsInstance(params["p_worker_id"], str)
        self.assertIs(type(params["p_lease_seconds"]), int)

    def test_worker_rejects_storage_paths_outside_the_meeting_prefix(self) -> None:
        class _StorageQuery:
            def __init__(self, path: str) -> None:
                self.path = path

            def select(self, _columns: str) -> "_StorageQuery":
                return self

            def eq(self, _column: str, _value: str) -> "_StorageQuery":
                return self

            def maybe_single(self) -> "_StorageQuery":
                return self

            def execute(self) -> SimpleNamespace:
                return SimpleNamespace(data={"storage_path": self.path})

        class _StorageSupabase:
            def __init__(self, path: str) -> None:
                self.query = _StorageQuery(path)

            def schema(self, _schema: str) -> "_StorageSupabase":
                return self

            def table(self, _table: str) -> _StorageQuery:
                return self.query

        self.assertEqual(
            _load_storage_path(
                _StorageSupabase("meeting-1/recording.wav"),
                meeting_id="meeting-1",
                file_id="file-1",
            ),
            "meeting-1/recording.wav",
        )
        for invalid_path in (
            "another-meeting/recording.wav",
            "meeting-1/../another-meeting/recording.wav",
            "meeting-1\\recording.wav",
        ):
            with self.subTest(path=invalid_path):
                with self.assertRaises(ProcessingJobError):
                    _load_storage_path(
                        _StorageSupabase(invalid_path),
                        meeting_id="meeting-1",
                        file_id="file-1",
                    )

    def test_enqueue_returns_persisted_job_identity(self) -> None:
        client = _FakeSupabase(
            {
                "enqueue_meeting_processing_job": [
                    {"job_id": "job-1", "job_status": "pending"}
                ]
            }
        )

        result = enqueue_meeting_processing_job(
            client,
            meeting_id="meeting-1",
            job_type="transcribe",
            idempotency_key="idempotency-1",
            file_id="file-1",
        )

        self.assertEqual(result, {"job_id": "job-1", "status": "pending"})
        self.assertEqual(
            client.calls[0],
            (
                "enqueue_meeting_processing_job",
                {
                    "p_meeting_id": "meeting-1",
                    "p_job_type": "transcribe",
                    "p_file_id": "file-1",
                    "p_idempotency_key": "idempotency-1",
                },
            ),
        )

    def test_invalid_enqueue_response_is_not_reported_as_success(self) -> None:
        client = _FakeSupabase({"enqueue_meeting_processing_job": []})
        with self.assertRaises(RuntimeError):
            enqueue_meeting_processing_job(
                client,
                meeting_id="meeting-1",
                job_type="insights",
                idempotency_key="idempotency-1",
            )

    def test_worker_restart_recovers_an_expired_claimed_job(self) -> None:
        queue = _ConcurrentQueue(
            [
                {
                    "job_id": "job-after-restart",
                    "meeting_id": "meeting-1",
                    "job_type": "insights",
                }
            ]
        )
        previous_worker_client = _FakeSupabase(
            {"claim_next_meeting_processing_job": queue.claim}
        )
        first_claim = claim_next_processing_job(
            previous_worker_client,
            "worker-before-restart",
        )
        queue.expire_lease("job-after-restart")
        restarted_worker_client = _FakeSupabase(
            {"claim_next_meeting_processing_job": queue.claim}
        )
        restarted_worker_claim = claim_next_processing_job(
            restarted_worker_client,
            "worker-after-restart",
        )

        self.assertEqual(
            restarted_worker_claim["job_id"],
            "job-after-restart",
        )
        self.assertEqual(restarted_worker_claim["attempt_count"], 2)
        self.assertNotEqual(
            restarted_worker_claim["lease_token"],
            first_claim["lease_token"],
        )

    def test_concurrent_claim_clients_do_not_receive_the_same_fake_job(self) -> None:
        queue = _ConcurrentQueue(
            [{"job_id": "only-job"}]
        )
        clients = [
            _FakeSupabase(
                {"claim_next_meeting_processing_job": queue.claim}
            )
            for _ in range(8)
        ]
        claimed: list[dict] = []
        result_lock = threading.Lock()

        def claim(index: int) -> None:
            result = claim_next_processing_job(clients[index], f"worker-{index}")
            if result is not None:
                with result_lock:
                    claimed.append(result)

        threads = [
            threading.Thread(target=claim, args=(index,))
            for index in range(len(clients))
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual([job["job_id"] for job in claimed], ["only-job"])

    def test_retry_policy_is_bounded_and_includes_jitter(self) -> None:
        self.assertEqual(MAX_JOB_ATTEMPTS, 3)
        self.assertEqual(retry_delay_seconds(1, random_value=0), 30)
        self.assertEqual(retry_delay_seconds(1, random_value=1), 36)
        self.assertEqual(
            retry_delay_seconds(100, random_value=1),
            RETRY_MAX_SECONDS,
        )
        with self.assertRaises(ValueError):
            retry_delay_seconds(0)

    def test_only_transient_http_statuses_are_retryable(self) -> None:
        for status in RETRYABLE_HTTP_STATUSES:
            with self.subTest(status=status):
                self.assertEqual(
                    classify_processing_error(
                        SimpleNamespace(status_code=status)
                    ),
                    (True, "provider_unavailable"),
                )
        self.assertEqual(
            classify_processing_error(SimpleNamespace(status_code=401)),
            (False, "authorization_failed"),
        )
        self.assertEqual(
            classify_processing_error(SimpleNamespace(status_code=415)),
            (False, "invalid_input"),
        )
        self.assertEqual(
            classify_processing_error(RuntimeError("internal detail")),
            (False, "processing_failed"),
        )

    def test_failure_rpc_receives_retry_schedule_not_exception_text(self) -> None:
        client = _FakeSupabase({"fail_meeting_processing_job": "retrying"})
        with patch(
            "app.services.processing_jobs.random.random",
            return_value=0,
        ):
            result = finish_processing_job_failure(
                client,
                job_id="job-1",
                worker_id="worker-1",
                lease_token="lease-1",
                attempt_count=1,
                error=ProcessingJobError(
                    "private provider detail",
                    category="provider_unavailable",
                    retryable=True,
                ),
            )

        self.assertEqual(result, "retrying")
        name, params = client.calls[0]
        self.assertEqual(name, "fail_meeting_processing_job")
        self.assertEqual(params["p_error_category"], "provider_unavailable")
        self.assertEqual(params["p_retry_delay_seconds"], 30)
        self.assertNotIn("private provider detail", str(params))


class ProcessingWorkerTests(unittest.TestCase):
    def _job(self, job_type: str = "insights") -> dict:
        return {
            "job_id": "job-1",
            "meeting_id": "meeting-1",
            "job_type": job_type,
            "file_id": "file-1" if job_type == "transcribe" else None,
            "attempt_count": 1,
            "max_attempts": 3,
            "lease_token": "lease-1",
            "attempt_started_at": "2026-10-30T00:00:00+00:00",
        }

    def test_claim_rpc_error_log_is_structured_and_redacts_sensitive_values(self) -> None:
        sensitive_values = (
            "worker-secret-value",
            "api-key-value",
            "private transcript phrase",
        )
        response = httpx.Response(
            400,
            request=httpx.Request(
                "POST",
                "https://supabase.invalid/rest/v1/rpc/claim_next_meeting_processing_job",
            ),
            json={
                "code": "PGRST202",
                "message": (
                    "Authorization: Bearer worker-secret-value; "
                    "api_key=api-key-value; "
                    "Transcript: private transcript phrase"
                ),
            },
        )

        with self.assertLogs("app.processing_worker", level="ERROR") as logs:
            _log_claim_rpc_error_response(response)

        output = "\n".join(logs.output)
        self.assertIn("rpc=claim_next_meeting_processing_job", output)
        self.assertIn("http_status=400", output)
        self.assertIn("api_code=PGRST202", output)
        for sensitive_value in sensitive_values:
            self.assertNotIn(sensitive_value, output)

    def test_claim_rpc_error_hook_ignores_other_rpc_paths(self) -> None:
        response = httpx.Response(
            400,
            request=httpx.Request(
                "POST", "https://supabase.invalid/rest/v1/rpc/other_function"
            ),
            json={"code": "PGRST202", "message": "private message"},
        )

        with self.assertNoLogs("app.processing_worker", level="ERROR"):
            _log_claim_rpc_error_response(response)

    def test_insight_job_runs_from_persisted_transcript(self) -> None:
        client = _FakeSupabase()
        with (
            patch("app.worker._LeaseHeartbeat") as heartbeat,
            patch("app.worker._load_transcript", return_value="stored transcript"),
            patch("app.worker._generate_and_save_insights") as generate,
        ):
            heartbeat.return_value.lost.is_set.return_value = False

            process_claimed_job(client, self._job(), "worker-1")

        generate.assert_called_once_with(
            client,
            "meeting-1",
            "stored transcript",
            "2026-10-30T00:00:00+00:00",
            job_id="job-1",
            worker_id="worker-1",
            lease_token="lease-1",
        )
        heartbeat.return_value.stop.assert_called_once()

    def test_permanent_failure_is_persisted_without_sensitive_error_text(self) -> None:
        client = _FakeSupabase({"fail_meeting_processing_job": "failed"})
        with (
            patch("app.worker._LeaseHeartbeat") as heartbeat,
            patch(
                "app.worker._load_transcript",
                side_effect=ProcessingJobError(
                    "private transcript detail",
                    category="invalid_input",
                    retryable=False,
                ),
            ),
            self.assertLogs("app.processing_worker", level="ERROR") as logs,
        ):
            heartbeat.return_value.lost.is_set.return_value = False
            process_claimed_job(client, self._job(), "worker-1")

        self.assertEqual(
            client.calls[0][1]["p_retryable"],
            False,
        )
        self.assertEqual(
            client.calls[0][1]["p_error_category"],
            "invalid_input",
        )
        self.assertNotIn("private transcript detail", "\n".join(logs.output))

    def test_lost_lease_does_not_schedule_a_failure_or_retry(self) -> None:
        client = _FakeSupabase()
        with patch("app.worker._LeaseHeartbeat") as heartbeat:
            heartbeat.return_value.lost.is_set.return_value = True
            process_claimed_job(client, self._job(), "worker-1")

        self.assertEqual(client.calls, [])
        heartbeat.return_value.stop.assert_called_once()


if __name__ == "__main__":
    unittest.main()
