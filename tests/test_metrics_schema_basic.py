"""Test metrics.schema.json validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.metrics import METRICS_SCHEMA_VERSION, RunMetrics, validate_metrics


@pytest.fixture
def repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def metrics_schema_path(repo_root: Path) -> Path:
    """Get path to metrics schema file."""
    return repo_root / "schema" / "metrics.schema.json"


@pytest.fixture
def metrics_schema(metrics_schema_path: Path) -> dict:
    """Load metrics schema."""
    return json.loads(metrics_schema_path.read_text(encoding="utf-8"))


class TestMetricsSchemaExists:
    """Test that the metrics schema file exists and is valid JSON."""

    def test_schema_file_exists(self, metrics_schema_path: Path) -> None:
        """Schema file should exist."""
        assert metrics_schema_path.exists(), f"Schema not found at {metrics_schema_path}"

    def test_schema_is_valid_json(self, metrics_schema: dict) -> None:
        """Schema should be valid JSON."""
        assert isinstance(metrics_schema, dict)
        assert "$schema" in metrics_schema
        assert metrics_schema["$schema"] == "http://json-schema.org/draft-07/schema#"

    def test_schema_has_required_fields(self, metrics_schema: dict) -> None:
        """Schema should define all required top-level fields."""
        assert "title" in metrics_schema
        assert metrics_schema["title"] == "RunMetrics"
        assert "type" in metrics_schema
        assert metrics_schema["type"] == "object"
        assert "required" in metrics_schema
        assert "properties" in metrics_schema


class TestMetricsValidation:
    """Test validation of metrics documents against the schema."""

    def test_valid_metrics_passes(self) -> None:
        """A valid metrics document should pass schema validation."""
        metrics = RunMetrics(
            schema_version=METRICS_SCHEMA_VERSION,
            messages_total=100,
            voice_total=10,
            voice_status={"ok": 8, "partial": 1, "failed": 1},
            media_resolution={"resolved": 5, "unresolved": 2, "ambiguous": 1},
            audio_seconds_total=45.5,
            asr_cost_total_usd=0.05,
            wall_clock_seconds=120.0,
            asr_provider="whisper_openai",
            asr_model="whisper-1",
            asr_language="en",
        )

        # Should not raise
        validate_metrics(metrics.to_dict())

    def test_missing_required_field_fails(self) -> None:
        """Metrics missing required field should fail validation."""
        invalid_metrics = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            # missing other required fields
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)

    def test_negative_counts_fail(self) -> None:
        """Metrics with negative counts should fail validation."""
        invalid_metrics = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": -1,  # Negative count
            "voice_total": 10,
            "voice_status": {"ok": 8, "partial": 1, "failed": 1},
            "media_resolution": {"resolved": 5, "unresolved": 2, "ambiguous": 1},
            "audio_seconds_total": 45.5,
            "asr_cost_total_usd": 0.05,
            "wall_clock_seconds": 120.0,
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)

    def test_invalid_schema_version_format_fails(self) -> None:
        """Metrics with invalid schema_version format should fail validation."""
        invalid_metrics = {
            "schema_version": "not-semver",  # Invalid semver format
            "messages_total": 100,
            "voice_total": 10,
            "voice_status": {"ok": 8, "partial": 1, "failed": 1},
            "media_resolution": {"resolved": 5, "unresolved": 2, "ambiguous": 1},
            "audio_seconds_total": 45.5,
            "asr_cost_total_usd": 0.05,
            "wall_clock_seconds": 120.0,
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)

    def test_null_asr_fields_allowed(self) -> None:
        """Metrics with null ASR fields should pass validation."""
        metrics_data = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            "voice_total": 0,  # No voice messages
            "voice_status": {"ok": 0, "partial": 0, "failed": 0},
            "media_resolution": {"resolved": 5, "unresolved": 2, "ambiguous": 1},
            "audio_seconds_total": 0.0,
            "asr_cost_total_usd": 0.0,
            "wall_clock_seconds": 10.0,
            "asr_provider": None,  # No ASR used
            "asr_model": None,
            "asr_language": None,
        }

        # Should not raise
        validate_metrics(metrics_data)


class TestVoiceStatusSchema:
    """Test voice_status object schema validation."""

    def test_voice_status_requires_all_keys(self) -> None:
        """voice_status must have ok, partial, and failed keys."""
        invalid_metrics = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            "voice_total": 10,
            "voice_status": {"ok": 8, "partial": 1},  # Missing 'failed'
            "media_resolution": {"resolved": 5, "unresolved": 2, "ambiguous": 1},
            "audio_seconds_total": 45.5,
            "asr_cost_total_usd": 0.05,
            "wall_clock_seconds": 120.0,
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)

    def test_voice_status_no_extra_keys(self) -> None:
        """voice_status should not allow extra keys."""
        invalid_metrics = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            "voice_total": 10,
            "voice_status": {
                "ok": 8,
                "partial": 1,
                "failed": 1,
                "extra_key": 5,  # Not allowed
            },
            "media_resolution": {"resolved": 5, "unresolved": 2, "ambiguous": 1},
            "audio_seconds_total": 45.5,
            "asr_cost_total_usd": 0.05,
            "wall_clock_seconds": 120.0,
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)


class TestMediaResolutionSchema:
    """Test media_resolution object schema validation."""

    def test_media_resolution_requires_all_keys(self) -> None:
        """media_resolution must have resolved, unresolved, and ambiguous keys."""
        invalid_metrics = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            "voice_total": 10,
            "voice_status": {"ok": 8, "partial": 1, "failed": 1},
            "media_resolution": {"resolved": 5, "unresolved": 2},  # Missing 'ambiguous'
            "audio_seconds_total": 45.5,
            "asr_cost_total_usd": 0.05,
            "wall_clock_seconds": 120.0,
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)

    def test_media_resolution_no_extra_keys(self) -> None:
        """media_resolution should not allow extra keys."""
        invalid_metrics = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            "voice_total": 10,
            "voice_status": {"ok": 8, "partial": 1, "failed": 1},
            "media_resolution": {
                "resolved": 5,
                "unresolved": 2,
                "ambiguous": 1,
                "extra_key": 10,  # Not allowed
            },
            "audio_seconds_total": 45.5,
            "asr_cost_total_usd": 0.05,
            "wall_clock_seconds": 120.0,
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)


class TestNumericFields:
    """Test numeric field validation."""

    def test_audio_seconds_can_be_float(self) -> None:
        """audio_seconds_total should accept float values."""
        metrics_data = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            "voice_total": 10,
            "voice_status": {"ok": 8, "partial": 1, "failed": 1},
            "media_resolution": {"resolved": 5, "unresolved": 2, "ambiguous": 1},
            "audio_seconds_total": 123.456,  # Float
            "asr_cost_total_usd": 0.123,  # Float
            "wall_clock_seconds": 45.678,  # Float
        }

        # Should not raise
        validate_metrics(metrics_data)

    def test_negative_numeric_values_fail(self) -> None:
        """Numeric fields should not accept negative values."""
        invalid_metrics = {
            "schema_version": METRICS_SCHEMA_VERSION,
            "messages_total": 100,
            "voice_total": 10,
            "voice_status": {"ok": 8, "partial": 1, "failed": 1},
            "media_resolution": {"resolved": 5, "unresolved": 2, "ambiguous": 1},
            "audio_seconds_total": -10.0,  # Negative
            "asr_cost_total_usd": 0.05,
            "wall_clock_seconds": 120.0,
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_metrics(invalid_metrics)
