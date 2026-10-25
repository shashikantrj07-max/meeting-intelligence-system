
from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException

from app.config import settings
from app.services.ai.gemini import GeminiMeetingInsightsProvider
from app.schemas.meeting_insights import MeetingInsights
from app.services.supabase import create_request_supabase_client
from app.services.transcription.whisper import WhisperTranscriptionService


router = APIRouter(
    prefix="/api/meetings",
    tags=["meeting transcription"],
)

logger = logging.getLogger(__name__)

PROCESSING_STALE_AFTER = timedelta(minutes=5)

# 500 MB maximum meeting-file size.
MAX_DOWNLOAD_BYTES = 500 * 1024 * 1024


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


def _server_error(
    message: str,
    stage: str,
    error: Exception,
) -> HTTPException:
    logger.error(
        "%s failed (%s): %s",
        stage,
        type(error).__name__,
        str(error),
    )

    return HTTPException(
        status_code=500,
        detail=message,
    )


def _claim_transcription(
    supabase: Any,
    meeting_id: str,
    started_at: str,
    stale_before: str,
) -> bool:
    table = supabase.schema("public").table("meeting_processing")

    update_values = {
        "stage": "transcribing",
        "started_at": started_at,
        "completed_at": None,
        "error_message": None,
    }

    # Reclaim a previous failed/completed attempt.
    reclaimed = (
        table.update(update_values)
        .eq("meeting_id", meeting_id)
        .in_("stage", ["failed", "completed"])
        .select("meeting_id")
        .execute()
    )

    if reclaimed.data:
        return True

    # Reclaim a stale transcription attempt.
    stale_reclaimed = (
        table.update(update_values)
        .eq("meeting_id", meeting_id)
        .eq("stage", "transcribing")
        .lt("started_at", stale_before)
        .select("meeting_id")
        .execute()
    )

    if stale_reclaimed.data:
        return True

    # Create the first processing record.
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
        # Another request won the race.
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
        .eq("stage", "transcribing")
        .eq("started_at", started_at)
        .select("meeting_id")
        .execute()
    )

    return bool(result.data)


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
            logger.info(
                "Skipping failure update for superseded transcription attempt."
            )

    except Exception as exc:
        logger.error(
            "Unable to record failed transcription state "
            "(%s): %s",
            type(exc).__name__,
            str(exc),
        )


def _claim_analysis(
    supabase: Any,
    meeting_id: str,
    started_at: str,
) -> bool:
    """
    Move the current transcription attempt into the analyzing stage.

    The update is guarded by the original transcription timestamp so that
    an older background task cannot take ownership of a newer attempt.
    """

    result = (
        supabase.schema("public")
        .table("meeting_processing")
        .update(
            {
                "stage": "analyzing",
                "error_message": None,
                "completed_at": None,
            }
        )
        .eq("meeting_id", meeting_id)
        .eq("stage", "transcribing")
        .eq("started_at", started_at)
        .select("meeting_id")
        .execute()
    )

    return bool(result.data)


def _update_analysis_attempt(
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


def _is_current_analysis_attempt(
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


def _mark_analysis_failed(
    supabase: Any,
    meeting_id: str,
    started_at: str,
    error_message: str,
) -> None:
    try:
        updated = _update_analysis_attempt(
            supabase,
            meeting_id,
            started_at,
            "failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error_message=error_message,
        )

        if not updated:
            logger.info(
                "Skipping analysis failure update for superseded attempt."
            )

    except Exception as exc:
        logger.error(
            "Unable to record failed analysis state (%s).",
            type(exc).__name__,
        )


def _generate_and_save_insights(
    supabase: Any,
    meeting_id: str,
    transcript_text: str,
    started_at: str,
) -> None:
    """
    Generate Gemini meeting intelligence and save it.

    The processing row must already be in the analyzing stage for the
    original transcription attempt.
    """

    print(
        "=== AUTOMATIC MEETING INTELLIGENCE STARTED ===",
        flush=True,
    )

    try:
        print(
            "=== INTELLIGENCE STEP 1: START GEMINI ===",
            flush=True,
        )

        insights: MeetingInsights = GeminiMeetingInsightsProvider().generate(
            transcript_text
        )

        print(
            "=== INTELLIGENCE STEP 2: GEMINI RETURNED ===",
            flush=True,
        )

    except Exception as exc:
        print(
            "=== AUTOMATIC MEETING INTELLIGENCE FAILED ===",
            flush=True,
        )

        print(
            f"ERROR TYPE: {type(exc).__name__}",
            flush=True,
        )

        print(
            f"ERROR: {exc}",
            flush=True,
        )

        logger.exception(
            "Automatic meeting intelligence generation failed: "
            "meeting_id=%s",
            meeting_id,
        )

        _mark_analysis_failed(
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

    print(
        "=== INTELLIGENCE STEP 3: SAVE INSIGHTS ===",
        flush=True,
    )

    try:
        if not _is_current_analysis_attempt(
            supabase,
            meeting_id,
            started_at,
        ):
            logger.info(
                "Skipping insight save for superseded analysis attempt."
            )
            return

        saved_result = (
            supabase.schema("public")
            .table("meeting_insights")
            .upsert(
                payload,
                on_conflict="meeting_id",
            )
            .select(
                "id, meeting_id, summary, key_decisions, "
                "action_items, discussion_points, open_questions, "
                "next_steps, risks_blockers, created_at, updated_at"
            )
            .single()
            .execute()
        )

    except Exception as exc:
        print(
            "=== INTELLIGENCE SAVE FAILED ===",
            flush=True,
        )

        print(
            f"ERROR TYPE: {type(exc).__name__}",
            flush=True,
        )

        print(
            f"ERROR: {exc}",
            flush=True,
        )

        logger.exception(
            "Meeting insights save failed: meeting_id=%s",
            meeting_id,
        )

        _mark_analysis_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting intelligence could not be saved.",
        )

        return

    if saved_result.data is None:
        logger.error(
            "Meeting insights save returned no data: meeting_id=%s",
            meeting_id,
        )

        _mark_analysis_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting intelligence could not be saved.",
        )

        return

    print(
        "=== INTELLIGENCE SAVED TO DATABASE ===",
        flush=True,
    )

    print(
        "=== INTELLIGENCE STEP 4: MARK COMPLETED ===",
        flush=True,
    )

    try:
        completed = _update_analysis_attempt(
            supabase,
            meeting_id,
            started_at,
            "completed",
            completed_at=datetime.now(
                timezone.utc
            ).isoformat(),
        )

        if not completed:
            logger.info(
                "Skipping intelligence completion update for "
                "superseded analysis attempt."
            )

    except Exception as exc:
        logger.error(
            "Unable to record completed intelligence state (%s).",
            type(exc).__name__,
        )

    print(
        "=== AUTOMATIC MEETING INTELLIGENCE COMPLETED ===",
        flush=True,
    )


def _download_storage_file(
    storage_path: str,
    access_token: str,
) -> bytes:
    """
    Download a private Supabase Storage object through the Storage HTTP API.

    We intentionally do NOT use:
        supabase.storage.from_("meeting-files").download(...)

    because that SDK call was returning a 404 in this project while the
    authenticated HTTP Storage endpoint successfully returned the file.
    """

    storage_url = (
        f"{settings.SUPABASE_URL.rstrip('/')}"
        f"/storage/v1/object/meeting-files/{storage_path}"
    )

    logger.info(
        "=== STORAGE DOWNLOAD START === path=%r",
        storage_path,
    )

    logger.info(
        "Storage URL: %s",
        storage_url,
    )

    try:
        response = httpx.get(
            storage_url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "apikey": settings.SUPABASE_ANON_KEY,
            },
            timeout=120,
        )

    except httpx.HTTPError as exc:
        logger.error(
            "Storage HTTP request failed: %s",
            str(exc),
        )

        raise RuntimeError(
            "Unable to connect to Supabase Storage."
        ) from exc

    logger.info(
        "Storage HTTP response: status=%s content_length=%s",
        response.status_code,
        response.headers.get("content-length"),
    )

    if response.status_code != 200:
        logger.error(
            "Supabase Storage returned HTTP %s: %s",
            response.status_code,
            response.text[:500],
        )

        if response.status_code in (401, 403):
            raise RuntimeError(
                "Supabase Storage denied access to the meeting file."
            )

        if response.status_code == 404:
            raise RuntimeError(
                "The meeting file was not found in Supabase Storage."
            )

        raise RuntimeError(
            "Supabase Storage download failed with HTTP "
            f"{response.status_code}."
        )

    downloaded = response.content

    if not downloaded:
        raise RuntimeError(
            "Supabase Storage returned an empty file."
        )

    if len(downloaded) > MAX_DOWNLOAD_BYTES:
        raise RuntimeError(
            "Meeting file exceeds the maximum supported size."
        )

    logger.info(
        "=== STORAGE DOWNLOAD SUCCESS === %d bytes",
        len(downloaded),
    )

    return downloaded


def _transcribe_and_save(
    supabase: Any,
    meeting_id: str,
    storage_path: str,
    started_at: str,
    access_token: str,
) -> None:
    """
    Background transcription worker.

    Stages:

        1. Download file from Supabase Storage
        2. Write file to temporary disk
        3. Create Whisper service
        4. Run Whisper
        5. Save transcript
        6. Move processing state to analyzing
        7. Run Gemini automatically
        8. Save meeting intelligence
        9. Mark processing completed
    """

    print(
        "=== BACKGROUND TRANSCRIPTION TASK STARTED ===",
        flush=True,
    )

    temporary_path: Path | None = None

    try:
        # ---------------------------------------------------------
        # STEP 1 — Create temporary file
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION STEP 1: CREATE TEMP FILE ===",
            flush=True,
        )

        file_suffix = Path(storage_path).suffix or ".tmp"

        with tempfile.NamedTemporaryFile(
            prefix="meeting-media-",
            suffix=file_suffix,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)

        print(
            f"=== TEMP FILE CREATED: {temporary_path} ===",
            flush=True,
        )

        # ---------------------------------------------------------
        # STEP 2 — Download from Supabase Storage
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION STEP 2: DOWNLOAD STORAGE FILE ===",
            flush=True,
        )

        downloaded = _download_storage_file(
            storage_path,
            access_token,
        )

        print(
            f"=== STORAGE DOWNLOAD COMPLETE: {len(downloaded)} BYTES ===",
            flush=True,
        )

        # ---------------------------------------------------------
        # STEP 3 — Write downloaded bytes to disk
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION STEP 3: WRITE TEMP FILE ===",
            flush=True,
        )

        temporary_path.write_bytes(downloaded)

        print(
            f"=== TEMP FILE WRITTEN: {temporary_path.stat().st_size} BYTES ===",
            flush=True,
        )

        logger.info(
            "Temporary meeting file created: %s (%d bytes)",
            temporary_path,
            len(downloaded),
        )

        # ---------------------------------------------------------
        # STEP 4 — Create Whisper service
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION STEP 4: CREATE WHISPER SERVICE ===",
            flush=True,
        )

        transcription_service = WhisperTranscriptionService()

        print(
            "=== WHISPER SERVICE CREATED ===",
            flush=True,
        )

        # ---------------------------------------------------------
        # STEP 5 — Run Whisper
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION STEP 5: START WHISPER ===",
            flush=True,
        )

        logger.info(
            "Starting Whisper transcription: meeting_id=%s",
            meeting_id,
        )

        transcript_text = transcription_service.transcribe(
            temporary_path
        )

        print(
            "=== WHISPER RETURNED ===",
            flush=True,
        )

        if transcript_text is None:
            raise RuntimeError(
                "Whisper transcription returned None."
            )

        transcript_text = transcript_text.strip()

        print(
            f"=== TRANSCRIPT LENGTH: {len(transcript_text)} ===",
            flush=True,
        )

        if not transcript_text:
            raise ValueError(
                "Whisper returned an empty transcript."
            )

        logger.info(
            "Whisper transcription completed: meeting_id=%s",
            meeting_id,
        )

        # ---------------------------------------------------------
        # STEP 6 — Save transcript
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION STEP 6: SAVE TRANSCRIPT ===",
            flush=True,
        )

        transcript_result = (
            supabase.schema("public")
            .table("meeting_transcripts")
            .upsert(
                {
                    "meeting_id": meeting_id,
                    "content": transcript_text,
                },
                on_conflict="meeting_id",
            )
            .select(
                "id, meeting_id, content"
            )
            .single()
            .execute()
        )

        if transcript_result.data is None:
            raise RuntimeError(
                "Transcript save returned no data."
            )

        print(
            "=== TRANSCRIPT SAVED TO DATABASE ===",
            flush=True,
        )

        # ---------------------------------------------------------
        # STEP 7 — Move processing to analyzing
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION STEP 7: START AUTOMATIC INTELLIGENCE ===",
            flush=True,
        )

        claimed_analysis = _claim_analysis(
            supabase,
            meeting_id,
            started_at,
        )

        if not claimed_analysis:
            logger.info(
                "Skipping automatic intelligence because the "
                "transcription attempt is no longer current."
            )

            print(
                "=== AUTOMATIC INTELLIGENCE SKIPPED ===",
                flush=True,
            )

            return

        # ---------------------------------------------------------
        # STEP 8 — Run Gemini automatically
        # ---------------------------------------------------------

        _generate_and_save_insights(
            supabase,
            meeting_id,
            transcript_text,
            started_at,
        )

        print(
            "=== BACKGROUND TRANSCRIPTION PIPELINE COMPLETED ===",
            flush=True,
        )

        logger.info(
            "Meeting transcription and intelligence pipeline completed: "
            "meeting_id=%s",
            meeting_id,
        )

    except Exception as exc:
        print(
            "=== BACKGROUND TRANSCRIPTION FAILED ===",
            flush=True,
        )

        print(
            f"ERROR TYPE: {type(exc).__name__}",
            flush=True,
        )

        print(
            f"ERROR: {exc}",
            flush=True,
        )

        logger.exception(
            "Meeting transcription failed: meeting_id=%s",
            meeting_id,
        )

        _mark_processing_failed(
            supabase,
            meeting_id,
            started_at,
            "Meeting transcription failed.",
        )

    finally:
        # ---------------------------------------------------------
        # STEP 9 — Remove temporary file
        # ---------------------------------------------------------

        print(
            "=== TRANSCRIPTION CLEANUP ===",
            flush=True,
        )

        if temporary_path is not None:
            try:
                temporary_path.unlink(
                    missing_ok=True
                )

                print(
                    "=== TEMP FILE REMOVED ===",
                    flush=True,
                )

            except Exception as exc:
                logger.warning(
                    "Unable to remove temporary transcription file "
                    "(%s): %s",
                    type(exc).__name__,
                    str(exc),
                )


@router.post(
    "/{meeting_id}/files/{file_id}/transcribe",
    status_code=202,
)
def transcribe_meeting_file(
    meeting_id: UUID,
    file_id: UUID,
    background_tasks: BackgroundTasks,
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    # ---------------------------------------------------------
    # STEP A — Extract bearer token
    # ---------------------------------------------------------

    access_token = _bearer_token(
        authorization
    )

    # ---------------------------------------------------------
    # STEP B — Create authenticated Supabase client
    # ---------------------------------------------------------

    try:
        supabase = create_request_supabase_client(
            access_token
        )

        verified_user = (
            supabase.auth
            .get_user(access_token)
            .user
        )

    except Exception as exc:
        if getattr(exc, "status", None) in (
            400,
            401,
            403,
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "The bearer access token is invalid or expired."
                ),
                headers={
                    "WWW-Authenticate": "Bearer"
                },
            ) from exc

        raise _server_error(
            "Unable to verify the access token.",
            "Supabase token verification",
            exc,
        ) from exc

    if verified_user is None or not verified_user.id:
        raise HTTPException(
            status_code=401,
            detail=(
                "The bearer access token is invalid or expired."
            ),
            headers={
                "WWW-Authenticate": "Bearer"
            },
        )

    meeting_id_value = str(
        meeting_id
    )

    file_id_value = str(
        file_id
    )

    # ---------------------------------------------------------
    # STEP C — Verify meeting ownership
    # ---------------------------------------------------------

    meeting_result = (
        supabase.schema("public")
        .table("meetings")
        .select(
            "id, owner_id"
        )
        .eq(
            "id",
            meeting_id_value,
        )
        .maybe_single()
        .execute()
    )

    if meeting_result.data is None:
        raise HTTPException(
            status_code=404,
            detail="Meeting not found.",
        )

    if (
        meeting_result.data.get("owner_id")
        != verified_user.id
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "You do not have access to this meeting."
            ),
        )

    # ---------------------------------------------------------
    # STEP D — Get meeting file
    # ---------------------------------------------------------

    try:
        file_result = (
            supabase.schema("public")
            .table("meeting_files")
            .select(
                "id, meeting_id, storage_path, "
                "original_filename, mime_type, "
                "file_size_bytes"
            )
            .eq(
                "id",
                file_id_value,
            )
            .eq(
                "meeting_id",
                meeting_id_value,
            )
            .maybe_single()
            .execute()
        )

    except Exception as exc:
        raise _server_error(
            "Unable to check meeting file access.",
            "Meeting file lookup",
            exc,
        ) from exc

    if file_result.data is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Meeting file not found or inaccessible."
            ),
        )

    file_data = file_result.data

    storage_path = file_data.get(
        "storage_path"
    )

    if (
        not isinstance(
            storage_path,
            str,
        )
        or not storage_path.strip()
    ):
        raise HTTPException(
            status_code=500,
            detail=(
                "The meeting file has no valid storage path."
            ),
        )

    # ---------------------------------------------------------
    # STEP E — Validate MIME type
    # ---------------------------------------------------------

    mime_type = file_data.get(
        "mime_type"
    )

    if isinstance(
        mime_type,
        str,
    ):
        if not (
            mime_type.startswith("audio/")
            or mime_type.startswith("video/")
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Only audio and video files "
                    "can be transcribed."
                ),
            )

    # ---------------------------------------------------------
    # STEP F — Claim transcription job
    # ---------------------------------------------------------

    started_at_datetime = datetime.now(
        timezone.utc
    )

    started_at = (
        started_at_datetime.isoformat()
    )

    stale_before = (
        started_at_datetime
        - PROCESSING_STALE_AFTER
    ).isoformat()

    try:
        claimed = _claim_transcription(
            supabase,
            meeting_id_value,
            started_at,
            stale_before,
        )

    except Exception as exc:
        raise _server_error(
            "Unable to start meeting transcription.",
            "Processing state update",
            exc,
        ) from exc

    if not claimed:
        raise HTTPException(
            status_code=409,
            detail=(
                "Meeting transcription is already "
                "being processed."
            ),
        )

    # ---------------------------------------------------------
    # STEP G — Start background transcription
    # ---------------------------------------------------------

    print(
        "=== QUEUING BACKGROUND TRANSCRIPTION ===",
        flush=True,
    )

    background_tasks.add_task(
        _transcribe_and_save,
        supabase,
        meeting_id_value,
        storage_path,
        started_at,
        access_token,
    )

    print(
        "=== BACKGROUND TRANSCRIPTION QUEUED ===",
        flush=True,
    )

    return {
        "meeting_id": meeting_id_value,
        "file_id": file_id_value,
        "stage": "transcribing",
    }
