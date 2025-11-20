"""Test run_manifest.schema.json validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.pipeline.manifest import (
    MANIFEST_SCHEMA_VERSION,
    RunManifest,
    StepProgress,
    validate_manifest,
)


@pytest.fixture
def repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def manifest_schema_path(repo_root: Path) -> Path:
    """Get path to manifest schema file."""
    return repo_root / "schema" / "run_manifest.schema.json"


@pytest.fixture
def manifest_schema(manifest_schema_path: Path) -> dict:
    """Load manifest schema."""
    return json.loads(manifest_schema_path.read_text(encoding="utf-8"))


class TestManifestSchemaExists:
    """Test that the manifest schema file exists and is valid JSON."""

    def test_schema_file_exists(self, manifest_schema_path: Path) -> None:
        """Schema file should exist."""
        assert manifest_schema_path.exists(), f"Schema not found at {manifest_schema_path}"

    def test_schema_is_valid_json(self, manifest_schema: dict) -> None:
        """Schema should be valid JSON."""
        assert isinstance(manifest_schema, dict)
        assert "$schema" in manifest_schema
        assert manifest_schema["$schema"] == "http://json-schema.org/draft-07/schema#"

    def test_schema_has_required_fields(self, manifest_schema: dict) -> None:
        """Schema should define all required top-level fields."""
        assert "title" in manifest_schema
        assert manifest_schema["title"] == "RunManifest"
        assert "type" in manifest_schema
        assert manifest_schema["type"] == "object"
        assert "required" in manifest_schema
        assert "properties" in manifest_schema


class TestManifestValidation:
    """Test validation of manifest documents against the schema."""

    def test_valid_manifest_passes(self) -> None:
        """A valid manifest should pass schema validation."""
        manifest = RunManifest(
            schema_version=MANIFEST_SCHEMA_VERSION,
            run_id="test-run-001",
            root="/path/to/root",
            chat_file="/path/to/chat.txt",
            run_dir="/path/to/run",
            start_time="2024-11-20T10:00:00Z",
            end_time=None,
            steps={
                "M1_parse": StepProgress(
                    name="M1_parse",
                    status="ok",
                    total=100,
                    done=100,
                )
            },
            summary={
                "messages_total": 100,
                "voice_total": 10,
                "error": None,
            },
        )

        # Should not raise
        validate_manifest(manifest.to_dict())

    def test_missing_required_field_fails(self) -> None:
        """Manifest missing required field should fail validation."""
        invalid_manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "run_id": "test-run-001",
            # missing required fields like root, chat_file, etc.
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_manifest(invalid_manifest)

    def test_invalid_step_status_fails(self) -> None:
        """Manifest with invalid step status should fail validation."""
        invalid_manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "run_id": "test-run-001",
            "root": "/path/to/root",
            "chat_file": "/path/to/chat.txt",
            "run_dir": "/path/to/run",
            "start_time": "2024-11-20T10:00:00Z",
            "end_time": None,
            "steps": {
                "M1_parse": {
                    "name": "M1_parse",
                    "status": "invalid_status",  # Not in enum
                    "total": 100,
                    "done": 100,
                    "error": None,
                    "started_at": None,
                    "ended_at": None,
                }
            },
            "summary": {
                "messages_total": 100,
                "voice_total": 10,
                "error": None,
            },
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_manifest(invalid_manifest)

    def test_negative_counts_fail(self) -> None:
        """Manifest with negative counts should fail validation."""
        invalid_manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "run_id": "test-run-001",
            "root": "/path/to/root",
            "chat_file": "/path/to/chat.txt",
            "run_dir": "/path/to/run",
            "start_time": "2024-11-20T10:00:00Z",
            "end_time": None,
            "steps": {},
            "summary": {
                "messages_total": -1,  # Negative count
                "voice_total": 10,
                "error": None,
            },
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_manifest(invalid_manifest)

    def test_invalid_schema_version_format_fails(self) -> None:
        """Manifest with invalid schema_version format should fail validation."""
        invalid_manifest = {
            "schema_version": "not-semver",  # Invalid semver format
            "run_id": "test-run-001",
            "root": "/path/to/root",
            "chat_file": "/path/to/chat.txt",
            "run_dir": "/path/to/run",
            "start_time": "2024-11-20T10:00:00Z",
            "end_time": None,
            "steps": {},
            "summary": {
                "messages_total": 100,
                "voice_total": 10,
                "error": None,
            },
        }

        with pytest.raises(Exception):  # jsonschema.ValidationError
            validate_manifest(invalid_manifest)


class TestStepProgressSchema:
    """Test StepProgress schema validation."""

    def test_step_progress_validates(self) -> None:
        """Valid StepProgress should pass validation."""
        manifest_data = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "run_id": "test-run-001",
            "root": "/path/to/root",
            "chat_file": "/path/to/chat.txt",
            "run_dir": "/path/to/run",
            "start_time": "2024-11-20T10:00:00Z",
            "end_time": "2024-11-20T10:05:00Z",
            "steps": {
                "M1_parse": {
                    "name": "M1_parse",
                    "status": "ok",
                    "total": 100,
                    "done": 100,
                    "error": None,
                    "started_at": "2024-11-20T10:00:00Z",
                    "ended_at": "2024-11-20T10:02:00Z",
                }
            },
            "summary": {
                "messages_total": 100,
                "voice_total": 10,
                "error": None,
            },
        }

        # Should not raise
        validate_manifest(manifest_data)

    def test_step_with_all_valid_statuses(self) -> None:
        """All valid step statuses should pass validation."""
        valid_statuses = ["pending", "running", "ok", "failed", "skipped"]

        for status in valid_statuses:
            manifest_data = {
                "schema_version": MANIFEST_SCHEMA_VERSION,
                "run_id": "test-run-001",
                "root": "/path/to/root",
                "chat_file": "/path/to/chat.txt",
                "run_dir": "/path/to/run",
                "start_time": "2024-11-20T10:00:00Z",
                "end_time": None,
                "steps": {
                    "M1_parse": {
                        "name": "M1_parse",
                        "status": status,
                        "total": 100,
                        "done": 50,
                        "error": None,
                        "started_at": None,
                        "ended_at": None,
                    }
                },
                "summary": {
                    "messages_total": 100,
                    "voice_total": 10,
                    "error": None,
                },
            }

            # Should not raise
            validate_manifest(manifest_data)
