from pathlib import Path
from types import SimpleNamespace

import pytest

from src.utils.asr import AsrClient, AsrConfigError


def test_asr_client_whisper_basic(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    cfg = SimpleNamespace(asr_provider="whisper_openai", asr_model=None, asr_language="en")
    client = AsrClient(cfg)

    result = client.transcribe_chunk(Path("chunk.wav"), 0.0, 1.0)
    assert result.status == "ok"
    assert result.text.startswith("whisper-1-chunk-0.00-1.00")
    assert result.provider_meta["provider"] == "whisper_openai"
    assert client.model == "whisper-1"
    assert client.language_hint == "en"


def test_asr_client_unknown_provider(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    cfg = SimpleNamespace(asr_provider="does-not-exist", asr_model=None, asr_language=None)
    with pytest.raises(AsrConfigError):
        AsrClient(cfg)
