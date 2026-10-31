from __future__ import annotations

import contextvars
import logging
import re
import sys
from dataclasses import dataclass, field
from time import perf_counter
from uuid import uuid4

from google import genai
from google.genai import types

from app.config import settings
from app.schemas.meeting_insights import MeetingInsights


logger = logging.getLogger(__name__)

# Maximum time allowed for one Gemini HTTP request.
# 120 seconds is intentionally generous for a meeting transcript.
GEMINI_REQUEST_TIMEOUT_MS = 120_000
GEMINI_RETRY_ATTEMPTS = 3
GEMINI_RETRY_MAX_DELAY_SECONDS = 8.0
GEMINI_RETRY_HTTP_STATUS_CODES = (408, 429, 500, 502, 503, 504)


@dataclass
class _GeminiRequestAttempt:
    request_id: str
    max_attempts: int
    attempt: int = 1
    started_at: float = field(default_factory=perf_counter)


_active_request_attempt: contextvars.ContextVar[
    _GeminiRequestAttempt | None
] = contextvars.ContextVar("active_gemini_request_attempt", default=None)


class _GeminiRetryLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name != "google_genai._api_client"
            or not isinstance(record.msg, str)
            or not record.msg.startswith("Retrying ")
        ):
            return True

        marker = " as it raised "
        if marker not in record.msg:
            record.msg = (
                "Gemini SDK retry scheduled: error_type=UnknownError "
                "will_retry=true"
            )
            record.args = ()
            return True

        detail = record.msg.partition(marker)[2]
        error_type = detail.split(":", 1)[0].split()[0]
        status_match = re.match(r"[^:]+:\s*(\d{3})\b", detail)
        status = status_match.group(1) if status_match else "none"
        delay_match = re.search(
            r"\bin\s+([0-9]+(?:\.[0-9]+)?)\s+seconds\b",
            record.msg,
        )
        retry_delay = delay_match.group(1) if delay_match else "unknown"

        attempt = _active_request_attempt.get()
        if attempt is None:
            record.msg = (
                "Gemini SDK retry scheduled: status=%s error_type=%s "
                "retry_delay_seconds=%s will_retry=true"
            )
            record.args = (status, error_type, retry_delay)
            return True

        elapsed_ms = int((perf_counter() - attempt.started_at) * 1000)
        record.msg = (
            "Gemini request_id=%s attempt %d/%d failed: status=%s "
            "error_type=%s elapsed_total_ms=%d retry_delay_seconds=%s "
            "will_retry=true"
        )
        record.args = (
            attempt.request_id,
            attempt.attempt,
            attempt.max_attempts,
            status,
            error_type,
            elapsed_ms,
            retry_delay,
        )
        attempt.attempt += 1
        return True


_sdk_api_logger = logging.getLogger("google_genai._api_client")
_sdk_api_logger.setLevel(logging.INFO)
_sdk_api_logger.addFilter(_GeminiRetryLogFilter())


def _gemini_http_options() -> types.HttpOptions:
    return types.HttpOptions(
        timeout=GEMINI_REQUEST_TIMEOUT_MS,
        retry_options=types.HttpRetryOptions(
            attempts=GEMINI_RETRY_ATTEMPTS,
            initial_delay=1.0,
            max_delay=GEMINI_RETRY_MAX_DELAY_SECONDS,
            exp_base=2.0,
            jitter=1.0,
            http_status_codes=list(GEMINI_RETRY_HTTP_STATUS_CODES),
        ),
    )


_startup_http_options = _gemini_http_options()
logger.info(
    "Gemini runtime detected: python=%s sdk_version=%s http_options=%s",
    sys.executable,
    genai.__version__,
    _startup_http_options.model_dump(exclude_none=True),
)


def _gemini_response_schema() -> dict[str, object]:
    schema = MeetingInsights.model_json_schema()
    _remove_additional_properties(schema)
    return schema


def _remove_additional_properties(value: object) -> None:
    if isinstance(value, dict):
        value.pop("additionalProperties", None)
        for nested_value in value.values():
            _remove_additional_properties(nested_value)
    elif isinstance(value, list):
        for nested_value in value:
            _remove_additional_properties(nested_value)


def _build_prompt(transcript: str) -> str:
    return (
        "You are extracting structured meeting intelligence from the "
        "transcript only.\n\n"
        "Use only information explicitly present in the transcript. "
        "Never invent decisions, action items, owners, dates, deadlines, "
        "risks, blockers, questions, or next steps.\n"
        "Return empty arrays when there is no evidence. Return an item only "
        "when it is supported by the transcript.\n"
        "For every extracted item, provide evidence as a concise excerpt "
        "copied directly from the transcript. Never invent evidence. If no "
        "reliable supporting excerpt exists, set evidence to null.\n\n"
        "Produce a concise but useful summary.\n"
        "Extract key decisions only when an actual decision or commitment "
        "was reached in the meeting. Do not classify ordinary discussion, "
        "suggestions, opinions, or historical statements as decisions.\n"
        "Extract action items only for concrete tasks or commitments, not "
        "general discussion. Set text to the concrete task. Include an "
        "owner, due date, or priority only when explicitly supported by "
        "the transcript; do not infer an owner or deadline because a person "
        "was mentioned.\n"
        "Identify risks or blockers only when the transcript supports an "
        "actual concern, obstacle, dependency, or potential problem. Do not "
        "treat ordinary technical discussion as a risk automatically.\n"
        "Extract discussion points as substantive topics or issues "
        "discussed in the meeting.\n"
        "Extract open questions as questions or issues that remain "
        "unresolved according to the transcript.\n"
        "Extract next steps as concrete follow-up activities supported "
        "by the transcript.\n\n"
        f"Transcript:\n{transcript}"
    )


class GeminiMeetingInsightsProvider:
    """Gemini-backed provider for structured meeting intelligence."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL

        if not self.api_key or not self.api_key.strip():
            raise ValueError("GEMINI_API_KEY is not configured.")

        if not self.model or not self.model.strip():
            raise ValueError("GEMINI_MODEL is not configured.")

        http_options = _gemini_http_options()
        self.client = genai.Client(
            api_key=self.api_key,
            http_options=http_options,
        )
        logger.info(
            "Initialized Gemini client: model=%s python=%s sdk_version=%s "
            "http_options=%s",
            self.model,
            sys.executable,
            genai.__version__,
            http_options.model_dump(exclude_none=True),
        )

    def generate(self, transcript: str) -> MeetingInsights:
        if transcript is None or not transcript.strip():
            raise ValueError(
                "Transcript content is required to generate meeting insights."
            )

        transcript = transcript.strip()
        request_id = uuid4().hex

        logger.info(
            "Starting Gemini meeting intelligence generation: "
            "request_id=%s model=%s transcript_length=%d",
            request_id,
            self.model,
            len(transcript),
        )

        prompt = _build_prompt(transcript)
        attempt = _GeminiRequestAttempt(
            request_id=request_id,
            max_attempts=GEMINI_RETRY_ATTEMPTS,
        )
        attempt_token = _active_request_attempt.set(attempt)

        try:
            logger.info(
                "Sending meeting transcript to Gemini: request_id=%s "
                "meeting_model=%s",
                request_id,
                self.model,
            )

            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_gemini_response_schema(),
                ),
            )

            logger.info(
                "Gemini request completed successfully: request_id=%s model=%s",
                request_id,
                self.model,
            )
            logger.info(
                "Gemini request_id=%s attempt %d/%d completed: "
                "elapsed_total_ms=%d will_retry=false final_outcome=success",
                request_id,
                attempt.attempt,
                attempt.max_attempts,
                int((perf_counter() - attempt.started_at) * 1000),
            )

        except Exception as exc:
            status = getattr(exc, "code", None)
            if not isinstance(status, int):
                status = "none"
            logger.error(
                "Gemini request_id=%s attempt %d/%d failed: status=%s "
                "error_type=%s elapsed_total_ms=%d will_retry=false "
                "final_outcome=failure",
                request_id,
                attempt.attempt,
                attempt.max_attempts,
                status,
                type(exc).__name__,
                int((perf_counter() - attempt.started_at) * 1000),
            )

            raise RuntimeError(
                "Gemini API request failed "
                f"({type(exc).__name__}, status={status})."
            ) from None
        finally:
            _active_request_attempt.reset(attempt_token)

        try:
            payload = response.text

            if not payload or not payload.strip():
                raise ValueError(
                    "Gemini returned an empty structured response."
                )

            logger.info(
                "Gemini returned structured response: request_id=%s "
                "characters=%d",
                request_id,
                len(payload),
            )

            insights = MeetingInsights.model_validate_json(payload)

            logger.info(
                "Gemini meeting intelligence validated successfully: "
                "request_id=%s",
                request_id,
            )

            return insights

        except Exception as exc:
            logger.error(
                "Gemini response validation failed: request_id=%s "
                "error_type=%s",
                request_id,
                type(exc).__name__,
            )

            raise ValueError(
                "Gemini response validation failed."
            ) from None