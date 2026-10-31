from __future__ import annotations

import importlib
import subprocess
import tempfile
from pathlib import Path
from typing import Any


class WhisperTranscriptionService:
    """Transcribe audio or video media using local Whisper."""

    def __init__(self, model_name: str = "base") -> None:
        self._model_name = model_name
        self._model: Any | None = None

    @property
    def model(self):
        """Load Whisper and its model only when transcription is requested."""
        if self._model is None:
            whisper = importlib.import_module("whisper")
            self._model = whisper.load_model(self._model_name)
        return self._model

    def transcribe(self, media_path: str | Path) -> str:
        source = Path(media_path)

        if not source.is_file():
            raise FileNotFoundError(f"Media file not found: {source}")

        with tempfile.TemporaryDirectory(prefix="meeting-transcription-") as temp_dir:
            temp_audio = Path(temp_dir) / "audio.wav"

            self._extract_audio(source, temp_audio)

            result = self.model.transcribe(
                str(temp_audio),
                fp16=False,
            )

        text = result.get("text", "").strip()

        if not text:
            raise ValueError("Whisper returned an empty transcript.")

        return text

    @staticmethod
    def _extract_audio(source: Path, destination: Path) -> None:
        command = [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(destination),
        ]

        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "FFmpeg is not installed or is not available on PATH."
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                "FFmpeg could not extract an audio track from the media file."
            ) from exc
