import pytest

from src.utils.cost import estimate_asr_cost, accumulate_costs
from src.schema.message import Message


def test_cost_estimate_basic_rounds_up():
    # 90 seconds rounds to 2 minutes at $0.006/min => $0.012
    cost = estimate_asr_cost(90, provider="whisper", model=None, billing="per_minute")
    assert cost == pytest.approx(0.012, rel=1e-6)


def test_accumulate_costs_sums_by_provider():
    m1 = Message(idx=0, ts="2025-01-01T00:00:00Z", sender="Alice", kind="voice")
    m1.derived["asr"] = {"provider": "whisper", "cost": 0.012}
    m2 = Message(idx=1, ts="2025-01-01T00:01:00Z", sender="Bob", kind="voice")
    m2.derived["asr"] = {"provider": "whisper", "cost": 0.006}
    summary = accumulate_costs([m1, m2])
    assert summary["total"] == pytest.approx(0.018, rel=1e-6)
    assert summary["providers"]["whisper"] == pytest.approx(0.018, rel=1e-6)
