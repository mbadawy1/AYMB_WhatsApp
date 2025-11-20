"""Tests for src/pipeline/status.py helpers."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.pipeline.status import (
    RunSummary,
    StepStatus,
    list_runs,
    load_run_summary,
    load_transcript_preview,
)


@pytest.fixture
def sample_run(tmp_path: Path) -> Path:
    """Create a sample run directory with manifest and metrics."""
    run_dir = tmp_path / "runs" / "test-run"
    run_dir.mkdir(parents=True)

    # Write manifest
    manifest = {
        "schema_version": "1.0.0",
        "run_id": "test-run",
        "root": str(tmp_path),
        "chat_file": str(tmp_path / "_chat.txt"),
        "run_dir": str(run_dir),
        "start_time": "2025-01-01T10:00:00Z",
        "end_time": "2025-01-01T10:05:00Z",
        "steps": {
            "M1_parse": {
                "name": "M1_parse",
                "status": "ok",
                "total": 100,
                "done": 100,
                "error": None,
                "started_at": "2025-01-01T10:00:00Z",
                "ended_at": "2025-01-01T10:01:00Z",
            },
            "M2_media": {
                "name": "M2_media",
                "status": "ok",
                "total": 100,
                "done": 100,
                "error": None,
                "started_at": "2025-01-01T10:01:00Z",
                "ended_at": "2025-01-01T10:02:00Z",
            },
            "M3_audio": {
                "name": "M3_audio",
                "status": "ok",
                "total": 20,
                "done": 20,
                "error": None,
                "started_at": "2025-01-01T10:02:00Z",
                "ended_at": "2025-01-01T10:04:00Z",
            },
            "M5_text": {
                "name": "M5_text",
                "status": "ok",
                "total": 100,
                "done": 100,
                "error": None,
                "started_at": "2025-01-01T10:04:00Z",
                "ended_at": "2025-01-01T10:05:00Z",
            },
        },
        "summary": {
            "messages_total": 100,
            "voice_total": 20,
            "error": None,
            "resume_enabled": True,
        },
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    # Write metrics
    metrics = {
        "schema_version": "1.0.0",
        "messages_total": 100,
        "voice_total": 20,
        "voice_status": {"ok": 18, "partial": 1, "failed": 1},
        "media_resolution": {"resolved": 50, "unresolved": 50, "ambiguous": 0},
        "audio_seconds_total": 120.5,
        "asr_cost_total_usd": 0.05,
        "wall_clock_seconds": 300.0,
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )

    # Write preview
    preview_lines = [
        "--- Message 1 ---",
        "Sender: Alice",
        "Transcript: Hello world",
        "",
        "--- Message 2 ---",
        "Sender: Bob",
        "Transcript: مرحبا",
    ]
    (run_dir / "preview_transcripts.txt").write_text(
        "\n".join(preview_lines), encoding="utf-8"
    )

    return tmp_path


def test_list_runs_finds_runs(sample_run: Path):
    """list_runs should find runs with manifests."""
    runs = list_runs(str(sample_run))
    assert len(runs) == 1
    assert runs[0].run_id == "test-run"
    assert runs[0].status == "ok"


def test_list_runs_empty_directory(tmp_path: Path):
    """list_runs should return empty list for empty directory."""
    runs = list_runs(str(tmp_path))
    assert runs == []


def test_list_runs_skips_invalid(tmp_path: Path):
    """list_runs should skip directories without valid manifests."""
    # Create run without manifest
    (tmp_path / "runs" / "invalid-run").mkdir(parents=True)

    # Create run with invalid JSON
    bad_run = tmp_path / "runs" / "bad-json"
    bad_run.mkdir(parents=True)
    (bad_run / "run_manifest.json").write_text("not json", encoding="utf-8")

    runs = list_runs(str(tmp_path))
    assert runs == []


def test_load_run_summary_populates_fields(sample_run: Path):
    """load_run_summary should populate all fields correctly."""
    run_dir = sample_run / "runs" / "test-run"
    summary = load_run_summary(str(run_dir))

    assert summary.run_id == "test-run"
    assert summary.status == "ok"
    assert summary.messages_total == 100
    assert summary.voice_total == 20
    assert summary.voice_ok == 18
    assert summary.voice_failed == 1
    assert summary.audio_seconds == 120.5
    assert summary.asr_cost_usd == 0.05
    assert len(summary.steps) == 4
    assert summary.steps[0].name == "M1_parse"
    assert summary.steps[0].status == "ok"


def test_load_run_summary_missing_metrics(tmp_path: Path):
    """load_run_summary should handle missing metrics gracefully."""
    run_dir = tmp_path / "test-run"
    run_dir.mkdir()

    # Minimal manifest
    manifest = {
        "run_id": "minimal",
        "root": str(tmp_path),
        "chat_file": "",
        "run_dir": str(run_dir),
        "steps": {},
        "summary": {},
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    summary = load_run_summary(str(run_dir))
    assert summary.run_id == "minimal"
    assert summary.audio_seconds == 0.0
    assert summary.asr_cost_usd == 0.0


def test_load_run_summary_failed_status(tmp_path: Path):
    """load_run_summary should detect failed status from error."""
    run_dir = tmp_path / "failed-run"
    run_dir.mkdir()

    manifest = {
        "run_id": "failed",
        "root": str(tmp_path),
        "chat_file": "",
        "run_dir": str(run_dir),
        "steps": {
            "M1_parse": {"name": "M1_parse", "status": "failed", "error": "Test error"},
        },
        "summary": {"error": "M1_parse: Test error"},
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    summary = load_run_summary(str(run_dir))
    assert summary.status == "failed"
    assert "Test error" in summary.error


def test_load_transcript_preview_parses_file(sample_run: Path):
    """load_transcript_preview should read and return lines."""
    run_dir = sample_run / "runs" / "test-run"
    lines = load_transcript_preview(str(run_dir))

    assert len(lines) == 7
    assert lines[0] == "--- Message 1 ---"
    assert "مرحبا" in lines[6]  # UTF-8 Arabic


def test_load_transcript_preview_missing_file(tmp_path: Path):
    """load_transcript_preview should return empty list for missing file."""
    lines = load_transcript_preview(str(tmp_path))
    assert lines == []


def test_load_transcript_preview_empty_file(tmp_path: Path):
    """load_transcript_preview should handle empty file."""
    (tmp_path / "preview_transcripts.txt").write_text("", encoding="utf-8")
    lines = load_transcript_preview(str(tmp_path))
    assert lines == []  # Empty string splitlines returns empty list


def test_step_status_dataclass():
    """StepStatus should be a valid dataclass."""
    step = StepStatus(
        name="M1_parse",
        status="ok",
        total=100,
        done=100,
    )
    assert step.name == "M1_parse"
    assert step.error is None


def test_run_summary_dataclass():
    """RunSummary should be a valid dataclass with defaults."""
    summary = RunSummary(
        run_id="test",
        run_dir="/tmp/test",
        root="/tmp",
        chat_file="/tmp/_chat.txt",
        status="pending",
    )
    assert summary.messages_total == 0
    assert summary.steps == []
