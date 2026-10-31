from types import SimpleNamespace

from app.services.transcription import whisper as whisper_service_module
from app.services.transcription.whisper import WhisperTranscriptionService


def test_whisper_library_and_model_load_only_when_transcription_starts(
    monkeypatch,
    tmp_path,
) -> None:
    class FakeModel:
        def transcribe(self, _media_path: str, *, fp16: bool) -> dict[str, str]:
            assert fp16 is False
            return {"text": "  meeting transcript  "}

    model = FakeModel()
    load_model_calls: list[str] = []
    import_calls: list[str] = []

    def load_model(model_name: str) -> FakeModel:
        load_model_calls.append(model_name)
        return model

    def import_module(module_name: str) -> SimpleNamespace:
        import_calls.append(module_name)
        return SimpleNamespace(load_model=load_model)

    monkeypatch.setattr(
        whisper_service_module.importlib,
        "import_module",
        import_module,
    )
    service = WhisperTranscriptionService(model_name="small")

    assert import_calls == []
    assert load_model_calls == []

    media_path = tmp_path / "meeting.wav"
    media_path.write_bytes(b"synthetic audio placeholder")
    monkeypatch.setattr(
        service,
        "_extract_audio",
        lambda _source, _destination: None,
    )

    assert service.transcribe(media_path) == "meeting transcript"
    assert import_calls == ["whisper"]
    assert load_model_calls == ["small"]
