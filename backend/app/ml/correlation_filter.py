"""Remove redundant BUY picks that move together (90d returns)."""

from __future__ import annotations

from typing import Any

import pandas as pd


def deduplicate_correlated_signals(signals: list[dict[str, Any]], price_df: pd.DataFrame, threshold: float = 0.70) -> list[dict[str, Any]]:
    clones = [dict(item) for item in signals]
    rests = [row for row in clones if row.get("signal") != "BUY"]
    buys = [row for row in clones if row.get("signal") == "BUY"]
    if not buys:
        return clones
    buys_sorted = sorted(buys, key=lambda row: float(row.get("avg_confidence", 0.0)), reverse=True)
    survivor_codes: list[str] = []
    filtered: list[dict[str, Any]] = []
    for cand in buys_sorted:
        ticker_code = str(cand["ticker"])
        flagged = False
        for existing in survivor_codes:
            duo = price_df[[ticker_code, existing]].dropna(how="any")
            duo = duo.sort_index().tail(90)
            corr_table = duo.pct_change().corr()
            corr_val = float(corr_table.loc[ticker_code, existing])
            if corr_val > threshold:
                flagged = True
                break
        if flagged:
            cand["signal"] = "HOLD"
            cand["correlation_filtered"] = True
        else:
            survivor_codes.append(ticker_code)
            cand["correlation_filtered"] = False
        filtered.append(cand)
    combined = rests + filtered
    ticker_rank = {str(row["ticker"]): idx for idx, row in enumerate(clones)}
    combined.sort(key=lambda row: ticker_rank[str(row["ticker"])])
    return combined
