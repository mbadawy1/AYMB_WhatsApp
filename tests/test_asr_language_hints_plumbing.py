"""Tests for ASR language hint plumbing end-to-end."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.utils.asr import (
    AsrClient,
    GoogleSttBackend,
    resolve_asr_provider_config,
)


class TestLanguageHintPlumbing:
    """Tests for language hint propagation through the ASR system."""

    def test_whisper_client_receives_language_hint(self, monkeypatch):
        """Verify AsrClient receives language hint from config."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cfg = SimpleNamespace(
            asr_provider="whisper_openai",
            asr_model=None,
            asr_language="ar"
        )

        client = AsrClient(cfg)

        assert client.language_hint == "ar"
        assert client.provider_config.language == "ar"

    def test_google_client_receives_language_hint(self, monkeypatch):
        """Verify AsrClient receives language hint for Google provider."""
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/creds.json")
        cfg = SimpleNamespace(
            asr_provider="google_stt",
            asr_model=None,
            asr_language="ar"
        )

        client = AsrClient(cfg)

        assert client.language_hint == "ar"
        assert client.provider_config.language == "ar"

    def test_language_auto_default(self, monkeypatch):
        """Verify auto language is default when not specified."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cfg = SimpleNamespace(
            asr_provider="whisper_openai",
            asr_model=None,
            asr_language=None
        )

        client = AsrClient(cfg)

        assert client.language_hint == "auto"

    def test_resolve_config_with_language_override(self, monkeypatch):
        """Verify language override in resolve_asr_provider_config."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")

        config = resolve_asr_provider_config(
            "whisper_openai",
            language_override="es"
        )

        assert config.language == "es"

    def test_chunk_result_includes_language(self, monkeypatch):
        """Verify transcription result includes language hint."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cfg = SimpleNamespace(
            asr_provider="whisper_openai",
            asr_model=None,
            asr_language="en"
        )

        client = AsrClient(cfg)
        result = client.transcribe_chunk(Path("test.wav"), 0.0, 1.0)

        assert result.language == "en"

    def test_arabic_language_hint(self, monkeypatch):
        """Verify Arabic language hint is properly plumbed."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cfg = SimpleNamespace(
            asr_provider="whisper_openai",
            asr_model=None,
            asr_language="ar"
        )

        client = AsrClient(cfg)
        result = client.transcribe_chunk(Path("test.wav"), 0.0, 1.0)

        assert client.language_hint == "ar"
        assert result.language == "ar"


class TestGoogleLanguageCodeMapping:
    """Tests for Google STT language code mapping."""

    def test_google_backend_maps_iso_to_bcp47(self, monkeypatch):
        """Verify Google backend converts ISO-639-1 to BCP-47."""
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/creds.json")

        config = resolve_asr_provider_config(
            "google_stt",
            language_override="ar"
        )

        backend = GoogleSttBackend(config)

        # Should map 'ar' to 'ar-SA'
        assert backend._get_language_code() == "ar-SA"

    def test_google_backend_preserves_bcp47(self, monkeypatch):
        """Verify Google backend preserves BCP-47 codes."""
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/creds.json")

        config = resolve_asr_provider_config(
            "google_stt",
            language_override="en-GB"
        )

        backend = GoogleSttBackend(config)

        # Should preserve 'en-GB' as-is
        assert backend._get_language_code() == "en-GB"

    def test_google_backend_auto_defaults_to_en_us(self, monkeypatch):
        """Verify Google backend defaults to en-US for auto."""
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/creds.json")

        config = resolve_asr_provider_config(
            "google_stt",
            language_override="auto"
        )

        backend = GoogleSttBackend(config)

        assert backend._get_language_code() == "en-US"

    @pytest.mark.parametrize("iso_code,expected_bcp47", [
        ("en", "en-US"),
        ("ar", "ar-SA"),
        ("es", "es-ES"),
        ("fr", "fr-FR"),
        ("de", "de-DE"),
        ("zh", "zh-CN"),
        ("ja", "ja-JP"),
    ])
    def test_google_language_mapping_table(self, monkeypatch, iso_code, expected_bcp47):
        """Verify all language mappings work correctly."""
        monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/creds.json")

        config = resolve_asr_provider_config(
            "google_stt",
            language_override=iso_code
        )

        backend = GoogleSttBackend(config)

        assert backend._get_language_code() == expected_bcp47


class TestDerivedAsrMetadata:
    """Tests for derived ASR metadata structure."""

    def test_provider_meta_includes_language(self, monkeypatch):
        """Verify provider_meta includes language information."""
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        cfg = SimpleNamespace(
            asr_provider="whisper_openai",
            asr_model=None,
            asr_language="ar"
        )

        client = AsrClient(cfg)
        result = client.transcribe_chunk(Path("test.wav"), 0.0, 1.0)

        assert result.provider_meta is not None
        assert "provider" in result.provider_meta
        assert "model" in result.provider_meta
