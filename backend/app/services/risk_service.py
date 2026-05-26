"""Phase 7 — Portfolio risk layer.

Applies exposure limits, correlation-aware sizing adjustments, and stop-loss
flags on top of the raw ML signal payloads before they reach the overseer.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---- Portfolio limit constants -----------------------------------------------

MAX_TOTAL_COMMODITY_PCT = 0.40   # max 40% of portfolio in commodities
MAX_TOTAL_EQUITY_PCT = 0.60      # max 60% in equities
MAX_SECTOR_PCT = 0.20            # no single sector > 20%
MAX_SINGLE_POSITION_PCT = 0.10   # no single name > 10% (Kelly already caps this)
MIN_POSITION_PCT = 0.01          # floor — don't show <1% positions
CORR_SHRINK_THRESHOLD = 0.75     # pairwise correlation above this triggers shrinkage
CORR_SHRINK_FACTOR = 0.5         # multiply Kelly by this when pair is too correlated

# Commodity sector groupings for sector exposure limits
_SECTOR_MAP: dict[str, str] = {
    "CL=F": "energy", "BZ=F": "energy", "NG=F": "energy",
    "HO=F": "energy", "RB=F": "energy",
    "GC=F": "metals", "SI=F": "metals", "HG=F": "metals",
    "PL=F": "metals", "PA=F": "metals",
    "ZC=F": "agriculture", "ZW=F": "agriculture", "ZS=F": "agriculture",
    "KC=F": "agriculture", "CT=F": "agriculture", "SB=F": "agriculture",
    "CC=F": "agriculture",
}


def _is_equity(ticker: str) -> bool:
    return "=" not in ticker


def apply_portfolio_limits(
    payloads: list[dict[str, Any]],
    close_prices: dict[str, pd.DataFrame] | None = None,
) -> list[dict[str, Any]]:
    """
    Enforce portfolio exposure limits on the signal payload list.

    Modifies `position_size_pct` in place and adds `risk_flags` to each payload.
    Returns the modified list.
    """
    buy_signals = [p for p in payloads if p.get("signal") == "BUY"]
    if not buy_signals:
        return payloads

    # ---- 1. Sector caps -------------------------------------------------------
    sector_totals: dict[str, float] = {}
    for p in buy_signals:
        ticker = p["ticker"]
        sector = _SECTOR_MAP.get(ticker, "equity" if _is_equity(ticker) else "other")
        sector_totals[sector] = sector_totals.get(sector, 0.0) + p.get("position_size_pct", 0.0)

    for p in buy_signals:
        ticker = p["ticker"]
        sector = _SECTOR_MAP.get(ticker, "equity" if _is_equity(ticker) else "other")
        total = sector_totals.get(sector, 0.0)
        if total > MAX_SECTOR_PCT and total > 0:
            scale = MAX_SECTOR_PCT / total
            p["position_size_pct"] = round(p.get("position_size_pct", 0.0) * scale, 4)
            p.setdefault("risk_flags", []).append(f"sector_cap:{sector}")

    # ---- 2. Asset-class caps --------------------------------------------------
    commodity_total = sum(p.get("position_size_pct", 0.0) for p in buy_signals if not _is_equity(p["ticker"]))
    equity_total = sum(p.get("position_size_pct", 0.0) for p in buy_signals if _is_equity(p["ticker"]))

    if commodity_total > MAX_TOTAL_COMMODITY_PCT and commodity_total > 0:
        scale = MAX_TOTAL_COMMODITY_PCT / commodity_total
        for p in buy_signals:
            if not _is_equity(p["ticker"]):
                p["position_size_pct"] = round(p.get("position_size_pct", 0.0) * scale, 4)
                p.setdefault("risk_flags", []).append("commodity_cap")

    if equity_total > MAX_TOTAL_EQUITY_PCT and equity_total > 0:
        scale = MAX_TOTAL_EQUITY_PCT / equity_total
        for p in buy_signals:
            if _is_equity(p["ticker"]):
                p["position_size_pct"] = round(p.get("position_size_pct", 0.0) * scale, 4)
                p.setdefault("risk_flags", []).append("equity_cap")

    # ---- 3. Single position cap -----------------------------------------------
    for p in buy_signals:
        if p.get("position_size_pct", 0.0) > MAX_SINGLE_POSITION_PCT:
            p["position_size_pct"] = MAX_SINGLE_POSITION_PCT
            p.setdefault("risk_flags", []).append("position_cap")

    # ---- 4. Correlation-aware shrinkage (using close price history) -----------
    if close_prices and len(buy_signals) >= 2:
        tickers = [p["ticker"] for p in buy_signals]
        frames = []
        for t in tickers:
            if t in close_prices and not close_prices[t].empty:
                s = close_prices[t].squeeze() if hasattr(close_prices[t], "squeeze") else close_prices[t]
                frames.append(pd.Series(s.values, name=t))
        if len(frames) >= 2:
            price_df = pd.concat(frames, axis=1).dropna()
            if len(price_df) > 30:
                ret_df = np.log(price_df / price_df.shift(1)).dropna()
                corr = ret_df.corr()
                payload_map = {p["ticker"]: p for p in buy_signals}
                for i, ti in enumerate(tickers):
                    for j, tj in enumerate(tickers):
                        if j <= i:
                            continue
                        try:
                            r = corr.loc[ti, tj]
                        except KeyError:
                            continue
                        if abs(r) >= CORR_SHRINK_THRESHOLD:
                            # Shrink the smaller-conviction position
                            pi = payload_map.get(ti)
                            pj = payload_map.get(tj)
                            if pi and pj:
                                if pi.get("avg_confidence", 0) >= pj.get("avg_confidence", 0):
                                    pj["position_size_pct"] = round(pj.get("position_size_pct", 0.0) * CORR_SHRINK_FACTOR, 4)
                                    pj.setdefault("risk_flags", []).append(f"corr_shrink:{ti}")
                                else:
                                    pi["position_size_pct"] = round(pi.get("position_size_pct", 0.0) * CORR_SHRINK_FACTOR, 4)
                                    pi.setdefault("risk_flags", []).append(f"corr_shrink:{tj}")

    # ---- 5. Remove sub-floor positions ----------------------------------------
    for p in buy_signals:
        if p.get("position_size_pct", 0.0) < MIN_POSITION_PCT:
            p["position_size_pct"] = 0.0
            p.setdefault("risk_flags", []).append("below_floor")

    # Propagate risk_flags to all payloads (HOLD signals get empty list)
    for p in payloads:
        p.setdefault("risk_flags", [])

    logger.info(
        "Risk layer applied: %d BUY signals, sectors=%s",
        len(buy_signals),
        {k: round(v, 3) for k, v in sector_totals.items()},
    )
    return payloads


def portfolio_summary(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Return portfolio-level exposure stats for the agent overseer."""
    buys = [p for p in payloads if p.get("signal") == "BUY"]
    total_exposure = sum(p.get("position_size_pct", 0.0) for p in buys)
    commodity_exp = sum(p.get("position_size_pct", 0.0) for p in buys if not _is_equity(p["ticker"]))
    equity_exp = sum(p.get("position_size_pct", 0.0) for p in buys if _is_equity(p["ticker"]))
    by_sector: dict[str, float] = {}
    for p in buys:
        ticker = p["ticker"]
        sector = _SECTOR_MAP.get(ticker, "equity" if _is_equity(ticker) else "other")
        by_sector[sector] = round(by_sector.get(sector, 0.0) + p.get("position_size_pct", 0.0), 4)
    flagged = [p["ticker"] for p in buys if p.get("risk_flags")]
    return {
        "total_exposure_pct": round(total_exposure, 4),
        "commodity_exposure_pct": round(commodity_exp, 4),
        "equity_exposure_pct": round(equity_exp, 4),
        "by_sector": by_sector,
        "buy_count": len(buys),
        "risk_flagged": flagged,
        "limits": {
            "max_commodity_pct": MAX_TOTAL_COMMODITY_PCT,
            "max_equity_pct": MAX_TOTAL_EQUITY_PCT,
            "max_sector_pct": MAX_SECTOR_PCT,
            "max_single_pct": MAX_SINGLE_POSITION_PCT,
        },
    }
