from __future__ import annotations

import random
from typing import Any, Callable


MAX_JOB_ATTEMPTS = 3
RETRY_BASE_SECONDS = 30
RETRY_MAX_SECONDS = 900
RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})


class LeaseLostError(RuntimeError):
    pass


class ProcessingJobError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.retryable = retryable


def retry_delay_seconds(
    attempt_count: int,
    *,
    random_value: float | None = None,
) -> int:
    if attempt_count < 1:
        raise ValueError("attempt_count must be positive")

    exponential = min(
        RETRY_BASE_SECONDS * (2 ** (attempt_count - 1)),
        RETRY_MAX_SECONDS,
    )
    jitter = random.random() if random_value is None else random_value
    if not 0 <= jitter <= 1:
        raise ValueError("random_value must be between zero and one")
    return min(RETRY_MAX_SECONDS, exponential + round(exponential * 0.2 * jitter))


def classify_processing_error(error: Exception) -> tuple[bool, str]:
    if isinstance(error, ProcessingJobError):
        return error.retryable, error.category

    status = getattr(error, "status_code", None)
    if status is None:
        status = getattr(error, "code", None)
    try:
        status_code = int(status)
    except (TypeError, ValueError):
        status_code = None

    if status_code in RETRYABLE_HTTP_STATUSES:
        return True, "provider_unavailable"
    if status_code in {401, 403}:
        return False, "authorization_failed"
    if status_code in {400, 404, 413, 415, 422}:
        return False, "invalid_input"
    return False, "processing_failed"


def enqueue_meeting_processing_job(
    supabase: Any,
    *,
    meeting_id: str,
    job_type: str,
    idempotency_key: str,
    file_id: str | None = None,
) -> dict[str, str]:
    result = (
        supabase.schema("public")
        .rpc(
            "enqueue_meeting_processing_job",
            {
                "p_meeting_id": meeting_id,
                "p_job_type": job_type,
                "p_file_id": file_id,
                "p_idempotency_key": idempotency_key,
            },
        )
        .execute()
    )
    data = result.data
    row = data[0] if isinstance(data, list) and data else data
    if not isinstance(row, dict):
        raise RuntimeError("Processing job enqueue returned an invalid response.")

    job_id = row.get("job_id")
    status = row.get("job_status")
    if not isinstance(job_id, str) or not isinstance(status, str):
        raise RuntimeError("Processing job enqueue returned an invalid response.")

    return {"job_id": job_id, "status": status}


def claim_next_processing_job(
    supabase: Any,
    worker_id: str,
    *,
    lease_seconds: int = 120,
    response_hook: Callable[[Any], None] | None = None,
) -> dict[str, Any] | None:
    postgrest = supabase.schema("public")
    session = getattr(postgrest, "session", None)
    if response_hook is not None and session is not None:
        response_hooks = session.event_hooks["response"]
        if response_hook not in response_hooks:
            response_hooks.append(response_hook)

    result = postgrest.rpc(
        "claim_next_meeting_processing_job",
        {
            "p_worker_id": worker_id,
            "p_lease_seconds": lease_seconds,
        },
    ).execute()
    data = result.data
    if not isinstance(data, list) or not data:
        return None
    if not isinstance(data[0], dict):
        raise RuntimeError("Processing job claim returned an invalid response.")
    return data[0]


def finish_processing_job_failure(
    supabase: Any,
    *,
    job_id: str,
    worker_id: str,
    lease_token: str,
    attempt_count: int,
    error: Exception,
) -> str:
    retryable, category = classify_processing_error(error)
    delay = retry_delay_seconds(attempt_count) if retryable else 0
    result = (
        supabase.schema("public")
        .rpc(
            "fail_meeting_processing_job",
            {
                "p_job_id": job_id,
                "p_worker_id": worker_id,
                "p_lease_token": lease_token,
                "p_retryable": retryable,
                "p_error_category": category,
                "p_retry_delay_seconds": delay,
            },
        )
        .execute()
    )
    status = result.data
    if status not in {"retrying", "failed", "superseded"}:
        raise RuntimeError("Processing job failure update returned an invalid response.")
    return status
