from __future__ import annotations

import logging
import threading

from fastapi.testclient import TestClient

from app import worker
from app.main import create_app
from app.services import supabase as supabase_service


def _wait_for_shutdown(stop_event: threading.Event) -> None:
    stop_event.wait()


class _EventLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.logged = threading.Event()
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())
        self.logged.set()


def _capture_worker_startup_log() -> list[str]:
    handler = _EventLogHandler()
    previous_level = worker.logger.level
    worker.logger.setLevel(logging.ERROR)
    worker.logger.addHandler(handler)
    supervisor = worker.WorkerSupervisor(
        worker.run_worker,
        initial_restart_delay=30,
        max_restart_delay=30,
        shutdown_timeout=1,
    )
    try:
        assert supervisor.start()
        assert handler.logged.wait(timeout=1)
        assert supervisor.stop()
        return handler.messages
    finally:
        supervisor.stop()
        worker.logger.removeHandler(handler)
        worker.logger.setLevel(previous_level)


def test_lifespan_starts_and_stops_worker_and_health_stays_responsive() -> None:
    started = threading.Event()
    stopped = threading.Event()

    def runner(stop_event: threading.Event) -> None:
        started.set()
        stop_event.wait()
        stopped.set()

    app = create_app(worker_runner=runner)
    with TestClient(app) as client:
        assert started.wait(timeout=1)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    assert stopped.wait(timeout=1)


def test_supervisor_restarts_unexpected_exit_with_bounded_backoff_and_one_runner() -> None:
    lock = threading.Lock()
    calls = 0
    active = 0
    max_active = 0
    third_start = threading.Event()

    def runner(stop_event: threading.Event) -> None:
        nonlocal calls, active, max_active
        with lock:
            calls += 1
            call_number = calls
            active += 1
            max_active = max(max_active, active)
        try:
            if call_number < 3:
                raise RuntimeError("expected test failure")
            third_start.set()
            stop_event.wait()
        finally:
            with lock:
                active -= 1

    supervisor = worker.WorkerSupervisor(
        runner,
        initial_restart_delay=0.01,
        max_restart_delay=0.02,
        shutdown_timeout=1,
    )
    supervisor.start()
    supervisor.start()
    assert third_start.wait(timeout=1)
    assert supervisor.stop()

    assert calls == 3
    assert max_active == 1


def test_distinct_supervisors_cannot_start_two_workers_in_one_process() -> None:
    first_started = threading.Event()
    second_started = threading.Event()

    def first_runner(stop_event: threading.Event) -> None:
        first_started.set()
        stop_event.wait()

    def second_runner(stop_event: threading.Event) -> None:
        second_started.set()
        stop_event.wait()

    first = worker.WorkerSupervisor(first_runner, shutdown_timeout=1)
    second = worker.WorkerSupervisor(second_runner, shutdown_timeout=1)
    assert first.start()
    assert first_started.wait(timeout=1)
    assert not second.start()

    assert first.stop()
    assert not second_started.is_set()


def test_shutdown_during_claimed_job_finishes_job_without_claiming_another(
    monkeypatch,
) -> None:
    claimed = threading.Event()
    processing = threading.Event()
    finish_processing = threading.Event()
    stop_event = threading.Event()
    claim_count = 0

    class FakeSupabase:
        pass

    def claim(*_args, **_kwargs):
        nonlocal claim_count
        claim_count += 1
        claimed.set()
        return {
            "job_id": "job-1",
            "job_type": "insights",
            "attempt_count": 1,
        }

    def process(*_args, **_kwargs):
        processing.set()
        finish_processing.wait(timeout=1)

    monkeypatch.setattr(worker, "create_worker_supabase_client", FakeSupabase)
    monkeypatch.setattr(worker, "claim_next_processing_job", claim)
    monkeypatch.setattr(worker, "process_claimed_job", process)

    worker_thread = threading.Thread(
        target=worker.run_worker,
        args=(stop_event,),
        daemon=True,
    )
    worker_thread.start()
    assert claimed.wait(timeout=1)
    assert processing.wait(timeout=1)

    stop_event.set()
    finish_processing.set()
    worker_thread.join(timeout=1)

    assert not worker_thread.is_alive()
    assert claim_count == 1


def test_stop_before_worker_loop_prevents_new_job_claim(monkeypatch) -> None:
    stop_event = threading.Event()
    stop_event.set()
    claim_count = 0

    class FakeSupabase:
        pass

    def claim(*_args, **_kwargs):
        nonlocal claim_count
        claim_count += 1
        return None

    monkeypatch.setattr(worker, "create_worker_supabase_client", FakeSupabase)
    monkeypatch.setattr(worker, "claim_next_processing_job", claim)

    worker.run_worker(stop_event)

    assert claim_count == 0


def test_missing_service_role_is_reported_as_safe_initialization_category(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        supabase_service.settings,
        "SUPABASE_URL",
        "https://example.supabase.co",
    )
    monkeypatch.setattr(
        supabase_service.settings,
        "SUPABASE_SERVICE_ROLE_KEY",
        " ",
    )

    def unexpected_create_client(*_args, **_kwargs):
        raise AssertionError("client construction must not run")

    monkeypatch.setattr(
        supabase_service,
        "create_client",
        unexpected_create_client,
    )

    messages = _capture_worker_startup_log()

    assert any(
        "failure_category=missing_service_role_configuration" in message
        for message in messages
    )


def test_missing_supabase_url_is_reported_as_safe_initialization_category(
    monkeypatch,
) -> None:
    monkeypatch.setattr(supabase_service.settings, "SUPABASE_URL", " ")
    monkeypatch.setattr(
        supabase_service.settings,
        "SUPABASE_SERVICE_ROLE_KEY",
        "test-service-role-secret",
    )

    def unexpected_create_client(*_args, **_kwargs):
        raise AssertionError("client construction must not run")

    monkeypatch.setattr(
        supabase_service,
        "create_client",
        unexpected_create_client,
    )

    messages = _capture_worker_startup_log()

    assert any(
        "failure_category=missing_supabase_url" in message
        for message in messages
    )
    assert "test-service-role-secret" not in "\n".join(messages)


def test_client_construction_failure_logs_category_without_exception_message(
    monkeypatch,
) -> None:
    test_secret = "test-client-secret-must-not-appear"
    monkeypatch.setattr(
        supabase_service.settings,
        "SUPABASE_URL",
        "https://example.supabase.co",
    )
    monkeypatch.setattr(
        supabase_service.settings,
        "SUPABASE_SERVICE_ROLE_KEY",
        "test-service-role-secret",
    )

    def fail_create_client(*_args, **_kwargs):
        raise RuntimeError(f"construction failed with {test_secret}")

    monkeypatch.setattr(
        supabase_service,
        "create_client",
        fail_create_client,
    )

    messages = _capture_worker_startup_log()
    output = "\n".join(messages)

    assert "failure_category=supabase_client_construction_failure" in output
    assert "cause_type=RuntimeError" in output
    assert test_secret not in output
    assert "test-service-role-secret" not in output


def test_other_worker_initialization_failure_logs_category_without_message(
    monkeypatch,
) -> None:
    test_secret = "test-worker-secret-must-not-appear"

    def fail_initialization():
        raise RuntimeError(f"startup failed with {test_secret}")

    monkeypatch.setattr(
        worker,
        "create_worker_supabase_client",
        fail_initialization,
    )

    messages = _capture_worker_startup_log()
    output = "\n".join(messages)

    assert "failure_category=worker_initialization_failure" in output
    assert "cause_type=RuntimeError" in output
    assert test_secret not in output
