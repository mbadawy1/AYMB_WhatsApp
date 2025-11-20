"""Pipeline configuration helpers for the orchestrator."""

from __future__ import annotations

import re
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEFAULT_CHAT_FILE = "_chat.txt"


def _slugify(value: str) -> str:
    """Normalize run_id values into deterministic, filesystem-safe slugs."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip())
    slug = slug.strip("-")
    return slug.lower() or "run"


@dataclass
class PipelineConfig:
    """Dataclass capturing all runner inputs and knobs."""

    root: Path
    run_id: Optional[str] = None
    run_dir: Optional[Path] = None
    chat_file: Optional[Path] = None
    max_workers_audio: int = 1
    asr_provider: str = "whisper_openai"
    asr_model: Optional[str] = None
    asr_language: Optional[str] = "auto"
    asr_api_version: Optional[str] = None
    sample_limit: Optional[int] = None
    sample_every: Optional[int] = None
    resume: bool = True

    def __post_init__(self) -> None:
        self.root = Path(self.root).resolve()
        chat = self.chat_file or self.root / DEFAULT_CHAT_FILE
        self.chat_file = Path(chat).resolve()

        self.run_id = _slugify(self.run_id or self.root.name or "run")
        run_dir = self.run_dir or (self.root / "runs" / self.run_id)
        self.run_dir = Path(run_dir).resolve()

        if self.sample_every is not None and self.sample_every <= 0:
            raise ValueError("sample_every must be > 0 when provided")
        if self.sample_limit is not None and self.sample_limit <= 0:
            raise ValueError("sample_limit must be > 0 when provided")
        self.max_workers_audio = max(1, int(self.max_workers_audio or 1))

    @classmethod
    def from_args(cls, args: Namespace) -> "PipelineConfig":
        """Build config from argparse Namespace (scripts/run_pipeline.py)."""
        return cls(
            root=Path(args.root),
            run_id=args.run_id,
            run_dir=Path(args.run_dir) if args.run_dir else None,
            chat_file=Path(args.chat_file) if getattr(args, "chat_file", None) else None,
            max_workers_audio=args.max_workers_audio,
            asr_provider=args.asr_provider,
            asr_model=args.asr_model,
            asr_language=args.asr_language,
            asr_api_version=getattr(args, "asr_api_version", None),
            sample_limit=args.sample_limit,
            sample_every=args.sample_every,
            resume=not getattr(args, "no_resume", False),
        )

    def validate(self) -> None:
        """Fail fast if required inputs are missing."""
        if not self.root.exists():
            raise FileNotFoundError(f"root directory not found: {self.root}")
        if not self.chat_file.exists():
            raise FileNotFoundError(f"chat export not found: {self.chat_file}")

    @property
    def manifest_path(self) -> Path:
        return self.run_dir / "run_manifest.json"

    @property
    def metrics_path(self) -> Path:
        return self.run_dir / "metrics.json"

    @property
    def exceptions_path(self) -> Path:
        return self.run_dir / "exceptions.csv"

    def messages_path(self, stage: str) -> Path:
        """Return run_dir path for a stage's Message JSONL."""
        return self.run_dir / f"messages.{stage}.jsonl"

    @property
    def chat_output_path(self) -> Path:
        return self.run_dir / "chat_with_audio.txt"

    @property
    def preview_path(self) -> Path:
        return self.run_dir / "preview_transcripts.txt"
