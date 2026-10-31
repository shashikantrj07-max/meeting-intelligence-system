from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from app import worker
from app.main import create_app


def _wait_for_shutdown(stop_event: threading.Event) -> None:
    stop_event.wait()


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
