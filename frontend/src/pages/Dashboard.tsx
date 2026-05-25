/** Dashboard: signal grids, regime summary, manual refresh, BUY-only filter. */

import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiClientError,
  getMeta,
  getSignals,
  triggerRefresh,
  triggerRefreshAsync,
} from "../api/client";
import type { SignalPayload } from "../api/types.generated";
import { CardSkeletonGrid, PageState } from "../components/PageState";
import { SignalCard } from "../components/SignalCard";
import { useJob } from "../hooks/useJob";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) {
    return e.message;
  }
  return "Unexpected error";
}

function isoFromMeta(meta: { last_refresh?: string; refreshed_at?: string } | null): string | undefined {
  return meta?.last_refresh ?? meta?.refreshed_at;
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
        setError(null);
      } else {
        setError(code);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const regimeSummary = useMemo(() => {
    if (!signals?.length) {
      return "—";
    }
    let t = 0;
    let m = 0;
    let h = 0;
    for (const s of signals) {
      if (s.regime === 1) {
        t += 1;
      } else if (s.regime === 2) {
        h += 1;
      } else {
        m += 1;
      }
    }
    return `${t} trending · ${m} mean-reverting · ${h} high-volatility (of ${signals.length} loaded)`;
  }, [signals]);

  const buys = useMemo(() => {
    const list = (signals ?? []).filter((s) => s.signal === "BUY");
    return [...list].sort((a, b) => b.avg_confidence - a.avg_confidence);
  }, [signals]);

  const holds = useMemo(() => {
    const list = (signals ?? []).filter((s) => s.signal !== "BUY");
    return [...list].sort((a, b) => b.avg_confidence - a.avg_confidence);
  }, [signals]);

  const onManualRefresh = async () => {
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

  const onSyncRefresh = async () => {
    resetJob();
    setRefreshing(true);
    setError(null);
    try {
      const res = await triggerRefresh();
      setMetaIso(res.refreshed_at);
      const sig = await getSignals();
      setSignals(sig);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setRefreshing(false);
    }
  };

  // When async refresh completes, pull fresh data.
  useEffect(() => {
    if (job && job.is_terminal) {
      setRefreshing(false);
      if (job.state === "completed") {
        void load();
      }
    }
  }, [job, load]);

  const emptyMsg =
    signals && signals.length === 0
      ? "No signals generated. Run a refresh from the Dashboard."
      : null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <header className="flex flex-col gap-4 border-b border-slate-800 pb-6 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-50">Commodity Trading Advisor</h1>
          <p className="mt-2 text-sm text-slate-400">Regime snapshot: {regimeSummary}</p>
          <p className="mt-1 font-mono text-xs text-slate-500">
            Last refresh: {metaIso ?? "unknown — run refresh"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
            <input
              type="checkbox"
              checked={buyOnly}
              onChange={(e) => setBuyOnly(e.target.checked)}
              className="rounded border-slate-600 bg-slate-900"
            />
            BUY only
          </label>
          <button
            type="button"
            disabled={refreshing || isPolling}
            onClick={() => void onManualRefresh()}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
            title="Async — kicks off a background job and polls"
          >
            {isPolling || refreshing ? "Refreshing…" : "Refresh data"}
          </button>
          <button
            type="button"
            disabled={refreshing || isPolling}
            onClick={() => void onSyncRefresh()}
            className="hidden rounded-md border border-slate-700 bg-slate-900/60 px-3 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-800 disabled:opacity-50 md:inline-flex"
            title="Sync — blocks until the refresh completes"
          >
            Sync refresh
          </button>
        </div>
      </header>

      {(job || jobError) ? (
        <div
          className={`mt-4 rounded-md border p-3 text-xs ${
            job?.state === "failed"
              ? "border-red-700 bg-red-900/30 text-red-200"
              : job?.state === "completed"
                ? "border-emerald-700 bg-emerald-900/30 text-emerald-200"
                : "border-slate-800 bg-slate-900/60 text-slate-300"
          }`}
        >
          {jobError ? (
            <span>Polling error: {jobError}</span>
          ) : job ? (
            <span>
              <strong className="font-mono">{job.name}</strong>
              <span className="mx-2 text-slate-500">·</span>
              <span>{job.state}</span>
              {job.message ? <span className="text-slate-400"> — {job.message}</span> : null}
              {isPolling ? <span className="ml-2 animate-pulse text-slate-500">polling…</span> : null}
            </span>
          ) : null}
        </div>
      ) : null}

      {loading ? <CardSkeletonGrid count={9} /> : null}

      <PageState error={error} onRetry={() => void load()} emptyMessage={emptyMsg}>
        {!loading && signals && signals.length > 0 ? (
          <div className="mt-8 space-y-10">
            {!buyOnly || buys.length > 0 ? (
              <section>
                <h2 className="mb-4 text-lg font-semibold text-emerald-300">BUY signals</h2>
                {buys.length === 0 ? (
                  <p className="text-sm text-slate-500">No BUY signals in the current batch.</p>
                ) : (
                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    {buys.map((s) => (
                      <SignalCard key={s.ticker} signal={s} muted={false} onOpen={(t) => navigate(`/commodity/${encodeURIComponent(t)}`)} />
                    ))}
                  </div>
                )}
              </section>
            ) : null}
            {!buyOnly ? (
              <section>
                <h2 className="mb-4 text-lg font-semibold text-slate-400">HOLD signals</h2>
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {holds.map((s) => (
                    <SignalCard key={s.ticker} signal={s} muted onOpen={(t) => navigate(`/commodity/${encodeURIComponent(t)}`)} />
                  ))}
                </div>
              </section>
            ) : null}
          </div>
        ) : null}
      </PageState>
    </div>
  );
}
