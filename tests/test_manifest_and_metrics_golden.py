"""Golden tests for manifest and metrics against known fixture outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.pipeline.config import PipelineConfig
from src.pipeline.runner import run_pipeline
from src.pipeline.manifest import load_manifest, validate_manifest
from src.pipeline.metrics import validate_metrics


@pytest.fixture
def repo_root() -> Path:
    """Get repository root directory."""
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_dir(repo_root: Path) -> Path:
    """Get pipeline_small_chat fixture directory."""
    return repo_root / "tests" / "fixtures" / "pipeline_small_chat"


@pytest.fixture
def expected_manifest_path(fixture_dir: Path) -> Path:
    """Path to expected manifest golden file."""
    return fixture_dir / "expected_run_manifest.json"


@pytest.fixture
def expected_metrics_path(fixture_dir: Path) -> Path:
    """Path to expected metrics golden file."""
    return fixture_dir / "expected_metrics.json"


def normalize_manifest(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize volatile fields in manifest for comparison.

    Removes or normalizes fields that change between runs:
    - Timestamps (start_time, end_time, started_at, ended_at)
    - run_id (contains timestamp)
    - run_dir (contains run_id)
    """
    normalized = data.copy()

    # Normalize top-level volatile fields
    if "run_id" in normalized:
        normalized["run_id"] = "NORMALIZED"
    if "run_dir" in normalized:
        normalized["run_dir"] = "NORMALIZED"
    if "start_time" in normalized:
        normalized["start_time"] = "2024-01-01T00:00:00Z"
    if "end_time" in normalized and normalized["end_time"]:
        normalized["end_time"] = "2024-01-01T00:01:00Z"

    # Normalize step timestamps
    if "steps" in normalized:
        for step_name, step_data in normalized["steps"].items():
            if isinstance(step_data, dict):
                if "started_at" in step_data and step_data["started_at"]:
                    step_data["started_at"] = "2024-01-01T00:00:00Z"
                if "ended_at" in step_data and step_data["ended_at"]:
                    step_data["ended_at"] = "2024-01-01T00:01:00Z"

    return normalized


def normalize_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize volatile fields in metrics for comparison.

    Removes or normalizes fields that change between runs:
    - wall_clock_seconds (execution time varies)
    """
    normalized = data.copy()

    # Normalize wall clock time (varies between runs)
    if "wall_clock_seconds" in normalized:
        normalized["wall_clock_seconds"] = 0.0

    return normalized


class TestManifestGolden:
    """Test manifest against golden fixture."""

    def test_golden_manifest_exists(self, expected_manifest_path: Path) -> None:
        """Golden manifest file should exist."""
        assert expected_manifest_path.exists(), (
            f"Golden manifest not found at {expected_manifest_path}. "
            "Run the pipeline on pipeline_small_chat fixture to generate it."
        )

    def test_golden_manifest_validates(self, expected_manifest_path: Path) -> None:
        """Golden manifest should pass schema validation."""
        golden_data = json.loads(expected_manifest_path.read_text(encoding="utf-8"))

        # Should not raise
        validate_manifest(golden_data)

    def test_golden_manifest_has_required_structure(self, expected_manifest_path: Path) -> None:
        """Golden manifest should have expected structure."""
        golden_data = json.loads(expected_manifest_path.read_text(encoding="utf-8"))

        # Check required top-level fields
        assert "schema_version" in golden_data
        assert "run_id" in golden_data
        assert "steps" in golden_data
        assert "summary" in golden_data

        # Check summary fields
        assert "messages_total" in golden_data["summary"]
        assert "voice_total" in golden_data["summary"]
        assert golden_data["summary"]["messages_total"] > 0  # Fixture should have messages

    @pytest.mark.slow
    @pytest.mark.integration
    def test_pipeline_output_matches_golden_manifest(
        self, fixture_dir: Path, expected_manifest_path: Path, tmp_path: Path
    ) -> None:
        """Run pipeline and compare manifest to golden (ignoring volatile fields)."""
        # Skip if golden doesn't exist yet
        if not expected_manifest_path.exists():
            pytest.skip("Golden manifest not yet generated")

        # Run pipeline on fixture
        cfg = PipelineConfig(
            root=fixture_dir,
            chat_file=fixture_dir / "_chat.txt",
            output_dir=tmp_path,
            sample_limit=10,  # Small sample for faster test
            resume=False,
        )

        run_pipeline(cfg)

        # Load actual manifest
        actual_manifest_path = cfg.run_dir / "run_manifest.json"
        assert actual_manifest_path.exists(), "Pipeline should create manifest"

        actual_data = json.loads(actual_manifest_path.read_text(encoding="utf-8"))
        golden_data = json.loads(expected_manifest_path.read_text(encoding="utf-8"))

        # Normalize both
        actual_normalized = normalize_manifest(actual_data)
        golden_normalized = normalize_manifest(golden_data)

        # Compare structure (not exact values due to normalization)
        assert actual_normalized["schema_version"] == golden_normalized["schema_version"]
        assert set(actual_normalized["steps"].keys()) == set(golden_normalized["steps"].keys())


class TestMetricsGolden:
    """Test metrics against golden fixture."""

    def test_golden_metrics_exists(self, expected_metrics_path: Path) -> None:
        """Golden metrics file should exist."""
        assert expected_metrics_path.exists(), (
            f"Golden metrics not found at {expected_metrics_path}. "
            "Run the pipeline on pipeline_small_chat fixture to generate it."
        )

    def test_golden_metrics_validates(self, expected_metrics_path: Path) -> None:
        """Golden metrics should pass schema validation."""
        golden_data = json.loads(expected_metrics_path.read_text(encoding="utf-8"))

        # Should not raise
        validate_metrics(golden_data)

    def test_golden_metrics_has_required_structure(self, expected_metrics_path: Path) -> None:
        """Golden metrics should have expected structure."""
        golden_data = json.loads(expected_metrics_path.read_text(encoding="utf-8"))

        # Check required fields
        assert "schema_version" in golden_data
        assert "messages_total" in golden_data
        assert "voice_total" in golden_data
        assert "voice_status" in golden_data
        assert "media_resolution" in golden_data

        # Check nested structures
        assert "ok" in golden_data["voice_status"]
        assert "partial" in golden_data["voice_status"]
        assert "failed" in golden_data["voice_status"]

        assert "resolved" in golden_data["media_resolution"]
        assert "unresolved" in golden_data["media_resolution"]
        assert "ambiguous" in golden_data["media_resolution"]

    @pytest.mark.slow
    @pytest.mark.integration
    def test_pipeline_output_matches_golden_metrics(
        self, fixture_dir: Path, expected_metrics_path: Path, tmp_path: Path
    ) -> None:
        """Run pipeline and compare metrics to golden (ignoring volatile fields)."""
        # Skip if golden doesn't exist yet
        if not expected_metrics_path.exists():
            pytest.skip("Golden metrics not yet generated")

        # Run pipeline on fixture
        cfg = PipelineConfig(
            root=fixture_dir,
            chat_file=fixture_dir / "_chat.txt",
            output_dir=tmp_path,
            sample_limit=10,  # Small sample for faster test
            resume=False,
        )

        run_pipeline(cfg)

        # Load actual metrics
        actual_metrics_path = cfg.run_dir / "metrics.json"
        assert actual_metrics_path.exists(), "Pipeline should create metrics"

        actual_data = json.loads(actual_metrics_path.read_text(encoding="utf-8"))
        golden_data = json.loads(expected_metrics_path.read_text(encoding="utf-8"))

        # Normalize both
        actual_normalized = normalize_metrics(actual_data)
        golden_normalized = normalize_metrics(golden_data)

        # Compare structure
        assert actual_normalized["schema_version"] == golden_normalized["schema_version"]
        assert actual_normalized["messages_total"] == golden_normalized["messages_total"]
        assert actual_normalized["voice_total"] == golden_normalized["voice_total"]
