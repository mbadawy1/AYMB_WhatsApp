"""Helpers to materialize run_dir outputs for M6 contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from src.schema.message import Message
from src.pipeline.outputs import write_messages_jsonl
from src.pipeline.validation import validate_jsonl
from src.pipeline.manifest import build_manifest, write_manifest
from src.pipeline.metrics import compute_metrics, write_metrics
from src.writers.text_renderer import (
    TextRenderOptions,
    render_messages_to_txt,
    write_transcript_preview,
)


def materialize_run(
    run_id: str,
    run_dir: Path,
    messages_m1: Iterable[Message],
    messages_m2: Iterable[Message],
    messages_m3: Iterable[Message],
    *,
    render_text: bool = True,
    render_preview: bool = True,
    preview_max_chars: int = 120,
    text_options: Optional[TextRenderOptions] = None,
) -> dict:
    """Write standardized outputs (messages/chat/preview/manifest/metrics) to run_dir."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    messages_m1 = list(messages_m1)
    messages_m2 = list(messages_m2)
    messages_m3 = list(messages_m3)

    m1_path = run_dir / "messages.M1.jsonl"
    m2_path = run_dir / "messages.M2.jsonl"
    m3_path = run_dir / "messages.M3.jsonl"
    chat_path = run_dir / "chat_with_audio.txt"
    preview_path = run_dir / "preview_transcripts.txt"
    manifest_path = run_dir / "run_manifest.json"
    metrics_path = run_dir / "metrics.json"

    write_messages_jsonl(messages_m1, m1_path)
    write_messages_jsonl(messages_m2, m2_path)
    write_messages_jsonl(messages_m3, m3_path)

    validate_jsonl(m1_path)
    validate_jsonl(m2_path)
    validate_jsonl(m3_path)

    if render_text:
        render_messages_to_txt(messages_m3, chat_path, text_options)
    else:
        chat_path = None

    preview_count = 0
    if render_preview:
        preview_count = write_transcript_preview(messages_m3, preview_path, max_chars=preview_max_chars)
    else:
        preview_path = None

    inputs = {
        "messages_m1": str(m1_path),
        "messages_m2": str(m2_path),
        "messages_m3": str(m3_path),
    }
    outputs = {
        "chat_with_audio": str(chat_path) if chat_path else None,
        "preview_transcripts": str(preview_path) if preview_path else None,
        "manifest": str(manifest_path),
        "metrics": str(metrics_path),
    }

    manifest = build_manifest(run_id, messages_m1, messages_m2, messages_m3, inputs=inputs, outputs=outputs)
    write_manifest(manifest, manifest_path)

    metrics = compute_metrics(messages_m3)
    write_metrics(metrics, metrics_path)

    return {
        "manifest_path": manifest_path,
        "metrics_path": metrics_path,
        "preview_count": preview_count,
        "outputs": outputs,
    }
