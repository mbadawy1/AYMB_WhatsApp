"""Audio transcription pipeline (M3)."""

from __future__ import annotations

import json
import math
import wave
from dataclasses import asdict, dataclass
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from src.utils.asr import AsrClient, map_asr_error_to_status_reason
from src.utils.cost import estimate_asr_cost
from src.utils.hashing import sha256_file
from src.utils.vad import run_vad
from src.schema.message import Message, StatusReason


class ChunkingError(Exception):
    """Raised when audio chunking fails due to invalid or degenerate audio."""
    pass


@dataclass
class AudioConfig:
    ffmpeg_bin: str = "ffmpeg"
    sample_rate: int = 16000
    channels: int = 1
    chunk_seconds: float = 120.0
    chunk_overlap_seconds: float = 0.25
    vad_min_speech_ratio: float = 0.05
    vad_min_speech_seconds: float = 0.1
    asr_provider: str = "whisper_openai"
    asr_model: Optional[str] = None
    asr_language: Optional[str] = None
    asr_api_version: Optional[str] = None
    asr_timeout_seconds: int = 60
    asr_max_retries: int = 2
    ffmpeg_max_retries: int = 2
    ffmpeg_timeout_seconds: int = 30
    enable_vad: bool = True
    cache_dir: Path = Path("cache/audio")
    asr_billing_plan: str = "per_minute"
    chunk_dir: Optional[Path] = None


class AudioTranscriber:
    """Transcribe WhatsApp voice messages."""

    pipeline_version = "m3.10"

    def __init__(self, cfg: Optional[AudioConfig] = None) -> None:
        self.cfg = cfg or AudioConfig()
        self.asr_client = AsrClient(self.cfg)

    def transcribe(self, m: Message) -> None:
        """Populate derived ASR metadata for voice messages."""
        if m.kind != "voice":
            return
        asr_info = m.derived.get("asr") or {}
        asr_info.update(
            {
                "pipeline_version": self.pipeline_version,
                "config_snapshot": asdict(self.cfg),
            }
        )
        if hasattr(self, "asr_client"):
            asr_info["language_hint"] = getattr(self.asr_client, "language_hint", self.cfg.asr_language or "auto")
        m.derived["asr"] = asr_info

        if not m.media_filename:
            m.status = "failed"
            m.status_reason = StatusReason.from_code("audio_unsupported_format")
            if not m.content_text:
                m.content_text = "[UNSUPPORTED AUDIO FORMAT]"
            return

        cache_payload = self._load_cache(m)
        if cache_payload:
            self._apply_cache(m, cache_payload)
            return

        wav_path = self._to_wav(m)
        if wav_path is None:
            return

        total_seconds = self._wav_duration_seconds(wav_path)

        if self.cfg.enable_vad:
            vad_stats = run_vad(wav_path, self.cfg)
            asr_info["vad"] = {
                "speech_ratio": vad_stats.speech_ratio,
                "speech_seconds": vad_stats.speech_seconds,
                "total_seconds": vad_stats.total_seconds,
                "segments": vad_stats.segments,
                "is_mostly_silence": (
                    vad_stats.speech_ratio < self.cfg.vad_min_speech_ratio
                    or vad_stats.speech_seconds < self.cfg.vad_min_speech_seconds
                ),
            }
            m.derived["asr"] = asr_info

        # Attempt to chunk the audio
        try:
            chunks = self._chunk_wav(wav_path, total_seconds)
        except ChunkingError as e:
            # Chunking failed - set error state
            m.status = "failed"
            m.partial = False
            m.status_reason = StatusReason.from_code("asr_failed")
            if not m.content_text:
                m.content_text = "[AUDIO TRANSCRIPTION FAILED (chunking)]"

            asr_info["api_version"] = getattr(self.asr_client, "api_version", self.cfg.asr_api_version)
            asr_info["provider"] = getattr(self.asr_client, "provider_name", self.cfg.asr_provider)
            asr_info["model"] = getattr(self.asr_client, "model", self.cfg.asr_model)
            asr_info["billing_plan"] = self.cfg.asr_billing_plan
            asr_info["chunks"] = []
            asr_info["total_duration_seconds"] = total_seconds
            asr_info["error_summary"] = {
                "chunks_ok": 0,
                "chunks_error": 0,
                "last_error_kind": "chunking",
                "last_error_message": str(e),
            }
            asr_info["cost"] = 0.0
            m.derived["asr"] = asr_info
            return

        chunk_results = []
        for chunk in chunks:
            result = self.asr_client.transcribe_chunk(
                chunk["wav_chunk_path"], chunk["start_sec"], chunk["end_sec"]
            )
            chunk_result = {
                "chunk_index": chunk["chunk_index"],
                "start_sec": chunk["start_sec"],
                "end_sec": chunk["end_sec"],
                "duration_sec": chunk["duration_sec"],
                "wav_chunk_path": str(chunk["wav_chunk_path"]),
                "status": result.status,
                "text": result.text,
                "error": result.error,
                "error_kind": result.error_kind,
                "language": result.language,
            }
            chunk_results.append(chunk_result)

        transcript_parts = [c["text"] for c in chunk_results if c["status"] == "ok" and c["text"]]
        transcript = "\n".join(transcript_parts)

        any_ok = any(c["status"] == "ok" for c in chunk_results)
        any_err = any(c["status"] != "ok" for c in chunk_results)

        if not transcript and not m.content_text:
            m.content_text = transcript
        elif transcript and not m.content_text:
            m.content_text = transcript
        elif transcript and m.content_text:
            m.content_text = m.content_text + "\n" + transcript

        # Determine last error kind for proper status_reason mapping
        last_error_kind = None
        for c in reversed(chunk_results):
            if c.get("error_kind"):
                last_error_kind = c["error_kind"]
                break

        if any_err and not any_ok:
            m.status = "failed"
            m.partial = False
            # Use error mapping to differentiate timeout vs other errors
            if last_error_kind:
                m.status_reason = map_asr_error_to_status_reason(last_error_kind)
            else:
                m.status_reason = StatusReason.from_code("asr_failed")
            if not m.content_text:
                m.content_text = "[AUDIO TRANSCRIPTION FAILED]"
        elif any_err and any_ok:
            m.status = "partial"
            m.partial = True
            m.status_reason = StatusReason.from_code("asr_partial")
        else:
            m.status = "ok"
            m.partial = False
            m.status_reason = None

        asr_info["api_version"] = getattr(self.asr_client, "api_version", self.cfg.asr_api_version)
        asr_info["provider"] = getattr(self.asr_client, "provider_name", self.cfg.asr_provider)
        asr_info["model"] = getattr(self.asr_client, "model", self.cfg.asr_model)
        asr_info["billing_plan"] = self.cfg.asr_billing_plan
        asr_info["chunks"] = chunk_results
        asr_info["total_duration_seconds"] = total_seconds
        asr_info["error_summary"] = {
            "chunks_ok": sum(1 for c in chunk_results if c["status"] == "ok"),
            "chunks_error": sum(1 for c in chunk_results if c["status"] != "ok"),
            "last_error_kind": last_error_kind,
            "last_error_message": next((c["error"] for c in reversed(chunk_results) if c["error"]), None),
        }
        asr_info["cost"] = estimate_asr_cost(
            total_seconds,
            asr_info["provider"],
            asr_info["model"],
            self.cfg.asr_billing_plan,
        )
        m.derived["asr"] = asr_info

        self._write_cache(m)

    def _to_wav(self, m: Message) -> Optional[Path]:
        """Convert input media to normalized WAV using ffmpeg with retries."""
        if m.kind != "voice" or not m.media_filename:
            return None

        input_path = Path(m.media_filename)
        if not input_path.exists():
            m.status = "failed"
            m.status_reason = StatusReason.from_code("audio_unsupported_format")
            return None

        self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        out_path = self.cfg.cache_dir / f"{sha256_file(input_path)}.wav"

        cmd = [
            self.cfg.ffmpeg_bin,
            "-y",
            "-i",
            str(input_path),
            "-ar",
            str(self.cfg.sample_rate),
            "-ac",
            str(self.cfg.channels),
            "-f",
            "wav",
            str(out_path),
        ]

        last_err = ""
        for attempt in range(self.cfg.ffmpeg_max_retries):
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=self.cfg.ffmpeg_timeout_seconds,
                    check=False,
                )
                last_err = (result.stderr or "")[-2048:]
                if result.returncode == 0:
                    m.derived.setdefault("asr", {})["ffmpeg_log_tail"] = last_err
                    if not out_path.exists():
                        continue
                    return out_path
            except subprocess.TimeoutExpired as exc:
                last_err = str(exc)
                m.derived.setdefault("asr", {})["ffmpeg_log_tail"] = last_err
                m.status = "failed"
                m.status_reason = StatusReason.from_code("timeout_ffmpeg")
                if not m.content_text:
                    m.content_text = "[AUDIO CONVERSION FAILED]"
                return None

        # Failed after retries
        m.derived.setdefault("asr", {})["ffmpeg_log_tail"] = last_err
        m.status = "failed"
        m.status_reason = StatusReason.from_code("ffmpeg_failed")
        if not m.content_text:
            m.content_text = "[AUDIO CONVERSION FAILED]"
        if out_path.exists():
            out_path.unlink()
        return None

    def _wav_duration_seconds(self, wav_path: Path) -> float:
        try:
            with wave.open(str(wav_path), "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate == 0:
                    return 0.0
                return frames / float(rate)
        except wave.Error:
            # Fallback to approximate based on file size when not a valid WAV header
            try:
                size = wav_path.stat().st_size
                bytes_per_second = self.cfg.sample_rate * self.cfg.channels * 2
                return size / bytes_per_second if bytes_per_second else 0.0
            except OSError:
                return 0.0

    def _chunk_wav(self, wav_path: Path, total_seconds: float) -> list[dict]:
        """Split WAV into fixed windows with overlap and emit chunk wavs.

        Args:
            wav_path: Path to the WAV file to chunk.
            total_seconds: Duration of the audio in seconds.

        Returns:
            Non-empty list of chunk dictionaries with strictly increasing timestamps.

        Raises:
            ChunkingError: If audio is invalid, 0-length, or cannot be chunked.
        """
        # Validate input
        if total_seconds <= 0:
            raise ChunkingError(f"Invalid audio duration: {total_seconds} seconds")

        if not wav_path.exists():
            raise ChunkingError(f"WAV file not found: {wav_path}")

        chunk_seconds = self.cfg.chunk_seconds
        overlap = min(self.cfg.chunk_overlap_seconds, chunk_seconds / 2)
        start = 0.0
        chunks: list[dict] = []

        base_chunk_dir = self.cfg.chunk_dir or (self.cfg.cache_dir / "chunks" / sha256_file(wav_path))
        base_chunk_dir.mkdir(parents=True, exist_ok=True)

        try:
            with wave.open(str(wav_path), "rb") as wf:
                params = wf.getparams()
                sampwidth = wf.getsampwidth()
                n_channels = wf.getnchannels()
                framerate = wf.getframerate()

                # Validate WAV parameters
                if framerate == 0:
                    raise ChunkingError("Invalid WAV: framerate is 0")
                if sampwidth == 0:
                    raise ChunkingError("Invalid WAV: sample width is 0")

                prev_start = -1.0
                while start < total_seconds:
                    end = min(start + chunk_seconds, total_seconds)
                    if end <= start:
                        break
                    frames_start = int(start * framerate)
                    frames_end = int(end * framerate)
                    frame_count = frames_end - frames_start
                    wf.setpos(frames_start)
                    frames = wf.readframes(frame_count)

                    chunk_index = len(chunks)
                    chunk_path = base_chunk_dir / f"chunk_{chunk_index:04d}.wav"
                    with wave.open(str(chunk_path), "wb") as out_wf:
                        out_wf.setnchannels(n_channels)
                        out_wf.setsampwidth(sampwidth)
                        out_wf.setframerate(framerate)
                        out_wf.writeframes(frames)

                    chunks.append(
                        {
                            "chunk_index": chunk_index,
                            "start_sec": round(start, 3),
                            "end_sec": round(min(end, total_seconds), 3),
                            "duration_sec": round(min(end, total_seconds) - start, 3),
                            "wav_chunk_path": str(chunk_path),
                        }
                    )
                    if end >= total_seconds:
                        break
                    next_start = end - overlap
                    if next_start <= start:
                        break
                    start = next_start
                    if abs(start - prev_start) < 1e-6:
                        break
                    prev_start = start
        except wave.Error as e:
            raise ChunkingError(f"Failed to read WAV file: {e}")
        except OSError as e:
            raise ChunkingError(f"I/O error reading WAV file: {e}")

        # Invariant: must produce at least one chunk for valid audio
        if not chunks:
            raise ChunkingError(
                f"No chunks produced for audio of {total_seconds} seconds. "
                "This may indicate corrupted or truncated audio."
            )

        return chunks

    def _cache_key(self, m: Message) -> Optional[str]:
        media_path = Path(m.media_filename)
        if not media_path.exists():
            return None
        media_hash = sha256_file(media_path)
        cfg_bits = (
            f"{self.cfg.asr_provider}|{self.cfg.asr_model}|"
            f"{self.cfg.chunk_seconds}|{self.cfg.chunk_overlap_seconds}|"
            f"{self.cfg.vad_min_speech_ratio}|{self.cfg.vad_min_speech_seconds}|"
            f"{self.cfg.asr_billing_plan}"
        )
        return sha256_file(media_path, extra=cfg_bits)

    def _cache_path(self, key: str) -> Path:
        return self.cfg.cache_dir / f"{key}.json"

    def _load_cache(self, m: Message) -> Optional[dict]:
        key = self._cache_key(m)
        if not key:
            return None
        path = self._cache_path(key)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None

    def _apply_cache(self, m: Message, payload: dict) -> None:
        m.content_text = payload.get("content_text", "")
        m.status = payload.get("status", "ok")
        m.partial = bool(payload.get("partial", False))
        reason = payload.get("status_reason")
        m.status_reason = StatusReason.from_code(reason) if reason else None
        m.derived["asr"] = payload.get("derived_asr", {})

    def _write_cache(self, m: Message) -> None:
        key = self._cache_key(m)
        if not key:
            return
        path = self._cache_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "content_text": m.content_text,
            "status": m.status,
            "status_reason": m.status_reason.code if m.status_reason else None,
            "partial": m.partial,
            "derived_asr": m.derived.get("asr", {}),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        shutil.move(tmp, path)
