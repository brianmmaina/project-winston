"""Consensus probability thresholds aligned with live `predictor` BUY gate (per horizon)."""

from __future__ import annotations

HORIZON_PROB_THRESHOLDS: dict[str, float] = {
    "5d": 0.60,
    "10d": 0.58,
    "21d": 0.55,
}
