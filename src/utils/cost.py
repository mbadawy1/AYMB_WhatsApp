"""ASR cost estimation utilities.

Provides deterministic, table-driven cost calculation for ASR providers.
Rates are kept in-code (no network calls) to ensure reproducibility.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple, Optional

# Rates are expressed per minute in USD, with a billing increment in seconds.
# Expand or adjust as providers/models are added.
COST_TABLE: Dict[Tuple[str, str, str], Dict[str, float]] = {
    ("whisper", "default", "per_minute"): {"rate_per_minute": 0.006, "increment_seconds": 60.0},
    ("whisper", "large-v2", "per_minute"): {"rate_per_minute": 0.012, "increment_seconds": 60.0},
}

DEFAULT_RATE = {"rate_per_minute": 0.006, "increment_seconds": 60.0}


def _lookup_rate(provider: str, model: Optional[str], billing: str) -> Dict[str, float]:
    """Fetch rate configuration for a provider/model/billing tuple."""
    key = (provider or "whisper", (model or "default"), billing or "per_minute")
    return COST_TABLE.get(key, DEFAULT_RATE)


def estimate_asr_cost(seconds: float, provider: str, model: Optional[str], billing: str = "per_minute") -> float:
    """Estimate ASR cost given audio duration and provider settings.

    Args:
        seconds: Audio duration in seconds.
        provider: ASR provider identifier.
        model: Provider model identifier (optional).
        billing: Billing plan key (e.g., "per_minute").

    Returns:
        Cost in USD rounded to 4 decimal places.
    """
    duration = max(0.0, float(seconds))
    rate_cfg = _lookup_rate(provider, model, billing)
    increment = rate_cfg.get("increment_seconds", 60.0)
    if increment <= 0:
        rounded = duration
    else:
        rounded = math.ceil(duration / increment) * increment

    minutes = rounded / 60.0
    cost = rate_cfg.get("rate_per_minute", 0.0) * minutes
    # Round for determinism
    return round(cost, 4)


def accumulate_costs(messages) -> Dict[str, float]:
    """Aggregate per-message ASR costs from derived payloads."""
    total = 0.0
    per_provider: Dict[str, float] = {}
    for msg in messages or []:
        asr = getattr(msg, "derived", {}).get("asr", {})  # type: ignore[attr-defined]
        cost = asr.get("cost")
        if cost is None:
            continue
        provider = asr.get("provider") or "unknown"
        total += float(cost)
        per_provider[provider] = per_provider.get(provider, 0.0) + float(cost)
    return {"total": round(total, 4), "providers": {k: round(v, 4) for k, v in per_provider.items()}}
