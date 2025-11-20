"""Pipeline runners for contract materialization and M6 orchestration."""

from __future__ import annotations

import concurrent.futures
import contextlib
import copy
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

from src.audio_transcriber import AudioConfig, AudioTranscriber
from src.media_resolver import MediaResolver
from src.parser_agent import ParserAgent
from src.pipeline.config import PipelineConfig
from src.pipeline.manifest import (
    RunManifest,
    finalize_manifest,
    init_manifest,
    load_manifest,
    set_summary,
    update_step,
    write_manifest,
)
from src.pipeline.materialize import materialize_run
from src.pipeline.metrics import RunMetrics, write_metrics
from src.pipeline.outputs import load_messages, write_messages_jsonl
from src.pipeline.validation import validate_jsonl
from src.schema.message import Message
from src.writers.text_renderer import render_messages_to_txt, write_transcript_preview

# ---------------------------------------------------------------------------
# Helpers


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clone_messages(messages: Iterable[Message]) -> List[Message]:
    clones: List[Message] = []
    for msg in messages:
        if hasattr(msg, "model_copy"):
            clones.append(msg.model_copy(deep=True))
        else:
            clones.append(Message(**msg.dict()))  # type: ignore[attr-defined]
    return clones


@contextlib.contextmanager
def _pushd(path: Path):
    prev = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(prev)


def _write_manifest(manifest: RunManifest, cfg: PipelineConfig) -> None:
    write_manifest(manifest, cfg.manifest_path)


def _begin_step(manifest: RunManifest, cfg: PipelineConfig, step: str, *, total: int, done: int = 0) -> None:
    update_step(manifest, step, status="running", total=total, done=done, started_at=_iso_now(), error=None)
    _write_manifest(manifest, cfg)


def _complete_step(manifest: RunManifest, cfg: PipelineConfig, step: str, *, total: int, done: int) -> None:
    update_step(manifest, step, status="ok", total=total, done=done, ended_at=_iso_now())
    _write_manifest(manifest, cfg)


def _fail_step(manifest: RunManifest, cfg: PipelineConfig, step: str, exc: Exception) -> None:
    update_step(manifest, step, status="failed", error=str(exc), ended_at=_iso_now())
    manifest.summary["error"] = f"{step}: {exc}"
    _write_manifest(manifest, cfg)


def _can_resume(cfg: PipelineConfig, manifest: RunManifest, step: str, required: List[Path]) -> bool:
    if not cfg.resume:
        return False
    step_state = manifest.steps.get(step)
    if not step_state or step_state.status != "ok":
        return False
    return all(path.exists() for path in required)


def _apply_sampling(messages: List[Message], cfg: PipelineConfig) -> List[Message]:
    sampled = list(messages)
    if cfg.sample_every:
        sampled = sampled[:: cfg.sample_every]
    if cfg.sample_limit:
        sampled = sampled[: cfg.sample_limit]
    for new_idx, msg in enumerate(sampled):
        msg.idx = new_idx
    return sampled


def _copy_voice_state(target: Message, cached: Message) -> None:
    target.content_text = cached.content_text
    target.status = cached.status
    target.partial = cached.partial
    target.status_reason = cached.status_reason
    target.errors = list(cached.errors)
    target.derived = copy.deepcopy(cached.derived)


def _reuse_voice_message(
    msg: Message,
    cached: Message,
    *,
    provider: str,
    model: Optional[str],
    pipeline_version: str,
) -> bool:
    payload = cached.derived.get("asr") if isinstance(cached.derived, dict) else None
    if not payload:
        return False
    if payload.get("pipeline_version") != pipeline_version:
        return False
    if payload.get("provider") != provider:
        return False
    if payload.get("model") != model:
        return False
    _copy_voice_state(msg, cached)
    return True


def _load_if_exists(path: Path) -> Optional[List[Message]]:
    return load_messages(path) if path.exists() else None


# ---------------------------------------------------------------------------
# M6.1 pipeline runner


def run_pipeline(cfg: PipelineConfig) -> Dict[str, str]:
    """Run M1->M2->M3->M5 pipeline with resume + concurrency semantics."""
    cfg.validate()
    cfg.run_dir.mkdir(parents=True, exist_ok=True)

    if cfg.resume and cfg.manifest_path.exists():
        manifest = load_manifest(cfg.manifest_path)
    else:
        manifest = init_manifest(cfg)
    _write_manifest(manifest, cfg)

    metrics = RunMetrics()
    run_start = time.perf_counter()

    messages_m1 = _run_m1(cfg, manifest)
    messages_m2 = _run_m2(cfg, manifest, messages_m1)
    messages_m3 = _run_m3(cfg, manifest, messages_m2)
    preview_count = _run_m5(cfg, manifest, messages_m3)

    metrics.record_messages(messages_m3)
    metrics.record_media_resolution(messages_m2)
    metrics.record_audio(messages_m3)
    metrics.wall_clock_seconds = round(time.perf_counter() - run_start, 3)

    set_summary(
        manifest,
        messages_total=len(messages_m3),
        voice_total=metrics.voice_total,
        error=manifest.summary.get("error"),
    )
    finalize_manifest(manifest)
    _write_manifest(manifest, cfg)

    write_metrics(metrics, cfg.metrics_path)

    outputs = {
        "messages_m1": str(cfg.messages_path("M1")),
        "messages_m2": str(cfg.messages_path("M2")),
        "messages_m3": str(cfg.messages_path("M3")),
        "chat_with_audio": str(cfg.chat_output_path),
        "preview_transcripts": str(cfg.preview_path),
        "manifest": str(cfg.manifest_path),
        "metrics": str(cfg.metrics_path),
    }

    return {
        "run_id": cfg.run_id,
        "run_dir": str(cfg.run_dir),
        "manifest_path": str(cfg.manifest_path),
        "metrics_path": str(cfg.metrics_path),
        "preview_count": preview_count,
        "outputs": outputs,
    }


def _run_m1(cfg: PipelineConfig, manifest: RunManifest) -> List[Message]:
    step = "M1_parse"
    path = cfg.messages_path("M1")
    required = [path]
    if _can_resume(cfg, manifest, step, required):
        messages = load_messages(path)
        update_step(manifest, step, total=len(messages), done=len(messages))
        _write_manifest(manifest, cfg)
        return messages

    try:
        parser = ParserAgent(str(cfg.root), chat_file=str(cfg.chat_file) if cfg.chat_file else None)
        _begin_step(manifest, cfg, step, total=0)
        messages = parser.parse()
        messages = _apply_sampling(messages, cfg)
        write_messages_jsonl(messages, path)
        validate_jsonl(path)
        _complete_step(manifest, cfg, step, total=len(messages), done=len(messages))
        return messages
    except Exception as exc:  # pragma: no cover - safety net
        _fail_step(manifest, cfg, step, exc)
        raise


def _run_m2(cfg: PipelineConfig, manifest: RunManifest, messages_m1: List[Message]) -> List[Message]:
    step = "M2_media"
    path = cfg.messages_path("M2")
    required = [path]
    if _can_resume(cfg, manifest, step, required):
        messages = load_messages(path)
        update_step(manifest, step, total=len(messages), done=len(messages))
        _write_manifest(manifest, cfg)
        return messages

    try:
        msgs = _clone_messages(messages_m1)
        _begin_step(manifest, cfg, step, total=len(msgs))
        resolver = MediaResolver(cfg.root)
        with _pushd(cfg.run_dir):
            resolver.map_media(msgs)
        write_messages_jsonl(msgs, path)
        validate_jsonl(path)
        _complete_step(manifest, cfg, step, total=len(msgs), done=len(msgs))
        return msgs
    except Exception as exc:  # pragma: no cover - safety net
        _fail_step(manifest, cfg, step, exc)
        raise


def _run_m3(cfg: PipelineConfig, manifest: RunManifest, messages_m2: List[Message]) -> List[Message]:
    step = "M3_audio"
    path = cfg.messages_path("M3")
    required = [path]
    if _can_resume(cfg, manifest, step, required):
        messages = load_messages(path)
        update_step(
            manifest,
            step,
            total=sum(1 for m in messages if m.kind == "voice"),
            done=sum(1 for m in messages if m.kind == "voice"),
        )
        _write_manifest(manifest, cfg)
        return messages

    try:
        messages = _clone_messages(messages_m2)
        existing = _load_if_exists(path) if cfg.resume else None
        existing_map = {msg.idx: msg for msg in existing or []}

        voice_count = sum(1 for msg in messages if msg.kind == "voice")
        _begin_step(manifest, cfg, step, total=voice_count, done=0)

        audio_cfg = AudioConfig(
            asr_provider=cfg.asr_provider,
            asr_model=cfg.asr_model,
            asr_language=cfg.asr_language,
            asr_api_version=cfg.asr_api_version,
        )
        transcriber = AudioTranscriber(audio_cfg)

        done = 0
        to_process: List[Message] = []
        for msg in messages:
            if msg.kind != "voice":
                continue
            cached = existing_map.get(msg.idx)
            if cached and _reuse_voice_message(
                msg,
                cached,
                provider=audio_cfg.asr_provider,
                model=audio_cfg.asr_model,
                pipeline_version=transcriber.pipeline_version,
            ):
                done += 1
                continue
            to_process.append(msg)

        if done:
            update_step(manifest, step, done=done)
            _write_manifest(manifest, cfg)

        def _mark_progress() -> None:
            nonlocal done
            done += 1
            update_step(manifest, step, done=done)
            _write_manifest(manifest, cfg)

        if to_process:
            if cfg.max_workers_audio <= 1:
                for msg in to_process:
                    transcriber.transcribe(msg)
                    _mark_progress()
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.max_workers_audio) as pool:
                    futures = [pool.submit(transcriber.transcribe, msg) for msg in to_process]
                    for future in concurrent.futures.as_completed(futures):
                        future.result()
                        _mark_progress()

        write_messages_jsonl(messages, path)
        validate_jsonl(path)
        _complete_step(manifest, cfg, step, total=voice_count, done=voice_count)
        return messages
    except Exception as exc:  # pragma: no cover - safety net
        _fail_step(manifest, cfg, step, exc)
        raise


def _run_m5(cfg: PipelineConfig, manifest: RunManifest, messages_m3: List[Message]) -> int:
    step = "M5_text"
    chat_path = cfg.chat_output_path
    required = [chat_path]
    if _can_resume(cfg, manifest, step, required):
        update_step(manifest, step, total=len(messages_m3), done=len(messages_m3))
        _write_manifest(manifest, cfg)
        return sum(1 for m in messages_m3 if m.kind == "voice")

    try:
        _begin_step(manifest, cfg, step, total=len(messages_m3))
        render_messages_to_txt(messages_m3, chat_path)
        preview_count = write_transcript_preview(messages_m3, cfg.preview_path)
        _complete_step(manifest, cfg, step, total=len(messages_m3), done=len(messages_m3))
        return preview_count
    except Exception as exc:  # pragma: no cover - safety net
        _fail_step(manifest, cfg, step, exc)
        raise


# ---------------------------------------------------------------------------
# Contract hardening pipeline (M6C.x compatibility)


def run_contract_pipeline(root: Path, run_dir: Path, run_id: str) -> dict:
    """Run Parser→Resolver→Audio pipeline and materialize outputs (M6C)."""
    parser = ParserAgent(str(root))
    messages_m1 = parser.parse()

    messages_m2 = _clone_messages(messages_m1)
    resolver = MediaResolver(root)
    resolver.map_media(messages_m2)

    messages_m3 = _clone_messages(messages_m2)
    transcriber = AudioTranscriber()
    for msg in messages_m3:
        transcriber.transcribe(msg)

    return materialize_run(run_id, run_dir, messages_m1, messages_m2, messages_m3)
