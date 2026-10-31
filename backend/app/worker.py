from __future__ import annotations

import logging
import re
import threading
import time
from time import perf_counter
from typing import Any
from uuid import uuid4

from app.config import settings
from app.routers.meeting_transcription import (
    _generate_and_save_insights,
    _transcribe_and_save,
)
from app.services.processing_jobs import (
    LeaseLostError,
    ProcessingJobError,
    claim_next_processing_job,
    finish_processing_job_failure,
)
from app.services.supabase import create_worker_supabase_client

logger = logging.getLogger("app.processing_worker")

POLL_INTERVAL_SECONDS = 1
LEASE_SECONDS = 120
HEARTBEAT_INTERVAL_SECONDS = 30
CLAIM_RPC_NAME = "claim_next_meeting_processing_job"
CLAIM_RPC_PATH = f"/rest/v1/rpc/{CLAIM_RPC_NAME}"
_SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\b(authorization|api[-_ ]?key|service[-_ ]?role[-_ ]?key|"
    r"access[-_ ]?token|token|password|secret)\s*[:=]\s*"
    r"(?:bearer\s+)?[^\s,;]+"
)
_TRANSCRIPT_VALUE_PATTERN = re.compile(
    r"(?i)\btranscript(?:\s+content)?\s*[:=]\s*.*"
)
_JWT_PATTERN = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _sanitize_rpc_error_message(message: Any) -> str:
    if not isinstance(message, str) or not message:
        return "unavailable"

    safe_message = _SENSITIVE_VALUE_PATTERN.sub(r"\1=[REDACTED]", message)
    safe_message = _TRANSCRIPT_VALUE_PATTERN.sub("transcript=[REDACTED]", safe_message)
    safe_message = _JWT_PATTERN.sub("[REDACTED_TOKEN]", safe_message)
    safe_message = re.sub(r"[\r\n\t]+", " ", safe_message)
    return safe_message[:500]


def _log_claim_rpc_error_response(response: Any) -> None:
    """Log only safe error fields for the durable worker's claim RPC."""
    request = getattr(response, "request", None)
    url = getattr(request, "url", None)
    path = getattr(url, "path", None)
    if path != CLAIM_RPC_PATH:
        return

    status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int) or status_code < 400:
        return

    try:
        response.read()
        error_body = response.json()
    except Exception:
        error_body = {}
    if not isinstance(error_body, dict):
        error_body = {}

    code = error_body.get("code")
    code = str(code) if isinstance(code, (str, int)) else ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code):
        code = "unavailable"

    logger.error(
        "Supabase RPC failed: rpc=%s http_status=%d api_code=%s api_message=%s",
        CLAIM_RPC_NAME,
        status_code,
        code,
        _sanitize_rpc_error_message(error_body.get("message")),
    )


class _LeaseHeartbeat:
    def __init__(
        self,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
    ) -> None:
        self.job_id = job_id
        self.worker_id = worker_id
        self.lease_token = lease_token
        self.lost = threading.Event()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=f"processing-lease-{job_id[:8]}",
            daemon=True,
        )

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=HEARTBEAT_INTERVAL_SECONDS + 1)

    def _run(self) -> None:
        try:
            client = create_worker_supabase_client()
        except Exception as exc:
            self.lost.set()
            logger.error(
                "Unable to initialize processing lease heartbeat: "
                "job_id=%s error_type=%s",
                self.job_id,
                type(exc).__name__,
            )
            return

        while not self._stop.wait(HEARTBEAT_INTERVAL_SECONDS):
            try:
                result = (
                    client.schema("public")
                    .rpc(
                        "renew_meeting_processing_job_lease",
                        {
                            "p_job_id": self.job_id,
                            "p_worker_id": self.worker_id,
                            "p_lease_token": self.lease_token,
                            "p_lease_seconds": LEASE_SECONDS,
                        },
                    )
                    .execute()
                )
                if result.data is not True:
                    self.lost.set()
                    logger.warning(
                        "Processing lease lost: job_id=%s",
                        self.job_id,
                    )
                    return
            except Exception as exc:
                logger.warning(
                    "Processing lease renewal failed: job_id=%s error_type=%s",
                    self.job_id,
                    type(exc).__name__,
                )


def _job_identifier(job: dict[str, Any], key: str) -> str:
    value = job.get(key)
    if not isinstance(value, str) or not value:
        raise ProcessingJobError(
            "The queued processing job is invalid.",
            category="invalid_input",
            retryable=False,
        )
    return value


def _load_transcript(supabase: Any, meeting_id: str) -> str:
    load_started = perf_counter()
    result = (
        supabase.schema("public")
        .table("meeting_transcripts")
        .select("content")
        .eq("meeting_id", meeting_id)
        .maybe_single()
        .execute()
    )
    transcript = (result.data or {}).get("content")
    if not isinstance(transcript, str) or not transcript.strip():
        raise ProcessingJobError(
            "The meeting transcript is unavailable.",
            category="invalid_input",
            retryable=False,
        )
    logger.info(
        "Processing transcript loaded: elapsed_ms=%d characters=%d",
        int((perf_counter() - load_started) * 1000),
        len(transcript),
    )
    return transcript


def _load_storage_path(
    supabase: Any,
    *,
    meeting_id: str,
    file_id: str,
) -> str:
    result = (
        supabase.schema("public")
        .table("meeting_files")
        .select("storage_path")
        .eq("id", file_id)
        .eq("meeting_id", meeting_id)
        .maybe_single()
        .execute()
    )
    storage_path = (result.data or {}).get("storage_path")
    if not isinstance(storage_path, str) or not storage_path.strip():
        raise ProcessingJobError(
            "The meeting file is unavailable.",
            category="invalid_input",
            retryable=False,
        )
    path_parts = storage_path.split("/")
    if (
        len(path_parts) < 2
        or path_parts[0] != meeting_id
        or any(part in {"", ".", ".."} for part in path_parts)
        or "\\" in storage_path
    ):
        raise ProcessingJobError(
            "The meeting file path is invalid.",
            category="invalid_input",
            retryable=False,
        )
    return storage_path


def process_claimed_job(
    supabase: Any,
    job: dict[str, Any],
    worker_id: str,
) -> None:
    job_id = _job_identifier(job, "job_id")
    meeting_id = _job_identifier(job, "meeting_id")
    lease_token = _job_identifier(job, "lease_token")
    job_type = job.get("job_type")
    attempt_started_at = _job_identifier(job, "attempt_started_at")
    attempt_count = job.get("attempt_count")
    if not isinstance(attempt_count, int) or attempt_count < 1:
        raise ProcessingJobError(
            "The queued processing job is invalid.",
            category="invalid_input",
            retryable=False,
        )

    heartbeat = _LeaseHeartbeat(
        job_id=job_id,
        worker_id=worker_id,
        lease_token=lease_token,
    )
    heartbeat.start()
    job_started = perf_counter()
    try:
        if heartbeat.lost.is_set():
            raise LeaseLostError("Processing lease is no longer current.")

        if job_type == "transcribe":
            file_id = _job_identifier(job, "file_id")
            storage_path = _load_storage_path(
                supabase,
                meeting_id=meeting_id,
                file_id=file_id,
            )
            service_role_key = settings.SUPABASE_SERVICE_ROLE_KEY
            if not service_role_key:
                raise RuntimeError(
                    "SUPABASE_SERVICE_ROLE_KEY is required for processing."
                )
            _transcribe_and_save(
                supabase,
                meeting_id,
                storage_path,
                attempt_started_at,
                service_role_key,
                job_id=job_id,
                worker_id=worker_id,
                lease_token=lease_token,
            )
        elif job_type == "insights":
            transcript = _load_transcript(supabase, meeting_id)
            _generate_and_save_insights(
                supabase,
                meeting_id,
                transcript,
                attempt_started_at,
                job_id=job_id,
                worker_id=worker_id,
                lease_token=lease_token,
            )
        else:
            raise ProcessingJobError(
                "The queued processing job type is invalid.",
                category="invalid_input",
                retryable=False,
            )
    except LeaseLostError:
        logger.info("Skipping superseded processing job: job_id=%s", job_id)
    except Exception as exc:
        try:
            status = finish_processing_job_failure(
                supabase,
                job_id=job_id,
                worker_id=worker_id,
                lease_token=lease_token,
                attempt_count=attempt_count,
                error=exc,
            )
        except Exception as finish_error:
            logger.error(
                "Unable to record processing failure: job_id=%s error_type=%s",
                job_id,
                type(finish_error).__name__,
            )
            return

        logger.error(
            "Processing job failed: job_id=%s attempt=%s status=%s "
            "error_type=%s elapsed_ms=%d",
            job_id,
            attempt_count,
            status,
            type(exc).__name__,
            int((perf_counter() - job_started) * 1000),
        )
    finally:
        heartbeat.stop()
        logger.info(
            "Processing job execution finished: job_id=%s type=%s elapsed_ms=%d",
            job_id,
            job_type,
            int((perf_counter() - job_started) * 1000),
        )


def run_worker() -> None:
    supabase = create_worker_supabase_client()
    worker_id = str(uuid4())
    logger.info("Durable processing worker started: worker_id=%s", worker_id)

    while True:
        try:
            claim_started = perf_counter()
            job = claim_next_processing_job(
                supabase,
                worker_id,
                lease_seconds=LEASE_SECONDS,
                response_hook=_log_claim_rpc_error_response,
            )
            if job is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue
            logger.info(
                "Processing job claimed: job_id=%s type=%s attempt=%s "
                "claim_rpc_ms=%d",
                job.get("job_id"),
                job.get("job_type"),
                job.get("attempt_count"),
                int((perf_counter() - claim_started) * 1000),
            )
            process_claimed_job(supabase, job, worker_id)
        except KeyboardInterrupt:
            logger.info("Durable processing worker stopping.")
            return
        except Exception as exc:
            logger.error(
                "Processing worker iteration failed: error_type=%s",
                type(exc).__name__,
            )
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run_worker()
