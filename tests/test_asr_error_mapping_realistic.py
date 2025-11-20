"""Tests for realistic ASR error scenarios and status mapping."""

import tempfile
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.audio_transcriber import AudioConfig, AudioTranscriber
from src.schema.message import Message
from src.utils.asr import AsrChunkResult


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
def multi_chunk_wav(temp_dir):
    """Create a WAV file that will generate multiple chunks."""
    wav_path = temp_dir / "multi_chunk.wav"
    sample_rate = 16000
    duration_sec = 3.0  # 3 seconds should produce 1 chunk with default settings
    n_frames = int(sample_rate * duration_sec)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00" * (n_frames * 2))

    return wav_path


@pytest.fixture
def audio_config(temp_dir):
    """Create an AudioConfig with test-friendly settings."""
    return AudioConfig(
        cache_dir=temp_dir / "cache",
        chunk_seconds=1.0,  # Small chunks for testing
        chunk_overlap_seconds=0.0,  # No overlap for predictable chunk count
    )


def create_mock_asr_result(status, text="", error=None, error_kind=None):
    """Helper to create mock ASR results."""
    return AsrChunkResult(
        status=status,
        text=text,
        start_sec=0.0,
        end_sec=1.0,
        duration_sec=1.0,
        language="en",
        error=error,
        error_kind=error_kind,
        provider_meta={"provider": "test", "model": "test"},
    )


class TestMixedSuccessAndTimeout:
    """Tests for mixed success and timeout scenarios."""

    def test_some_chunks_succeed_last_times_out(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify partial status when some chunks succeed but last times out."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        # Mock transcribe_chunk to succeed first, then timeout
        call_count = [0]

        def mock_transcribe(wav_path, start, end):
            call_count[0] += 1
            if call_count[0] < 3:  # First 2 succeed
                return create_mock_asr_result("ok", text=f"chunk-{call_count[0]}")
            else:  # Last one times out
                return create_mock_asr_result(
                    "error",
                    error="Request timeout",
                    error_kind="timeout"
                )

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        assert m.status == "partial"
        assert m.partial is True
        assert m.status_reason is not None
        assert m.status_reason.code == "asr_partial"

    def test_first_chunk_succeeds_rest_fail(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify partial status when first chunk succeeds but rest fail."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        call_count = [0]

        def mock_transcribe(wav_path, start, end):
            call_count[0] += 1
            if call_count[0] == 1:  # First succeeds
                return create_mock_asr_result("ok", text="first chunk")
            else:  # Rest fail
                return create_mock_asr_result(
                    "error",
                    error="Server error",
                    error_kind="server"
                )

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        assert m.status == "partial"
        assert "first chunk" in m.content_text


class TestAllChunksFail:
    """Tests for all chunks failing scenarios."""

    def test_all_chunks_timeout_maps_to_timeout_asr(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify timeout_asr status reason when all chunks timeout."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        def mock_transcribe(wav_path, start, end):
            return create_mock_asr_result(
                "error",
                error="Request timeout after 30s",
                error_kind="timeout"
            )

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        assert m.status == "failed"
        assert m.partial is False
        assert m.status_reason is not None
        assert m.status_reason.code == "timeout_asr"

    def test_all_chunks_auth_error_maps_to_asr_failed(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify asr_failed status reason when all chunks have auth errors."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        def mock_transcribe(wav_path, start, end):
            return create_mock_asr_result(
                "error",
                error="401 Unauthorized: Invalid API key",
                error_kind="auth"
            )

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        assert m.status == "failed"
        assert m.status_reason.code == "asr_failed"

    def test_all_chunks_quota_error(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify asr_failed status reason when quota exceeded."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        def mock_transcribe(wav_path, start, end):
            return create_mock_asr_result(
                "error",
                error="429 Rate limit exceeded",
                error_kind="quota"
            )

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        assert m.status == "failed"
        assert m.status_reason.code == "asr_failed"


class TestErrorSummaryContents:
    """Tests for error_summary field contents."""

    def test_error_summary_counts_correct(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify error_summary has correct chunk counts."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        call_count = [0]

        def mock_transcribe(wav_path, start, end):
            call_count[0] += 1
            if call_count[0] <= 2:  # First 2 succeed
                return create_mock_asr_result("ok", text=f"chunk-{call_count[0]}")
            else:  # Rest fail
                return create_mock_asr_result(
                    "error",
                    error="Error",
                    error_kind="server"
                )

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        error_summary = m.derived["asr"]["error_summary"]
        assert error_summary["chunks_ok"] == 2
        assert error_summary["chunks_error"] > 0

    def test_error_summary_last_error_kind_correct(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify last_error_kind is correctly captured."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        call_count = [0]

        def mock_transcribe(wav_path, start, end):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_mock_asr_result("ok", text="ok")
            elif call_count[0] == 2:
                return create_mock_asr_result("error", error="server", error_kind="server")
            else:
                # Last error should be timeout
                return create_mock_asr_result("error", error="timeout", error_kind="timeout")

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        error_summary = m.derived["asr"]["error_summary"]
        assert error_summary["last_error_kind"] == "timeout"


class TestPlaceholderText:
    """Tests for placeholder text on failures."""

    def test_failed_transcription_has_placeholder(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify placeholder text is set when transcription fails."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        def mock_transcribe(wav_path, start, end):
            return create_mock_asr_result(
                "error",
                error="Failed",
                error_kind="unknown"
            )

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        assert "[AUDIO TRANSCRIPTION FAILED]" in m.content_text

    def test_partial_transcription_has_content(self, multi_chunk_wav, audio_config, monkeypatch):
        """Verify partial transcription preserves successful content."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        transcriber = AudioTranscriber(audio_config)

        call_count = [0]

        def mock_transcribe(wav_path, start, end):
            call_count[0] += 1
            if call_count[0] == 1:
                return create_mock_asr_result("ok", text="Successfully transcribed")
            else:
                return create_mock_asr_result("error", error="Failed", error_kind="server")

        transcriber.asr_client.transcribe_chunk = mock_transcribe

        m = make_message(
            kind="voice",
            media_filename=str(multi_chunk_wav),
        )

        transcriber.transcribe(m)

        assert m.status == "partial"
        assert "Successfully transcribed" in m.content_text
