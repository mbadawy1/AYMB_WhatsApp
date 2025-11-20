from pathlib import Path
from types import SimpleNamespace

import pytest

from src.utils.asr import AsrClient, AsrConfigError


def test_asr_client_google_basic(monkeypatch):
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/google-creds.json")
    cfg = SimpleNamespace(asr_provider="google_stt", asr_model=None, asr_language="ar")
    client = AsrClient(cfg)

    result = client.transcribe_chunk(Path("chunk.wav"), 0.0, 1.0)
    assert result.status == "ok"
    assert "google" in result.text
    assert result.provider_meta["provider"] == "google_stt"
    assert client.language_hint == "ar"


def test_asr_client_google_env_required(monkeypatch):
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    cfg = SimpleNamespace(asr_provider="google_stt", asr_model=None, asr_language=None)
    with pytest.raises(AsrConfigError):
        AsrClient(cfg)
