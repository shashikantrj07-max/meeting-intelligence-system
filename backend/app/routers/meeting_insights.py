import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.schemas.meeting_insights import MeetingInsights
from app.services.ai.gemini import GeminiMeetingInsightsProvider
from app.services.meeting_action_items import sync_generated_action_items
from app.services.supabase import create_request_supabase_client

router = APIRouter(prefix="/api/meetings", tags=["meeting insights"])
logger = logging.getLogger(__name__)
PROCESSING_STALE_AFTER = timedelta(minutes=5)


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


def _claim_processing(
    supabase: Any,
    meeting_id: str,
    started_at: str,
    stale_before: str,
) -> bool:
    table = supabase.schema("public").table("meeting_processing")
    update_values = {
        "stage": "analyzing",
        "started_at": started_at,
        "completed_at": None,
        "error_message": None,
    }

    reclaimed = (
        table.update(update_values)
        .eq("meeting_id", meeting_id)
        .in_("stage", ["failed", "completed"])
        .select("meeting_id")
        .execute()
    )
    if reclaimed.data:
        return True

    stale_reclaimed = (
        table.update(update_values)
        .eq("meeting_id", meeting_id)
        .eq("stage", "analyzing")
        .lt("started_at", stale_before)
        .select("meeting_id")
        .execute()
    )
    if stale_reclaimed.data:
        return True

    try:
        inserted = (
            table.insert(
                {
                    "meeting_id": meeting_id,
                    **update_values,
                }
            )
            .select("meeting_id")
            .execute()
        )
    except Exception as exc:
        if getattr(exc, "code", None) == "23505":
            return False
        raise

    return bool(inserted.data)


def _update_processing_attempt(
    supabase: Any,
    meeting_id: str,
    started_at: str,
    stage: str,
    *,
    completed_at: str,
    error_message: str | None = None,
) -> bool:
    result = (
        supabase.schema("public")
        .table("meeting_processing")
        .update(
            {
                "stage": stage,
                "completed_at": completed_at,
                "error_message": error_message,
            }
        )
        .eq("meeting_id", meeting_id)
        .eq("stage", "analyzing")
        .eq("started_at", started_at)
        .select("meeting_id")
        .execute()
    )
    return bool(result.data)


def _is_current_processing_attempt(
    supabase: Any,
    meeting_id: str,
    started_at: str,
) -> bool:
    result = (
        supabase.schema("public")
        .table("meeting_processing")
        .select("meeting_id")
        .eq("meeting_id", meeting_id)
        .eq("stage", "analyzing")
        .eq("started_at", started_at)
        .maybe_single()
        .execute()
    )
    return result.data is not None


def _mark_processing_failed(
    supabase: Any,
    meeting_id: str,
    started_at: str,
    error_message: str,
) -> None:
    try:
        updated = _update_processing_attempt(
            supabase,
            meeting_id,
            started_at,
            "failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_message=error_message,
        )
        if not updated:
            logger.info("Skipping failure update for a superseded processing attempt.")
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
        "discussion_points": insight_data["discussion_points"],
        "open_questions": insight_data["open_questions"],
        "next_steps": insight_data["next_steps"],
        "risks_blockers": insight_data["risks_blockers"],
    }

    try:
        if not _is_current_processing_attempt(supabase, meeting_id, started_at):
            logger.info("Skipping save for a superseded processing attempt.")
            return

        saved_result = (
            supabase.schema("public")
            .table("meeting_insights")
            .upsert(payload, on_conflict="meeting_id")
            .select(
                "id, meeting_id, summary, key_decisions, action_items, "
                "discussion_points, open_questions, next_steps, "
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
        sync_generated_action_items(
            supabase,
            meeting_id,
            insights.action_items,
        )
    except Exception as exc:
        logger.error("Meeting action-item sync failed (%s).", type(exc).__name__)
        _mark_processing_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting action items could not be synchronized.",
        )
        return

    try:
        completed = _update_processing_attempt(
            supabase,
            meeting_id,
            started_at,
            "completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
        if not completed:
            logger.info("Skipping completion update for a superseded processing attempt.")
    except Exception as exc:
        logger.error(
            "Unable to record completed processing state (%s).",
            type(exc).__name__,
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

    started_at_datetime = datetime.now(timezone.utc)
    started_at = started_at_datetime.isoformat()
    stale_before = (started_at_datetime - PROCESSING_STALE_AFTER).isoformat()
    try:
        claimed = _claim_processing(
            supabase,
            meeting_id_value,
            started_at,
            stale_before,
        )
    except Exception as exc:
        raise _server_error(
            "Unable to start meeting intelligence processing.",
            "Processing state update",
            exc,
        ) from exc

    if not claimed:
        raise HTTPException(
            status_code=409,
            detail="Meeting intelligence is already being processed.",
        )

    background_tasks.add_task(
        _generate_and_save_insights,
        supabase,
        meeting_id_value,
        transcript_text,
        started_at,
    )
    return {"meeting_id": meeting_id_value, "stage": "analyzing"}
