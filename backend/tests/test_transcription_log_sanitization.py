from contextlib import nullcontext
import logging

import httpx
import pytest

from app.routers.meeting_transcription import (
    _download_storage_file,
    _server_error,
)
from app.services.processing_jobs import ProcessingJobError


def test_storage_response_body_is_not_logged(monkeypatch, caplog, tmp_path) -> None:
    sensitive_body = "provider response contains PRIVATE_CONTENT"
    response = httpx.Response(502, text=sensitive_body)
    monkeypatch.setattr(
        "app.routers.meeting_transcription.httpx.stream",
        lambda *_args, **_kwargs: nullcontext(response),
    )

    with caplog.at_level(logging.ERROR, logger="app.routers.meeting_transcription"):
        with pytest.raises(
            ProcessingJobError,
            match="download failed with HTTP 502",
        ) as error:
            _download_storage_file(
                "user/file.wav",
                "test-token",
                tmp_path / "download.wav",
            )

    assert error.value.category == "storage_unavailable"
    assert error.value.retryable is True
    assert "PRIVATE_CONTENT" not in str(error.value)
    assert "HTTP 502" in caplog.text
    assert sensitive_body not in caplog.text


def test_storage_transport_error_text_is_not_logged(monkeypatch, caplog, tmp_path) -> None:
    sensitive_detail = "request URL contains PRIVATE_TOKEN"

    def fail_request(*_args, **_kwargs):
        raise httpx.ConnectError(sensitive_detail)

    monkeypatch.setattr(
        "app.routers.meeting_transcription.httpx.stream",
        fail_request,
    )

    with caplog.at_level(logging.ERROR, logger="app.routers.meeting_transcription"):
        with pytest.raises(RuntimeError, match="Unable to connect"):
            _download_storage_file(
                "user/file.wav",
                "test-token",
                tmp_path / "download.wav",
            )

    assert "ConnectError" in caplog.text
    assert sensitive_detail not in caplog.text


def test_storage_download_enforces_size_limit_while_streaming(
    monkeypatch,
    tmp_path,
) -> None:
    class _StreamingResponse:
        status_code = 200
        headers: dict[str, str] = {}

        def __enter__(self) -> "_StreamingResponse":
            return self

        def __exit__(self, *_args) -> None:
            return None

        @staticmethod
        def iter_bytes(*, chunk_size: int):
            assert chunk_size == 64 * 1024
            yield b"12"
            yield b"34"

    response = _StreamingResponse()
    monkeypatch.setattr(
        "app.routers.meeting_transcription.httpx.stream",
        lambda *_args, **_kwargs: response,
    )
    monkeypatch.setattr(
        "app.routers.meeting_transcription.MAX_DOWNLOAD_BYTES",
        3,
    )
    destination = tmp_path / "download.wav"

    with pytest.raises(RuntimeError, match="maximum supported size"):
        _download_storage_file("user/file.wav", "test-token", destination)

    assert destination.stat().st_size <= 3


def test_storage_download_streams_to_temporary_file(monkeypatch, tmp_path) -> None:
    response = httpx.Response(200, content=b"audio-bytes")
    monkeypatch.setattr(
        "app.routers.meeting_transcription.httpx.stream",
        lambda *_args, **_kwargs: nullcontext(response),
    )
    destination = tmp_path / "download.wav"

    downloaded_size = _download_storage_file(
        "user/file.wav",
        "test-token",
        destination,
    )

    assert downloaded_size == len(b"audio-bytes")
    assert destination.read_bytes() == b"audio-bytes"


def test_server_error_logs_exception_type_without_details(caplog) -> None:
    sensitive_detail = "database response contains PRIVATE_CONTENT"

    with caplog.at_level(logging.ERROR, logger="app.routers.meeting_transcription"):
        _server_error(
            "Request failed.",
            "Database lookup",
            RuntimeError(sensitive_detail),
        )

    assert "RuntimeError" in caplog.text
    assert sensitive_detail not in caplog.text
