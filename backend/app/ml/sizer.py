"""Kelly-based position sizing."""

from __future__ import annotations

def kelly_position_size(win_probability: float, avg_win_pct: float, avg_loss_pct: float, kelly_fraction: float = 0.25, cap: float = 0.15) -> float:
    loss_mag = avg_loss_pct
    if loss_mag <= 0:
        return 0.0
    if win_probability <= 0 or win_probability >= 1:
        return 0.0
    odds_ratio = avg_win_pct / loss_mag
    downside_prob = 1.0 - win_probability
    edge = win_probability * odds_ratio - downside_prob
    raw_fraction = edge / odds_ratio
    guarded = raw_fraction * kelly_fraction
    guarded = max(0.0, guarded)
    guarded = min(guarded, cap)
    return round(guarded, 4)
