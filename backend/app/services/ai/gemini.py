from __future__ import annotations

import logging

from google import genai
from google.genai import types

from app.config import settings
from app.schemas.meeting_insights import MeetingInsights


logger = logging.getLogger(__name__)

# Maximum time allowed for one Gemini HTTP request.
# 120 seconds is intentionally generous for a meeting transcript.
GEMINI_REQUEST_TIMEOUT_MS = 120_000


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

        logger.info(
            "Initializing Gemini meeting insights provider with model=%s",
            self.model,
        )

        self.client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(
                timeout=GEMINI_REQUEST_TIMEOUT_MS,
            ),
        )

    def generate(self, transcript: str) -> MeetingInsights:
        if transcript is None or not transcript.strip():
            raise ValueError(
                "Transcript content is required to generate meeting insights."
            )

        transcript = transcript.strip()

        logger.info(
            "Starting Gemini meeting intelligence generation: "
            "model=%s transcript_length=%d",
            self.model,
            len(transcript),
        )

        prompt = _build_prompt(transcript)

        try:
            logger.info(
                "Sending meeting transcript to Gemini: meeting_model=%s",
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
                "Gemini request completed successfully: model=%s",
                self.model,
            )

        except Exception as exc:
            logger.exception(
                "Gemini API request failed: model=%s error_type=%s",
                self.model,
                type(exc).__name__,
            )

            raise RuntimeError(
                f"Gemini API request failed: {exc}"
            ) from exc

        try:
            payload = response.text

            if not payload or not payload.strip():
                raise ValueError(
                    "Gemini returned an empty structured response."
                )

            logger.info(
                "Gemini returned structured response: characters=%d",
                len(payload),
            )

            insights = MeetingInsights.model_validate_json(payload)

            logger.info(
                "Gemini meeting intelligence validated successfully."
            )

            return insights

        except Exception as exc:
            logger.exception(
                "Gemini response validation failed: error_type=%s",
                type(exc).__name__,
            )

            raise ValueError(
                f"Gemini response validation failed: {exc}"
            ) from exc