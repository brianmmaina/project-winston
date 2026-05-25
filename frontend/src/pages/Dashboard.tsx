import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiClientError,
  getMeta,
  getSignals,
  triggerRefreshAsync,
} from "../api/client";
import type { SignalPayload } from "../api/types.generated";
import { PageState } from "../components/PageState";
import { useJob } from "../hooks/useJob";

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

export default function Dashboard(): ReactElement {
  const navigate = useNavigate();
  const [signals, setSignals] = useState<SignalPayload[] | null>(null);
  const [metaIso, setMetaIso] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [buyOnly, setBuyOnly] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const { job, isPolling, error: jobError, start: startJob, reset: resetJob } = useJob();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sig, metaTry] = await Promise.all([
        getSignals(),
        getMeta().catch(() => null),
      ]);
      setSignals(sig);
      setMetaIso(isoFromMeta(metaTry));
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

  const COLS = ["COMMODITY", "NAME", "SIGNAL", "CONVICTION", "REGIME", "SENTIMENT", "UPDATED"];

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div>
            <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
              {signals?.length ?? 0} commodities · {buyCt} BUY signals
            </p>
            {metaIso && (
              <p className="font-mono text-[10px] text-on-surface-variant opacity-60 mt-0.5">
                Last refresh: {new Date(metaIso).toLocaleString()}
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
                      <span className="font-mono text-[13px] font-semibold text-on-surface">{s.ticker}</span>
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant whitespace-nowrap max-w-[140px] truncate">
                      {s.name ?? "—"}
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
