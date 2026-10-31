import logging
from contextlib import asynccontextmanager
from time import perf_counter
from typing import AsyncIterator

_IMPORT_STARTED_AT = perf_counter()
_startup_logger = logging.getLogger("app.startup")


def _load_application_dependencies():
    """Load runtime dependencies while measuring their import cost."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware

    from app.config import settings
    from app.routers.meeting_action_items import router as action_items_router
    from app.routers.meeting_insights import router as insights_router
    from app.routers.meeting_transcription import (
        router as transcription_router,
    )
    from app.worker import WorkerRunner, WorkerSupervisor, run_worker

    return (
        FastAPI,
        CORSMiddleware,
        settings,
        action_items_router,
        insights_router,
        transcription_router,
        WorkerRunner,
        WorkerSupervisor,
        run_worker,
    )


(
    FastAPI,
    CORSMiddleware,
    settings,
    meeting_action_items_router,
    meeting_insights_router,
    meeting_transcription_router,
    WorkerRunner,
    WorkerSupervisor,
    run_worker,
) = _load_application_dependencies()

_startup_logger.info(
    "Application imports complete: elapsed_ms=%d",
    int((perf_counter() - _IMPORT_STARTED_AT) * 1000),
)


def create_app(
    frontend_origin: str | None = None,
    *,
    worker_runner: WorkerRunner | None = None,
) -> FastAPI:
    runner = worker_runner or run_worker

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        lifespan_started_at = perf_counter()
        _startup_logger.info("FastAPI lifespan startup started")
        supervisor = WorkerSupervisor(runner)
        app.state.worker_supervisor = supervisor
        worker_start_started_at = perf_counter()
        started = supervisor.start()
        _startup_logger.info(
            "Worker supervisor start returned: started=%s elapsed_ms=%d",
            started,
            int((perf_counter() - worker_start_started_at) * 1000),
        )
        _startup_logger.info(
            "FastAPI lifespan startup complete; awaiting ASGI server socket bind: "
            "elapsed_ms=%d",
            int((perf_counter() - lifespan_started_at) * 1000),
        )
        try:
            yield
        finally:
            if started:
                shutdown_started_at = perf_counter()
                supervisor.stop()
                _startup_logger.info(
                    "FastAPI lifespan shutdown complete: elapsed_ms=%d",
                    int((perf_counter() - shutdown_started_at) * 1000),
                )

    app = FastAPI(title="Meeting Intelligence System API", lifespan=lifespan)
    allowed_origins = (
        [frontend_origin]
        if frontend_origin
        else ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "PATCH", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
    )

    app.include_router(meeting_insights_router)
    app.include_router(meeting_transcription_router)
    app.include_router(meeting_action_items_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app(settings.FRONTEND_ORIGIN)
