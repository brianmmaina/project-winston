import { useCallback, useEffect, useState } from "react";
import { getLivePrices } from "../api/client";
import { isMarketHours } from "../utils/marketHours";

const POLL_MS = 2 * 60 * 1000;

/**
 * Polls /api/prices/live every 2 minutes during market hours.
 * Pass a stable array (memo-ized or module-level constant) to avoid
 * re-subscribing on every render.
 */
export function useLivePrices(tickers: string[]): Record<string, number | null> {
  // Stable key so the effect only re-runs when the ticker list actually changes.
  const tickersKey = tickers.slice().sort().join(",");
  const [prices, setPrices] = useState<Record<string, number | null>>({});

  const doFetch = useCallback(async () => {
    const list = tickersKey.split(",").filter(Boolean);
    if (!list.length) return;
    try {
      setPrices(await getLivePrices(list));
    } catch {
      // non-critical — stale prices are fine
    }
  }, [tickersKey]);

  useEffect(() => {
    void doFetch();
    const id = setInterval(() => {
      if (isMarketHours()) void doFetch();
    }, POLL_MS);
    return () => clearInterval(id);
  }, [doFetch]);

  return prices;
}
