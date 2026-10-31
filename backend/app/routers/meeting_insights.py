import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException

from app.schemas.meeting_insights import MeetingInsights
from app.services.ai.gemini import GeminiMeetingInsightsProvider
from app.services.meeting_action_items import sync_generated_action_items
from app.services.processing_jobs import enqueue_meeting_processing_job
from app.services.supabase import create_request_supabase_client

router = APIRouter(prefix="/api/meetings", tags=["meeting insights"])
logger = logging.getLogger(__name__)
# Covers three 120-second Gemini attempts, retry backoff, and a safety margin.
PROCESSING_STALE_AFTER = timedelta(minutes=7)


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
    except Exception:
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
    authorization: str | None = Header(default=None),
    idempotency_key: UUID = Header(alias="Idempotency-Key"),
) -> dict[str, str]:
    request_started = perf_counter()
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
    auth_ms = int((perf_counter() - request_started) * 1000)

    meeting_id_value = str(meeting_id)
    lookup_started = perf_counter()
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
    meeting_lookup_ms = int((perf_counter() - lookup_started) * 1000)

    transcript_started = perf_counter()
    try:
        transcript_result = (
            supabase.schema("public")
            .table("meeting_transcripts")
            .select("meeting_id")
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

    transcript_lookup_ms = int((perf_counter() - transcript_started) * 1000)

    enqueue_started = perf_counter()
    try:
        job = enqueue_meeting_processing_job(
            supabase,
            meeting_id=meeting_id_value,
            job_type="insights",
            idempotency_key=str(idempotency_key),
        )
    except Exception as exc:
        raise _server_error(
            "Unable to queue meeting intelligence processing.",
            "Processing job enqueue",
            exc,
        ) from exc

    enqueue_ms = int((perf_counter() - enqueue_started) * 1000)
    logger.info(
        "Meeting intelligence queued: status=%s auth_ms=%d "
        "meeting_lookup_ms=%d transcript_presence_ms=%d enqueue_ms=%d "
        "request_total_ms=%d",
        job["status"],
        auth_ms,
        meeting_lookup_ms,
        transcript_lookup_ms,
        enqueue_ms,
        int((perf_counter() - request_started) * 1000),
    )

    return {
        "meeting_id": meeting_id_value,
        "job_id": job["job_id"],
        "stage": job["status"],
        "job_status": job["status"],
    }
