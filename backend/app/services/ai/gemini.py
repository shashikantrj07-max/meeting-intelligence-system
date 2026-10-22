from __future__ import annotations

from google import genai
from google.genai import types

from app.config import settings
from app.schemas.meeting_insights import MeetingInsights


class GeminiMeetingInsightsProvider:
    """Simple Gemini-backed meeting insights provider for structured transcript analysis."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL
        if not self.api_key or not self.api_key.strip():
            raise ValueError("GEMINI_API_KEY is not configured.")

        self.client = genai.Client(api_key=self.api_key)

    def generate(self, transcript: str) -> MeetingInsights:
        if transcript is None or not transcript.strip():
            raise ValueError("Transcript content is required to generate meeting insights.")

        prompt = (
            "You are extracting structured meeting intelligence from the transcript only. "
            "Use only information present in the transcript. Never invent decisions, action items, "
            "owners, dates, or risks. Return empty arrays when there is no evidence. "
            "Produce a concise but useful summary. Extract concrete decisions. Extract concrete "
            "action items. Identify risks/blockers only when supported by the transcript."
        )

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[
                    {
                        "text": (
                            f"{prompt}\n\nTranscript:\n{transcript}"
                        )
                    }
                ],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MeetingInsights,
                ),
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini API request failed: {exc}") from exc

        try:
            payload = response.text
            if not payload or not payload.strip():
                raise ValueError("Gemini returned an empty structured response.")
            return MeetingInsights.model_validate_json(payload)
        except Exception as exc:
            raise ValueError(f"Gemini response validation failed: {exc}") from exc
