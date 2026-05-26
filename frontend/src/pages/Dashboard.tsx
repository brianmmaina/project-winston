import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiClientError,
  getEconomicEvents,
  getMeta,
  getPortfolioRisk,
  getPriceTriggers,
  getSignals,
  triggerRefreshAsync,
} from "../api/client";
import type { EconomicEvent, PortfolioRiskSummary, PriceTriggerEvent, SignalPayload } from "../api/types.generated";
import { PageState } from "../components/PageState";
import { useJob } from "../hooks/useJob";
import { useLivePrices } from "../hooks/useLivePrices";
import { isMarketHours } from "../utils/marketHours";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

function isoFromMeta(meta: { last_refresh?: string; refreshed_at?: string } | null): string | undefined {
  return meta?.last_refresh ?? meta?.refreshed_at;
}

function SignalBadge({ signal }: { signal: string }) {
  if (signal === "BUY") {
    return (
      <span className="font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border border-secondary/30 bg-secondary/10 text-secondary">
        BUY
      </span>
    );
  }
  return (
    <span className="font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border border-outline-variant text-on-surface-variant">
      HOLD
    </span>
  );
}

function ConvictionBar({ value }: { value: number }) {
  const width = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1 bg-surface-container-high rounded-none overflow-hidden">
        <div
          className="h-full bg-secondary"
          style={{ width: `${width}%` }}
        />
      </div>
      <span className="font-mono text-[11px] text-on-surface-variant tabular-nums">{value.toFixed(2)}</span>
    </div>
  );
}

function ExposureBar({ label, value, max }: { label: string; value: number; max: number }) {
  const pct = Math.round(Math.min((value / max) * 100, 100));
  const overLimit = value > max;
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-on-surface-variant w-20 shrink-0">{label}</span>
      <div className="flex-1 h-1.5 bg-surface-container-high overflow-hidden">
        <div className={`h-full ${overLimit ? "bg-error" : "bg-secondary"}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`font-mono text-[10px] tabular-nums w-10 text-right ${overLimit ? "text-error" : "text-on-surface"}`}>
        {(value * 100).toFixed(1)}%
      </span>
    </div>
  );
}

function PortfolioExposure({ risk }: { risk: PortfolioRiskSummary }) {
  const sectors = Object.entries(risk.by_sector);
  return (
    <div className="border border-outline-variant bg-surface-container px-4 py-3 space-y-2">
      <div className="flex items-center justify-between mb-1">
        <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant">Portfolio Exposure</p>
        <p className="font-mono text-[9px] text-on-surface-variant opacity-60">{risk.buy_count} BUY · total {(risk.total_exposure_pct * 100).toFixed(1)}%</p>
      </div>
      <ExposureBar label="Commodities" value={risk.commodity_exposure_pct} max={risk.limits.max_commodity_pct} />
      <ExposureBar label="Equities" value={risk.equity_exposure_pct} max={risk.limits.max_equity_pct} />
      {sectors.map(([sector, exp]) => (
        <ExposureBar key={sector} label={sector} value={exp} max={risk.limits.max_sector_pct} />
      ))}
      {risk.risk_flagged.length > 0 && (
        <div className="pt-1 flex flex-wrap gap-1">
          {risk.risk_flagged.map((t) => (
            <span key={t} className="font-mono text-[9px] px-1.5 py-0.5 border border-error/30 bg-error/10 text-error">{t}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function PriceTriggerStrip({ triggers }: { triggers: PriceTriggerEvent[] }) {
  if (triggers.length === 0) return null;
  return (
    <div className="border border-outline-variant bg-surface-container px-4 py-2.5 flex items-center gap-4 overflow-x-auto">
      <span className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant shrink-0">
        <span className="material-symbols-outlined text-[11px] leading-none mr-1 align-middle">electric_bolt</span>
        Price Events
      </span>
      <div className="flex items-center gap-2">
        {triggers.slice(0, 10).map((t, i) => {
          const up = t.direction === "above";
          return (
            <div
              key={i}
              className={`shrink-0 flex items-center gap-1 px-2 py-0.5 border font-mono text-[9px] ${
                up
                  ? "border-secondary/40 bg-secondary/10 text-secondary"
                  : "border-error/40 bg-error/10 text-error"
              }`}
              title={`${t.name}: ${t.latest_price.toFixed(2)} vs SMA ${t.sma_20d.toFixed(2)} · ${new Date(t.triggered_at).toLocaleString()}`}
            >
              <span className="material-symbols-outlined text-[10px] leading-none">
                {up ? "arrow_upward" : "arrow_downward"}
              </span>
              <span className="font-bold">{t.ticker.replace("=F", "")}</span>
              <span className="opacity-70">{up ? "+" : ""}{t.deviation_pct.toFixed(1)}%</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function CalendarStrip({ events }: { events: EconomicEvent[] }) {
  if (events.length === 0) return null;
  const typeColor: Record<string, string> = {
    FOMC: "text-error border-error/40 bg-error/10",
    CPI: "text-warning border-warning/40 bg-warning/10",
    NFP: "text-secondary border-secondary/40 bg-secondary/10",
  };
  return (
    <div className="border border-outline-variant bg-surface-container px-4 py-2.5 flex items-center gap-4 overflow-x-auto">
      <span className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant shrink-0">Upcoming</span>
      <div className="flex items-center gap-3">
        {events.slice(0, 8).map((e, i) => (
          <div key={i} className={`shrink-0 flex items-center gap-1.5 px-2 py-0.5 border font-mono text-[9px] ${typeColor[e.event_type] ?? "text-on-surface-variant border-outline-variant"}`}>
            <span className="font-bold">{e.event_type}</span>
            <span className="opacity-70">{new Date(e.event_date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Dashboard(): ReactElement {
  const navigate = useNavigate();
  const [signals, setSignals] = useState<SignalPayload[] | null>(null);
  const [metaIso, setMetaIso] = useState<string | undefined>(undefined);
  const [calEvents, setCalEvents] = useState<EconomicEvent[]>([]);
  const [portfolioRisk, setPortfolioRisk] = useState<PortfolioRiskSummary | null>(null);
  const [priceTriggers, setPriceTriggers] = useState<PriceTriggerEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [buyOnly, setBuyOnly] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const { job, isPolling, error: jobError, start: startJob, reset: resetJob } = useJob();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sig, metaTry, cal, risk, triggers] = await Promise.all([
        getSignals(),
        getMeta().catch(() => null),
        getEconomicEvents(60).catch(() => [] as EconomicEvent[]),
        getPortfolioRisk().catch(() => null),
        getPriceTriggers().catch(() => [] as PriceTriggerEvent[]),
      ]);
      setSignals(sig);
      setMetaIso(isoFromMeta(metaTry));
      setCalEvents(cal);
      setPortfolioRisk(risk);
      setPriceTriggers(triggers);
    } catch (e) {
      const code = errMsg(e);
      if (code.includes("503") || code.includes("cache empty")) {
        setSignals([]);
      } else {
        setError(code);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Auto-refresh price triggers every 5 min during market hours
  useEffect(() => {
    const id = setInterval(() => {
      if (isMarketHours()) {
        getPriceTriggers().then(setPriceTriggers).catch(() => {});
      }
    }, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, []);

  const signalTickers = useMemo(() => (signals ?? []).map((s) => s.ticker), [signals]);
  const livePrices = useLivePrices(signalTickers);

  const rows = useMemo(() => {
    const list = signals ?? [];
    const filtered = buyOnly ? list.filter((s) => s.signal === "BUY") : list;
    return [...filtered].sort((a, b) => {
      if (a.signal === "BUY" && b.signal !== "BUY") return -1;
      if (b.signal === "BUY" && a.signal !== "BUY") return 1;
      return b.avg_confidence - a.avg_confidence;
    });
  }, [signals, buyOnly]);

  const buyCt = useMemo(() => (signals ?? []).filter((s) => s.signal === "BUY").length, [signals]);

  const onRefresh = async () => {
    resetJob();
    setRefreshing(true);
    setError(null);
    try {
      const res = await triggerRefreshAsync();
      startJob(res.job_id);
    } catch (e) {
      setError(errMsg(e));
      setRefreshing(false);
    }
  };

  useEffect(() => {
    if (job && job.is_terminal) {
      setRefreshing(false);
      if (job.state === "completed") void load();
    }
  }, [job, load]);

  const marketOpen = isMarketHours();
  const COLS = ["COMMODITY", "PRICE", "SIGNAL", "CONVICTION", "REGIME", "SENTIMENT", "UPDATED"];

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <div className="flex items-center gap-2">
              <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
                {signals?.length ?? 0} commodities · {buyCt} BUY signals
              </p>
              {marketOpen ? (
                <span className="flex items-center gap-1 font-mono text-[9px] font-bold uppercase tracking-widest text-secondary">
                  <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
                  Live · 2 min
                </span>
              ) : (
                <span className="font-mono text-[9px] text-on-surface-variant opacity-40 uppercase tracking-widest">Market closed</span>
              )}
            </div>
            {metaIso && (
              <p className="font-mono text-[10px] text-on-surface-variant opacity-60 mt-0.5">
                Signals from: {new Date(metaIso).toLocaleString()}
              </p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2">
            <input
              type="checkbox"
              checked={buyOnly}
              onChange={(e) => setBuyOnly(e.target.checked)}
              className="w-3 h-3 accent-secondary"
            />
            <span className="font-mono text-[10px] font-bold tracking-[0.06em] uppercase text-on-surface-variant">BUY Only</span>
          </label>
          <button
            type="button"
            disabled={refreshing || isPolling}
            onClick={() => void onRefresh()}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-outline-variant text-on-surface-variant hover:text-on-surface hover:border-outline font-mono text-[10px] font-bold tracking-[0.06em] uppercase transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[14px] leading-none">refresh</span>
            {isPolling || refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      {(job || jobError) && (
        <div className={`border px-3 py-2 font-mono text-[11px] ${
          job?.state === "failed"
            ? "border-error/30 bg-error/10 text-error"
            : job?.state === "completed"
              ? "border-secondary/30 bg-secondary/10 text-secondary"
              : "border-outline-variant text-on-surface-variant"
        }`}>
          {jobError ? `Polling error: ${jobError}` : job ? (
            <span>
              <strong>{job.name}</strong> · {job.state}
              {job.message ? ` — ${job.message}` : ""}
              {isPolling ? <span className="ml-2 animate-pulse opacity-60">polling…</span> : null}
            </span>
          ) : null}
        </div>
      )}

      <CalendarStrip events={calEvents} />
      <PriceTriggerStrip triggers={priceTriggers} />
      {portfolioRisk && <PortfolioExposure risk={portfolioRisk} />}

      <PageState error={error} onRetry={() => void load()} emptyMessage={!loading && signals?.length === 0 ? "No signals — run a refresh." : null}>
        {loading ? (
          <div className="border border-outline-variant">
            <div className="border-b border-outline-variant bg-surface-container-high px-4 py-2 flex gap-8">
              {COLS.map((c) => <div key={c} className="h-3 bg-surface-container-highest animate-pulse rounded" style={{ width: 60 }} />)}
            </div>
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="border-b border-outline-variant px-4 py-3 flex gap-8">
                {COLS.map((c) => <div key={c} className="h-3 bg-surface-container animate-pulse rounded" style={{ width: 80 }} />)}
              </div>
            ))}
          </div>
        ) : rows.length > 0 ? (
          <div className="border border-outline-variant bg-surface-container overflow-x-auto">
            <table className="w-full text-left">
              <thead className="border-b border-outline-variant bg-surface-container-high">
                <tr>
                  {COLS.map((h) => (
                    <th key={h} className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant">
                {rows.map((s) => (
                  <tr
                    key={s.ticker}
                    className="cursor-pointer hover:bg-surface-container-high transition-colors"
                    onClick={() => navigate(`/commodity/${encodeURIComponent(s.ticker)}`)}
                  >
                    <td className="px-4 py-2.5">
                      <div>
                        <span className="font-mono text-[13px] font-semibold text-on-surface">{s.ticker}</span>
                        <p className="font-mono text-[9px] text-on-surface-variant opacity-60 truncate max-w-[100px]">{s.name}</p>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 font-mono tabular-nums whitespace-nowrap">
                      {(() => {
                        const live = livePrices[s.ticker];
                        const price = live ?? s.current_price;
                        return (
                          <div className="flex items-center gap-1.5">
                            <span className="text-[13px] font-semibold text-on-surface">${price.toFixed(2)}</span>
                            {live != null && (
                              <span className="w-1 h-1 rounded-full bg-secondary animate-pulse shrink-0" title="Live price" />
                            )}
                          </div>
                        );
                      })()}
                    </td>
                    <td className="px-4 py-2.5">
                      <SignalBadge signal={s.signal} />
                    </td>
                    <td className="px-4 py-2.5">
                      <ConvictionBar value={s.avg_confidence} />
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[10px] font-bold tracking-[0.06em] text-on-surface-variant">
                      {s.regime_label ?? "—"}
                    </td>
                    <td className="px-4 py-2.5">
                      <span className={`font-mono text-[11px] ${
                        s.sentiment.label === "BULLISH" ? "text-secondary"
                        : s.sentiment.label === "BEARISH" ? "text-error"
                        : "text-on-surface-variant"
                      }`}>
                        {s.sentiment.label}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[10px] text-on-surface-variant whitespace-nowrap">
                      {s.generated_at ? new Date(s.generated_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </PageState>
    </div>
  );
}
