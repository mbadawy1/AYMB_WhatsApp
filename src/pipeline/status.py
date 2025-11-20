"""Status helpers for the Streamlit UI."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class StepStatus:
    """Status of a single pipeline step."""

    name: str
    status: str  # "pending" | "running" | "ok" | "failed"
    total: int = 0
    done: int = 0
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None


@dataclass
class RunSummary:
    """Summary of a pipeline run for UI display."""

    run_id: str
    run_dir: str
    root: str
    chat_file: str
    status: str  # "pending" | "running" | "ok" | "failed"
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    messages_total: int = 0
    voice_total: int = 0
    voice_ok: int = 0
    voice_failed: int = 0
    audio_seconds: float = 0.0
    asr_cost_usd: float = 0.0
    error: Optional[str] = None
    steps: List[StepStatus] = field(default_factory=list)


def list_runs(root: str) -> List[RunSummary]:
    """Find all runs under root and return summaries.

    Looks for directories matching 'runs/*' pattern with run_manifest.json.

    Args:
        root: Base directory to search for runs

    Returns:
        List of RunSummary objects, sorted by start_time (newest first)
    """
    root_path = Path(root)
    runs_dir = root_path / "runs" if (root_path / "runs").is_dir() else root_path

    summaries: List[RunSummary] = []

    # Find all directories with run_manifest.json
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.exists():
            continue

        try:
            summary = load_run_summary(str(run_dir))
            summaries.append(summary)
        except Exception:
            # Skip invalid runs but don't crash
            continue

    # Sort by start_time (newest first), handling None
    summaries.sort(
        key=lambda s: s.start_time or "",
        reverse=True
    )

    return summaries


def load_run_summary(run_dir: str) -> RunSummary:
    """Load a single run's manifest and metrics into a summary.

    Args:
        run_dir: Path to the run directory

    Returns:
        RunSummary populated from manifest and metrics files

    Raises:
        FileNotFoundError: If run_manifest.json is missing
        json.JSONDecodeError: If manifest is invalid JSON
    """
    run_path = Path(run_dir)
    manifest_path = run_path / "run_manifest.json"
    metrics_path = run_path / "metrics.json"

    # Load manifest (required)
    with manifest_path.open("r", encoding="utf-8") as f:
        manifest: Dict[str, Any] = json.load(f)

    # Load metrics (optional)
    metrics: Dict[str, Any] = {}
    if metrics_path.exists():
        try:
            with metrics_path.open("r", encoding="utf-8") as f:
                metrics = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass  # Use empty metrics if invalid

    # Determine overall status from steps
    steps_data = manifest.get("steps", {})
    status = _determine_status(steps_data, manifest.get("summary", {}))

    # Build step list
    steps: List[StepStatus] = []
    for step_name in ["M1_parse", "M2_media", "M3_audio", "M5_text"]:
        step_data = steps_data.get(step_name, {})
        steps.append(StepStatus(
            name=step_data.get("name", step_name),
            status=step_data.get("status", "pending"),
            total=step_data.get("total", 0),
            done=step_data.get("done", 0),
            error=step_data.get("error"),
            started_at=step_data.get("started_at"),
            ended_at=step_data.get("ended_at"),
        ))

    # Extract voice status from metrics
    voice_status = metrics.get("voice_status", {})

    return RunSummary(
        run_id=manifest.get("run_id", run_path.name),
        run_dir=str(run_path),
        root=manifest.get("root", ""),
        chat_file=manifest.get("chat_file", ""),
        status=status,
        start_time=manifest.get("start_time"),
        end_time=manifest.get("end_time"),
        messages_total=manifest.get("summary", {}).get("messages_total", 0),
        voice_total=manifest.get("summary", {}).get("voice_total", 0),
        voice_ok=voice_status.get("ok", 0),
        voice_failed=voice_status.get("failed", 0),
        audio_seconds=metrics.get("audio_seconds_total", 0.0),
        asr_cost_usd=metrics.get("asr_cost_total_usd", 0.0),
        error=manifest.get("summary", {}).get("error"),
        steps=steps,
    )


def load_transcript_preview(run_dir: str) -> List[str]:
    """Load transcript preview lines from a run.

    Args:
        run_dir: Path to the run directory

    Returns:
        List of transcript lines, or empty list if file missing/invalid
    """
    preview_path = Path(run_dir) / "preview_transcripts.txt"

    if not preview_path.exists():
        return []

    try:
        text = preview_path.read_text(encoding="utf-8")
        return text.splitlines()
    except (IOError, UnicodeDecodeError):
        return []


def _determine_status(steps: Dict[str, Any], summary: Dict[str, Any]) -> str:
    """Determine overall run status from step statuses.

    Returns:
        "ok" if all steps completed, "failed" if any failed,
        "running" if any in progress, "pending" otherwise
    """
    if summary.get("error"):
        return "failed"

    statuses = [step.get("status", "pending") for step in steps.values()]

    if any(s == "failed" for s in statuses):
        return "failed"
    if any(s == "running" for s in statuses):
        return "running"
    if all(s == "ok" for s in statuses) and statuses:
        return "ok"

    return "pending"
