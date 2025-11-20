import wave
from pathlib import Path

import pytest

from src.audio_transcriber import AudioConfig, AudioTranscriber
from src.schema.message import Message


def _make_wav(path: Path, seconds: float = 1.0, sample_rate: int = 16000) -> None:
    frame_count = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * frame_count)


def test_derived_asr_provider_model(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    wav_path = tmp_path / "voice.wav"
    _make_wav(wav_path)

    cfg = AudioConfig(
        cache_dir=tmp_path / "cache",
        chunk_dir=tmp_path / "chunks",
        asr_provider="whisper_openai",
        asr_language="en",
    )
    transcriber = AudioTranscriber(cfg)

    # Avoid ffmpeg by stubbing conversion + chunking.
    monkeypatch.setattr(AudioTranscriber, "_to_wav", lambda self, m: wav_path)
    monkeypatch.setattr(AudioTranscriber, "_wav_duration_seconds", lambda self, _: 1.0)
    monkeypatch.setattr(
        AudioTranscriber,
        "_chunk_wav",
        lambda self, _path, _total: [
            {
                "chunk_index": 0,
                "start_sec": 0.0,
                "end_sec": 1.0,
                "duration_sec": 1.0,
                "wav_chunk_path": str(wav_path),
            }
        ],
    )

    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(wav_path))
    transcriber.transcribe(msg)

    asr = msg.derived["asr"]
    assert asr["provider"] == "whisper_openai"
    assert asr["model"] == "whisper-1"
    assert asr["language_hint"] == "en"
    assert asr["chunks"][0]["status"] == "ok"
