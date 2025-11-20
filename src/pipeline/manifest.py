"""Run manifest schema + helpers for the pipeline orchestrator."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional

try:
    import jsonschema
    _JSONSCHEMA_AVAILABLE = True
except ImportError:
    _JSONSCHEMA_AVAILABLE = False

from src.schema.message import Message

MANIFEST_SCHEMA_VERSION = "1.0.0"
DEFAULT_STEPS: tuple[str, ...] = ("M1_parse", "M2_media", "M3_audio", "M5_text")
VALID_STATUSES = {"pending", "running", "ok", "failed", "skipped"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class StepProgress:
    """Progress record for a pipeline step."""

    name: str
    status: str = "pending"
    total: int = 0
    done: int = 0
    error: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status,
            "total": self.total,
            "done": self.done,
            "error": self.error,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "StepProgress":
        return cls(
            name=data["name"],
            status=data.get("status", "pending"),
            total=int(data.get("total", 0)),
            done=int(data.get("done", 0)),
            error=data.get("error"),
            started_at=data.get("started_at"),
            ended_at=data.get("ended_at"),
        )


@dataclass
class RunManifest:
    """Structured run manifest shared between runner/CLI/UI."""

    schema_version: str
    run_id: str
    root: str
    chat_file: str
    run_dir: str
    start_time: str
    end_time: Optional[str]
    steps: Dict[str, StepProgress] = field(default_factory=dict)
    summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "root": self.root,
            "chat_file": self.chat_file,
            "run_dir": self.run_dir,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "steps": {name: step.to_dict() for name, step in self.steps.items()},
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "RunManifest":
        steps_dict = {
            name: StepProgress.from_dict(step_data)
            for name, step_data in (data.get("steps") or {}).items()
        }
        return cls(
            schema_version=data.get("schema_version", MANIFEST_SCHEMA_VERSION),
            run_id=data["run_id"],
            root=data.get("root", ""),
            chat_file=data.get("chat_file", ""),
            run_dir=data.get("run_dir", ""),
            start_time=data.get("start_time", _now_iso()),
            end_time=data.get("end_time"),
            steps=steps_dict,
            summary=dict(data.get("summary", {})),
        )


def init_manifest(cfg, *, steps: Iterable[str] = DEFAULT_STEPS) -> RunManifest:
    """Create an initial manifest with all steps pending."""
    manifest = RunManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        run_id=cfg.run_id,
        root=str(cfg.root),
        chat_file=str(cfg.chat_file),
        run_dir=str(cfg.run_dir),
        start_time=_now_iso(),
        end_time=None,
        steps={name: StepProgress(name=name) for name in steps},
        summary={
            "messages_total": 0,
            "voice_total": 0,
            "error": None,
            "resume_enabled": cfg.resume,
        },
    )
    return manifest


def load_manifest(path: Path) -> RunManifest:
    """Load manifest.json from disk."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return RunManifest.from_dict(data)


def write_manifest(manifest: RunManifest, path: Path) -> None:
    """Persist manifest to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def update_step(manifest: RunManifest, step_name: str, **fields: Any) -> None:
    """Update a single step entry in the manifest."""
    if step_name not in manifest.steps:
        manifest.steps[step_name] = StepProgress(name=step_name)
    step = manifest.steps[step_name]
    for key, value in fields.items():
        if key == "status" and value not in VALID_STATUSES:
            raise ValueError(f"invalid step status {value}")
        setattr(step, key, value)
    manifest.steps[step_name] = step


def finalize_manifest(manifest: RunManifest) -> None:
    """Mark manifest end_time."""
    manifest.end_time = _now_iso()


def set_summary(manifest: RunManifest, *, messages_total: int, voice_total: int, error: Optional[str] = None) -> None:
    """Update manifest summary block."""
    manifest.summary.update(
        {
            "messages_total": messages_total,
            "voice_total": voice_total,
            "error": error,
        }
    )


def build_manifest(
    run_id: str,
    messages_m1: Iterable[Message],
    messages_m2: Iterable[Message],
    messages_m3: Iterable[Message],
    inputs: Dict[str, str],
    outputs: Dict[str, Optional[str]],
    *,
    root: str = "",
    chat_file: str = "",
) -> RunManifest:
    """Compatibility helper for contract materialization."""
    messages_m1 = list(messages_m1)
    messages_m2 = list(messages_m2)
    messages_m3 = list(messages_m3)

    manifest = RunManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        run_id=run_id,
        root=root,
        chat_file=chat_file,
        run_dir=str(Path(outputs.get("manifest") or "").parent),
        start_time=_now_iso(),
        end_time=_now_iso(),
        steps={
            name: StepProgress(name=name, status="ok", total=len(messages_m3), done=len(messages_m3))
            for name in DEFAULT_STEPS
        },
        summary={
            "messages_total": len(messages_m3),
            "voice_total": sum(1 for m in messages_m3 if m.kind == "voice"),
            "error": None,
            "inputs": inputs,
            "outputs": outputs,
        },
    )
    return manifest


def _get_manifest_schema() -> dict[str, Any]:
    """Load the manifest JSON schema from disk."""
    schema_path = Path(__file__).resolve().parents[2] / "schema" / "run_manifest.schema.json"
    if not schema_path.exists():
        raise FileNotFoundError(f"Manifest schema not found at {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_manifest(data: dict[str, Any]) -> None:
    """Validate a manifest dict against the JSON schema.

    Args:
        data: Manifest dictionary to validate

    Raises:
        jsonschema.ValidationError: If validation fails
        ImportError: If jsonschema is not installed
        FileNotFoundError: If schema file is missing
    """
    if not _JSONSCHEMA_AVAILABLE:
        raise ImportError(
            "jsonschema is required for validation. "
            "Install with: pip install jsonschema"
        )

    schema = _get_manifest_schema()
    jsonschema.validate(data, schema)
