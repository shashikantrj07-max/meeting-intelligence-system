from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.meeting_action_items import router as meeting_action_items_router
from app.routers.meeting_insights import router as meeting_insights_router

from app.routers.meeting_transcription import (
    router as meeting_transcription_router,
)
from app.worker import WorkerRunner, WorkerSupervisor, run_worker


def create_app(
    frontend_origin: str | None = None,
    *,
    worker_runner: WorkerRunner | None = None,
) -> FastAPI:
    runner = worker_runner or run_worker

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        supervisor = WorkerSupervisor(runner)
        app.state.worker_supervisor = supervisor
        started = supervisor.start()
        try:
            yield
        finally:
            if started:
                supervisor.stop()

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
