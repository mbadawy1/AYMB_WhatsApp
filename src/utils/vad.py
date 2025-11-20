"""Lightweight VAD wrapper placeholder."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class VadStats:
    speech_ratio: float
    speech_seconds: float
    total_seconds: float
    segments: list[tuple[float, float]]


def run_vad(wav_path: Path, cfg) -> VadStats:
    """Run a placeholder VAD over a WAV file.

    This lightweight implementation estimates duration from file size and
    treats non-zero bytes as speech content.
    """
    data = wav_path.read_bytes() if wav_path.exists() else b""
    total_seconds = len(data) / (cfg.sample_rate * cfg.channels * 2) if getattr(cfg, "sample_rate", None) else 0.0
    has_speech = any(byte != 0 for byte in data)
    speech_seconds = total_seconds * 0.8 if has_speech else 0.0
    speech_ratio = 0.0 if total_seconds == 0 else speech_seconds / total_seconds
    segments = [(0.0, speech_seconds)] if speech_seconds > 0 else []
    return VadStats(
        speech_ratio=speech_ratio,
        speech_seconds=speech_seconds,
        total_seconds=total_seconds,
        segments=segments,
    )
