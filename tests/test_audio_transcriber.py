"""Tests for AudioTranscriber pipeline."""

from pathlib import Path
import shutil
import wave
import subprocess
import pytest

from src.audio_transcriber import AudioConfig, AudioTranscriber
from src.schema.message import Message
from src.utils.vad import run_vad, VadStats


def test_audio_transcriber_smoke_imports(tmp_path):
    cfg = AudioConfig()
    transcriber = AudioTranscriber(cfg)
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice")
    transcriber.transcribe(msg)
    assert "asr" in msg.derived


def test_audio_transcriber_sets_empty_derived_asr():
    transcriber = AudioTranscriber()
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice")
    transcriber.transcribe(msg)

    asr = msg.derived.get("asr")
    assert asr is not None
    assert asr["pipeline_version"] == transcriber.pipeline_version
    # ensure config snapshot includes defaults
    assert asr["config_snapshot"]["sample_rate"] == 16000
    assert asr["config_snapshot"]["chunk_seconds"] == 120.0


def test_non_voice_noop():
    transcriber = AudioTranscriber()
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="text")
    transcriber.transcribe(msg)
    assert "asr" not in msg.derived


def test_ffmpeg_conversion_success_creates_wav(tmp_path, monkeypatch):
    input_path = tmp_path / "voice.opus"
    input_path.write_bytes(b"dummy")

    cfg = AudioConfig(cache_dir=tmp_path / "cache")
    transcriber = AudioTranscriber(cfg)
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(input_path))

    def fake_run(cmd, capture_output, text, timeout, check):
        # simulate ffmpeg success by creating output file
        out_path = Path(cmd[-1])
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"wavdata")
        completed = subprocess.CompletedProcess(cmd, 0, "", "ok")
        return completed

    monkeypatch.setattr(subprocess, "run", fake_run)
    wav_path = transcriber._to_wav(msg)
    assert wav_path is not None
    assert wav_path.exists()
    assert msg.status == "ok"
    assert msg.status_reason is None


def test_ffmpeg_failure_sets_status_and_placeholder(tmp_path, monkeypatch):
    input_path = tmp_path / "voice.opus"
    input_path.write_bytes(b"dummy")

    cfg = AudioConfig(cache_dir=tmp_path / "cache", ffmpeg_max_retries=1)
    transcriber = AudioTranscriber(cfg)
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(input_path))

    def fake_run(cmd, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(cmd, 1, "", "failure")

    monkeypatch.setattr(subprocess, "run", fake_run)
    wav_path = transcriber._to_wav(msg)
    assert wav_path is None
    assert msg.status == "failed"
    assert msg.status_reason.code == "ffmpeg_failed"
    assert msg.content_text == "[AUDIO CONVERSION FAILED]"


def test_vad_stats_recorded_for_nonspeech_audio(tmp_path, monkeypatch):
    wav_path = tmp_path / "silence.wav"
    wav_path.write_bytes(b"\x00" * 32000)  # ~1s of zeros at 16k/mono/16bit

    transcriber = AudioTranscriber()
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(wav_path))

    monkeypatch.setattr(transcriber, "_to_wav", lambda m: wav_path)

    transcriber.transcribe(msg)
    vad = msg.derived["asr"]["vad"]
    assert vad["speech_ratio"] == 0.0
    assert vad["is_mostly_silence"] is True


def test_vad_stats_recorded_for_speech_audio(tmp_path, monkeypatch):
    wav_path = tmp_path / "speech.wav"
    wav_path.write_bytes(b"\x01" * 64000)  # ~2s with non-zero bytes

    transcriber = AudioTranscriber()
    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(wav_path))

    monkeypatch.setattr(transcriber, "_to_wav", lambda m: wav_path)

    transcriber.transcribe(msg)
    vad = msg.derived["asr"]["vad"]
    assert vad["speech_ratio"] > 0
    assert vad["speech_seconds"] > 0


def _make_wav(path: Path, seconds: float, sample_rate: int = 16000):
    n_frames = int(seconds * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x01\x02" * n_frames)


def test_chunking_respects_length_and_overlap(tmp_path, monkeypatch):
    wav_path = tmp_path / "speech.wav"
    _make_wav(wav_path, seconds=5)

    cfg = AudioConfig(chunk_seconds=2.5, chunk_overlap_seconds=0.25, cache_dir=tmp_path / "cache")
    if cfg.cache_dir.exists():
        shutil.rmtree(cfg.cache_dir)
    transcriber = AudioTranscriber(cfg)
    monkeypatch.setattr(transcriber, "_to_wav", lambda m: wav_path)

    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(wav_path))
    transcriber.transcribe(msg)

    chunks = msg.derived["asr"]["chunks"]
    assert len(chunks) == 3  # 0-2.5, 2.25-4.75, 4.5-5
    assert chunks[0]["start_sec"] == 0.0
    assert chunks[0]["end_sec"] == 2.5
    assert chunks[1]["start_sec"] == 2.25
    assert chunks[2]["end_sec"] == pytest.approx(5.0, rel=0, abs=0.01)


def test_asr_partial_status_when_chunk_errors(tmp_path, monkeypatch):
    wav_path = tmp_path / "speech.wav"
    _make_wav(wav_path, seconds=3)

    cfg = AudioConfig(chunk_seconds=2.0, chunk_overlap_seconds=0.0, cache_dir=tmp_path / "cache")
    transcriber = AudioTranscriber(cfg)
    monkeypatch.setattr(transcriber, "_to_wav", lambda m: wav_path)

    original_transcribe = transcriber.asr_client.transcribe_chunk

    def fake_asr(path, start, end):
        if start == 0.0:
            return original_transcribe(path, start, end)
        return original_transcribe(Path(str(path) + "fail"), start, end)

    transcriber.asr_client.transcribe_chunk = fake_asr  # type: ignore

    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(wav_path))
    transcriber.transcribe(msg)
    assert msg.status == "partial"
    assert msg.status_reason.code == "asr_partial"

def test_config_snapshot_paths_are_strings(tmp_path, monkeypatch):
    wav_path = tmp_path / "speech.wav"
    _make_wav(wav_path, seconds=1)

    cfg = AudioConfig(cache_dir=tmp_path / "cache")
    transcriber = AudioTranscriber(cfg)
    monkeypatch.setattr(transcriber, "_to_wav", lambda m: wav_path)

    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(wav_path))
    transcriber.transcribe(msg)

    snapshot = msg.derived["asr"]["config_snapshot"]
    assert isinstance(snapshot["cache_dir"], str)
    assert snapshot["cache_dir"].endswith("cache")


def test_cache_write_and_read_roundtrip(tmp_path, monkeypatch):
    wav_path = tmp_path / "speech.wav"
    _make_wav(wav_path, seconds=1)

    cfg = AudioConfig(cache_dir=tmp_path / "cache")
    transcriber = AudioTranscriber(cfg)
    monkeypatch.setattr(transcriber, "_to_wav", lambda m: wav_path)

    msg = Message(idx=0, ts="2025-01-01T00:00:00", sender="Alice", kind="voice", media_filename=str(wav_path))
    transcriber.transcribe(msg)
    cache_files = list(cfg.cache_dir.glob("*.json"))
    assert cache_files, "cache file should be written"

    # Re-run; should load from cache and not modify transcript
    msg2 = Message(idx=1, ts="2025-01-01T00:00:00", sender="Bob", kind="voice", media_filename=str(wav_path))
    transcriber.transcribe(msg2)
    assert msg2.content_text == msg.content_text
    assert msg2.derived["asr"]["chunks"] == msg.derived["asr"]["chunks"]
