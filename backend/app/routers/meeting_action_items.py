from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query

from app.schemas.meeting_action_items import (
    ActionItemAccountabilityFilter,
    ActionItemAccountabilityItemsResponse,
    ActionItemAccountabilityRecord,
    ActionItemAccountabilitySummary,
    ActionItemStatusUpdate,
    TrackedActionItem,
    TrackedActionItemsResponse,
)
from app.schemas.meeting_insights import ActionItem
from app.services.meeting_action_items import (
    is_action_item_overdue,
    sync_generated_action_items,
)
from app.services.supabase import create_request_supabase_client


router = APIRouter(prefix="/api/meetings", tags=["meeting action items"])
logger = logging.getLogger(__name__)
ACCOUNTABILITY_PAGE_SIZE = 25


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


def _get_authenticated_client(authorization: str | None) -> Any:
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

        logger.error("Action-item token verification failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to verify the access token.",
        ) from exc

    if verified_user is None or not verified_user.id:
        raise HTTPException(
            status_code=401,
            detail="The bearer access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return supabase


def _verify_meeting_access(supabase: Any, meeting_id: str) -> None:
    try:
        result = (
            supabase.schema("public")
            .table("meetings")
            .select("id")
            .eq("id", meeting_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.error("Action-item meeting lookup failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to check meeting access.",
        ) from exc

    if result.data is None:
        raise HTTPException(
            status_code=404,
            detail="Meeting not found or inaccessible.",
        )


def _read_tracked_action_items(supabase: Any, meeting_id: str) -> list[dict[str, Any]]:
    try:
        result = (
            supabase.schema("public")
            .table("meeting_action_items")
            .select(
                "id, meeting_id, identity_key, text, owner, due_date, "
                "priority, evidence, status, created_at, updated_at"
            )
            .eq("meeting_id", meeting_id)
            .order("created_at")
            .execute()
        )
    except Exception as exc:
        logger.error("Action-item retrieval failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to load tracked action items.",
        ) from exc

    today = datetime.now(timezone.utc).date()
    return [
        {
            **item,
            "is_overdue": is_action_item_overdue(
                item.get("due_date"),
                item["status"],
                today=today,
            ),
        }
        for item in result.data or []
    ]


def _load_generated_action_items(
    supabase: Any,
    meeting_id: str,
) -> list[ActionItem]:
    try:
        result = (
            supabase.schema("public")
            .table("meeting_insights")
            .select("action_items")
            .eq("meeting_id", meeting_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.error("Generated action-item lookup failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to load generated action items.",
        ) from exc

    if result.data is None:
        return []

    values = result.data.get("action_items")
    if not isinstance(values, list):
        raise HTTPException(
            status_code=500,
            detail="Stored action items could not be processed.",
        )

    try:
        return [ActionItem.model_validate(value) for value in values]
    except Exception as exc:
        logger.error("Stored action-item validation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Stored action items could not be processed.",
        ) from exc


@router.get(
    "/action-items/accountability-summary",
    response_model=ActionItemAccountabilitySummary,
)
def get_action_item_accountability_summary(
    authorization: str | None = Header(default=None),
) -> ActionItemAccountabilitySummary:
    supabase = _get_authenticated_client(authorization)
    try:
        result = (
            supabase.schema("public")
            .rpc("get_my_action_item_accountability_summary")
            .execute()
        )
    except Exception as exc:
        logger.error("Action-item accountability RPC failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to load action-item accountability summary.",
        ) from exc

    if not isinstance(result.data, list) or len(result.data) != 1:
        logger.error("Action-item accountability RPC returned an invalid result.")
        raise HTTPException(
            status_code=500,
            detail="Unable to load action-item accountability summary.",
        )
    try:
        return ActionItemAccountabilitySummary.model_validate(result.data[0])
    except Exception as exc:
        logger.error("Action-item accountability result validation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to load action-item accountability summary.",
        ) from exc


@router.get(
    "/action-items/accountability-items",
    response_model=ActionItemAccountabilityItemsResponse,
)
def get_action_item_accountability_items(
    status: ActionItemAccountabilityFilter = Query(default="all"),
    page: int = Query(default=1, ge=1, le=100_000),
    authorization: str | None = Header(default=None),
) -> ActionItemAccountabilityItemsResponse:
    supabase = _get_authenticated_client(authorization)
    offset = (page - 1) * ACCOUNTABILITY_PAGE_SIZE
    try:
        result = (
            supabase.schema("public")
            .rpc(
                "get_my_action_item_accountability_items",
                {"p_status": status, "p_offset": offset},
            )
            .execute()
        )
    except Exception as exc:
        logger.error("Action-item accountability listing failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to load action-item accountability items.",
        ) from exc

    if not isinstance(result.data, list) or len(result.data) > ACCOUNTABILITY_PAGE_SIZE + 1:
        logger.error("Action-item accountability listing returned an invalid result.")
        raise HTTPException(
            status_code=500,
            detail="Unable to load action-item accountability items.",
        )
    has_more = len(result.data) > ACCOUNTABILITY_PAGE_SIZE
    try:
        items = [
            ActionItemAccountabilityRecord.model_validate(row)
            for row in result.data[:ACCOUNTABILITY_PAGE_SIZE]
        ]
    except Exception as exc:
        logger.error("Action-item accountability record validation failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to load action-item accountability items.",
        ) from exc

    return ActionItemAccountabilityItemsResponse(
        items=items,
        page=page,
        page_size=ACCOUNTABILITY_PAGE_SIZE,
        has_more=has_more,
    )


@router.get(
    "/{meeting_id}/action-items",
    response_model=TrackedActionItemsResponse,
)
def get_meeting_action_items(
    meeting_id: UUID,
    authorization: str | None = Header(default=None),
) -> TrackedActionItemsResponse:
    supabase = _get_authenticated_client(authorization)
    meeting_id_value = str(meeting_id)
    _verify_meeting_access(supabase, meeting_id_value)
    return TrackedActionItemsResponse(
        items=_read_tracked_action_items(supabase, meeting_id_value)
    )


@router.post(
    "/{meeting_id}/action-items/sync",
    response_model=TrackedActionItemsResponse,
)
def sync_meeting_action_items(
    meeting_id: UUID,
    authorization: str | None = Header(default=None),
) -> TrackedActionItemsResponse:
    supabase = _get_authenticated_client(authorization)
    meeting_id_value = str(meeting_id)
    _verify_meeting_access(supabase, meeting_id_value)
    generated_items = _load_generated_action_items(supabase, meeting_id_value)

    try:
        sync_generated_action_items(
            supabase,
            meeting_id_value,
            generated_items,
        )
    except Exception as exc:
        logger.error("Action-item synchronization failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to synchronize tracked action items.",
        ) from exc

    return TrackedActionItemsResponse(
        items=_read_tracked_action_items(supabase, meeting_id_value)
    )


@router.patch(
    "/{meeting_id}/action-items/{action_item_id}",
    response_model=TrackedActionItem,
)
def update_meeting_action_item_status(
    meeting_id: UUID,
    action_item_id: UUID,
    update: ActionItemStatusUpdate,
    authorization: str | None = Header(default=None),
) -> TrackedActionItem:
    supabase = _get_authenticated_client(authorization)
    meeting_id_value = str(meeting_id)
    _verify_meeting_access(supabase, meeting_id_value)

    try:
        result = (
            supabase.schema("public")
            .table("meeting_action_items")
            .update({"status": update.status})
            .eq("meeting_id", meeting_id_value)
            .eq("id", str(action_item_id))
            .select(
                "id, meeting_id, identity_key, text, owner, due_date, "
                "priority, evidence, status, created_at, updated_at"
            )
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        logger.error("Action-item status update failed (%s).", type(exc).__name__)
        raise HTTPException(
            status_code=500,
            detail="Unable to update action-item status.",
        ) from exc

    if result.data is None:
        raise HTTPException(
            status_code=404,
            detail="Action item not found or inaccessible.",
        )

    updated_item = result.data
    updated_item["is_overdue"] = is_action_item_overdue(
        updated_item.get("due_date"),
        updated_item["status"],
        today=datetime.now(timezone.utc).date(),
    )
    return TrackedActionItem.model_validate(updated_item)
