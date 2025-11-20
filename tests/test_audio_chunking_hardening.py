"""Tests for audio chunking error handling and hardening."""

import tempfile
import wave
from pathlib import Path

import pytest

from src.audio_transcriber import AudioConfig, AudioTranscriber, ChunkingError
from src.schema.message import Message


def make_message(**kwargs):
    """Create a Message with required fields filled in."""
    defaults = {
        "idx": 0,
        "ts": "2025-01-01T00:00:00",
        "sender": "Test",
        "kind": "text",
        "content_text": "",
        "derived": {},
    }
    defaults.update(kwargs)
    return Message(**defaults)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_wav_file(temp_dir):
    """Create a valid WAV file with 1 second of audio."""
    wav_path = temp_dir / "valid.wav"
    sample_rate = 16000
    duration_sec = 1.0
    n_frames = int(sample_rate * duration_sec)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Write silence (zeros)
        wf.writeframes(b"\x00" * (n_frames * 2))

    return wav_path


@pytest.fixture
def zero_length_wav(temp_dir):
    """Create a 0-length WAV file."""
    wav_path = temp_dir / "zero_length.wav"

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        # Write no frames
        wf.writeframes(b"")

    return wav_path


@pytest.fixture
def audio_config(temp_dir):
    """Create an AudioConfig with test-friendly settings."""
    return AudioConfig(
        cache_dir=temp_dir / "cache",
        chunk_seconds=10.0,
        chunk_overlap_seconds=0.25,
    )


class TestChunkingFailureSetsFailedStatus:
    """Tests for test_chunking_failure_sets_failed_status."""

    def test_zero_length_wav_raises_chunking_error(self, zero_length_wav, audio_config, monkeypatch):
        """Verify 0-length WAV raises ChunkingError."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        with pytest.raises(ChunkingError) as exc_info:
            transcriber._chunk_wav(zero_length_wav, 0.0)

        assert "Invalid audio duration" in str(exc_info.value)

    def test_zero_length_transcribe_sets_failed_status(self, zero_length_wav, audio_config, monkeypatch):
        """Verify transcribe sets failed status for 0-length WAV."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        m = make_message(
            kind="voice",
            media_filename=str(zero_length_wav),
        )

        transcriber.transcribe(m)

        assert m.status == "failed"
        assert m.status_reason is not None
        assert m.status_reason.code == "asr_failed"
        assert "[AUDIO TRANSCRIPTION FAILED" in m.content_text

    def test_chunking_failure_sets_error_summary(self, zero_length_wav, audio_config, monkeypatch):
        """Verify error_summary is set for chunking failures."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        m = make_message(
            kind="voice",
            media_filename=str(zero_length_wav),
        )

        transcriber.transcribe(m)

        asr_info = m.derived.get("asr", {})
        error_summary = asr_info.get("error_summary", {})

        assert error_summary["chunks_ok"] == 0
        assert error_summary["chunks_error"] == 0
        assert error_summary["last_error_kind"] == "chunking"
        assert error_summary["last_error_message"] is not None


class TestChunkManifestNonEmptyForValidAudio:
    """Tests for test_chunk_manifest_non_empty_for_valid_audio."""

    def test_valid_audio_produces_chunks(self, valid_wav_file, audio_config, monkeypatch):
        """Verify valid audio produces non-empty chunk list."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        # Get duration
        duration = transcriber._wav_duration_seconds(valid_wav_file)
        assert duration > 0

        # Chunk should succeed
        chunks = transcriber._chunk_wav(valid_wav_file, duration)

        assert len(chunks) > 0

    def test_chunks_have_increasing_timestamps(self, valid_wav_file, audio_config, monkeypatch):
        """Verify chunks have strictly increasing timestamps."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        duration = transcriber._wav_duration_seconds(valid_wav_file)
        chunks = transcriber._chunk_wav(valid_wav_file, duration)

        prev_start = -1.0
        for chunk in chunks:
            assert chunk["start_sec"] > prev_start
            assert chunk["end_sec"] > chunk["start_sec"]
            prev_start = chunk["start_sec"]

    def test_chunk_paths_exist(self, valid_wav_file, audio_config, monkeypatch):
        """Verify chunk WAV files are actually created."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        duration = transcriber._wav_duration_seconds(valid_wav_file)
        chunks = transcriber._chunk_wav(valid_wav_file, duration)

        for chunk in chunks:
            chunk_path = Path(chunk["wav_chunk_path"])
            assert chunk_path.exists()


class TestAsrChunkingErrorSetsErrorSummary:
    """Tests for test_asr_chunking_error_sets_error_summary."""

    def test_missing_wav_raises_chunking_error(self, audio_config, temp_dir, monkeypatch):
        """Verify missing WAV file raises ChunkingError."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        missing_path = temp_dir / "does_not_exist.wav"

        with pytest.raises(ChunkingError) as exc_info:
            transcriber._chunk_wav(missing_path, 1.0)

        assert "not found" in str(exc_info.value)

    def test_negative_duration_raises_chunking_error(self, valid_wav_file, audio_config, monkeypatch):
        """Verify negative duration raises ChunkingError."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        with pytest.raises(ChunkingError) as exc_info:
            transcriber._chunk_wav(valid_wav_file, -1.0)

        assert "Invalid audio duration" in str(exc_info.value)

    def test_derived_asr_always_has_required_fields(self, zero_length_wav, audio_config, monkeypatch):
        """Verify derived['asr'] has required fields even on failure."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        m = make_message(
            kind="voice",
            media_filename=str(zero_length_wav),
        )

        transcriber.transcribe(m)

        asr_info = m.derived.get("asr", {})

        # Required fields should be present
        assert "total_duration_seconds" in asr_info
        assert "chunks" in asr_info
        assert "error_summary" in asr_info
        assert isinstance(asr_info["chunks"], list)


class TestEdgeCases:
    """Additional edge case tests."""

    def test_truncated_wav_header(self, temp_dir, audio_config, monkeypatch):
        """Verify truncated WAV file raises ChunkingError."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        # Create a truncated WAV (just RIFF header, no data)
        truncated_path = temp_dir / "truncated.wav"
        truncated_path.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")

        with pytest.raises(ChunkingError):
            transcriber._chunk_wav(truncated_path, 1.0)

    def test_non_voice_message_skipped(self, valid_wav_file, audio_config, monkeypatch):
        """Verify non-voice messages are skipped without error."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        m = make_message(
            kind="text",
            media_filename=str(valid_wav_file),
            content_text="Hello",
        )

        # Should return without processing
        transcriber.transcribe(m)

        assert m.status == "ok"
        assert "asr" not in m.derived or m.derived.get("asr") == {}
