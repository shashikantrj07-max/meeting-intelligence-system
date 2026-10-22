from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.meeting_insights import router as meeting_insights_router

app = FastAPI(title="Meeting Intelligence System API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(meeting_insights_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}