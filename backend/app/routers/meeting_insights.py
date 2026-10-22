import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.schemas.meeting_insights import MeetingInsights
from app.services.ai.gemini import GeminiMeetingInsightsProvider
from app.services.supabase import create_request_supabase_client

router = APIRouter(prefix="/api/meetings", tags=["meeting insights"])
logger = logging.getLogger(__name__)


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        raise HTTPException(
            status_code=401,
            detail="A valid bearer access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(
            status_code=401,
            detail="A valid bearer access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return parts[1]


def _server_error(message: str, stage: str, error: Exception) -> HTTPException:
    logger.error("%s failed (%s).", stage, type(error).__name__)
    return HTTPException(status_code=500, detail=message)


def _upsert_processing_state(
    supabase: Any,
    meeting_id: str,
    stage: str,
    *,
    started_at: str | None = None,
    completed_at: str | None = None,
    error_message: str | None = None,
) -> None:
    supabase.schema("public").table("meeting_processing").upsert(
        {
            "meeting_id": meeting_id,
            "stage": stage,
            "started_at": started_at,
            "completed_at": completed_at,
            "error_message": error_message,
        },
        on_conflict="meeting_id",
    ).execute()


def _mark_processing_failed(
    supabase: Any,
    meeting_id: str,
    started_at: str,
    error_message: str,
) -> None:
    try:
        _upsert_processing_state(
            supabase,
            meeting_id,
            "failed",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_message=error_message,
        )
    except Exception as exc:
        logger.error(
            "Unable to record failed processing state (%s).",
            type(exc).__name__,
        )


def _generate_and_save_insights(
    supabase: Any,
    meeting_id: str,
    transcript_text: str,
    started_at: str,
) -> None:
    try:
        insights: MeetingInsights = GeminiMeetingInsightsProvider().generate(
            transcript_text
        )
    except Exception as exc:
        logger.error("Gemini insights generation failed (%s).", type(exc).__name__)
        _mark_processing_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting intelligence generation failed.",
        )
        return

    insight_data = insights.model_dump(mode="json")
    payload = {
        "meeting_id": meeting_id,
        "summary": insight_data["summary"],
        "key_decisions": insight_data["key_decisions"],
        "action_items": insight_data["action_items"],
        "risks_blockers": insight_data["risks_blockers"],
    }

    try:
        saved_result = (
            supabase.schema("public")
            .table("meeting_insights")
            .upsert(payload, on_conflict="meeting_id")
            .select(
                "id, meeting_id, summary, key_decisions, action_items, "
                "risks_blockers, created_at, updated_at"
            )
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error("Meeting insights save failed (%s).", type(exc).__name__)
        _mark_processing_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting intelligence could not be saved.",
        )
        return

    if saved_result.data is None:
        logger.error("Meeting insights save returned no data.")
        _mark_processing_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting intelligence could not be saved.",
        )
        return

    try:
        _upsert_processing_state(
            supabase,
            meeting_id,
            "completed",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        logger.error(
            "Unable to record completed processing state (%s).",
            type(exc).__name__,
        )
        _mark_processing_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting processing could not be completed.",
        )


@router.post("/{meeting_id}/insights", status_code=202)
def generate_meeting_insights(
    meeting_id: UUID,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    access_token = _bearer_token(authorization)

    try:
        supabase = create_request_supabase_client(access_token)
        verified_user = supabase.auth.get_user(access_token).user
    except Exception as exc:
        if getattr(exc, "status", None) in (400, 401, 403):
            raise HTTPException(
                status_code=401,
                detail="The bearer access token is invalid or expired.",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc
        raise _server_error(
            "Unable to verify the access token.",
            "Supabase token verification",
            exc,
        ) from exc

    if verified_user is None or not verified_user.id:
        raise HTTPException(
            status_code=401,
            detail="The bearer access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    authenticated_user_id = str(verified_user.id)
    if not authenticated_user_id:
        raise HTTPException(status_code=401, detail="The access token is invalid.")

    meeting_id_value = str(meeting_id)
    try:
        meeting_result = (
            supabase.schema("public")
            .table("meetings")
            .select("id")
            .eq("id", meeting_id_value)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        raise _server_error(
            "Unable to check meeting access.",
            "Meeting lookup",
            exc,
        ) from exc

    if meeting_result.data is None:
        raise HTTPException(
            status_code=404,
            detail="Meeting not found or inaccessible.",
        )

    try:
        transcript_result = (
            supabase.schema("public")
            .table("meeting_transcripts")
            .select("content")
            .eq("meeting_id", meeting_id_value)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        raise _server_error(
            "Unable to load the meeting transcript.",
            "Transcript lookup",
            exc,
        ) from exc

    if transcript_result.data is None:
        raise HTTPException(
            status_code=404,
            detail="No transcript found for this meeting.",
        )

    transcript_text = transcript_result.data.get("content")
    if not isinstance(transcript_text, str) or not transcript_text.strip():
        raise HTTPException(
            status_code=500,
            detail="The meeting transcript could not be processed.",
        )

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        _upsert_processing_state(
            supabase,
            meeting_id_value,
            "analyzing",
            started_at=started_at,
        )
    except Exception as exc:
        raise _server_error(
            "Unable to start meeting intelligence processing.",
            "Processing state update",
            exc,
        ) from exc

    background_tasks.add_task(
        _generate_and_save_insights,
        supabase,
        meeting_id_value,
        transcript_text,
        started_at,
    )
    return {"meeting_id": meeting_id_value, "stage": "analyzing"}
