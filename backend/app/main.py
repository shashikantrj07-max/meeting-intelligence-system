from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.meeting_action_items import router as meeting_action_items_router
from app.routers.meeting_insights import router as meeting_insights_router

from app.routers.meeting_transcription import (
    router as meeting_transcription_router,
)

app = FastAPI(title="Meeting Intelligence System API")

allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
if settings.FRONTEND_ORIGIN:
    allowed_origins.append(settings.FRONTEND_ORIGIN)

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