/** Stocks dashboard: cross-sectional rankings + universe browse, with sector filter
 * and a manual refresh action that kicks off the async pipeline. */

import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ApiClientError,
  getStockRankings,
  getStockUniverse,
  triggerStockRefresh,
  triggerStockRetrain,
} from "../api/client";
import type { StockRankingRow, StockUniverseRow } from "../api/types.generated";
import { CardSkeletonGrid, PageState } from "../components/PageState";
import { useJob } from "../hooks/useJob";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

const SECTOR_FILTER_ALL = "__all__";

export default function StocksDashboard(): ReactElement {
  const navigate = useNavigate();
  const [rankings, setRankings] = useState<StockRankingRow[] | null>(null);
  const [universe, setUniverse] = useState<StockUniverseRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sectorFilter, setSectorFilter] = useState<string>(SECTOR_FILTER_ALL);
  const [topOnly, setTopOnly] = useState(false);
  const [busy, setBusy] = useState<"refresh" | "retrain" | null>(null);
  const [busyMessage, setBusyMessage] = useState<string | null>(null);
  const { job, isPolling, error: jobError, start: startJob, reset: resetJob } = useJob();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [r, u] = await Promise.all([
        getStockRankings("5d", false).catch(() => [] as StockRankingRow[]),
        getStockUniverse(),
      ]);
      setRankings(r);
      setUniverse(u);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const sectors = useMemo(() => {
    const set = new Set<string>();
    for (const row of universe ?? []) {
      if (row.sector) set.add(row.sector);
    }
    return [SECTOR_FILTER_ALL, ...Array.from(set).sort()];
  }, [universe]);

  const filteredRankings = useMemo(() => {
    const list = (rankings ?? []).slice();
    list.sort((a, b) => a.rank - b.rank);
    return list.filter((r) => {
      if (topOnly && !r.in_topk) return false;
      if (sectorFilter !== SECTOR_FILTER_ALL && r.sector !== sectorFilter) return false;
      return true;
    });
  }, [rankings, sectorFilter, topOnly]);

  const onRefresh = async () => {
    resetJob();
    setBusy("refresh");
    setBusyMessage(null);
    try {
      const r = await triggerStockRefresh();
      startJob(r.job_id);
    } catch (e) {
      setBusyMessage(errMsg(e));
      setBusy(null);
    }
  };

  const onRetrain = async () => {
    resetJob();
    setBusy("retrain");
    setBusyMessage(null);
    try {
      const r = await triggerStockRetrain();
      startJob(r.job_id);
    } catch (e) {
      setBusyMessage(errMsg(e));
      setBusy(null);
    }
  };

  // Auto-refresh data when a job completes successfully.
  useEffect(() => {
    if (job && job.is_terminal) {
      setBusy(null);
      if (job.state === "completed") {
        void load();
      }
    }
  }, [job, load]);

  const universeCount = universe?.length ?? 0;
  const rankedCount = rankings?.length ?? 0;
  const topKCount = (rankings ?? []).filter((r) => r.in_topk).length;

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Stocks</h1>
          <p className="mt-1 text-sm text-slate-400">
            Universe size {universeCount} · Ranked today {rankedCount} · In top-K {topKCount}
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => void onRefresh()}
            disabled={busy !== null}
            className="rounded-md bg-emerald-600 px-3 py-2 text-xs font-semibold text-emerald-50 hover:bg-emerald-500 disabled:opacity-50"
          >
            {busy === "refresh" ? "Refreshing…" : "Refresh + rank"}
          </button>
          <button
            type="button"
            onClick={() => void onRetrain()}
            disabled={busy !== null}
            className="rounded-md bg-indigo-600 px-3 py-2 text-xs font-semibold text-indigo-50 hover:bg-indigo-500 disabled:opacity-50"
          >
            {busy === "retrain" ? "Retraining…" : "Retrain + backtest"}
          </button>
        </div>
      </header>

      {(job || jobError || busyMessage) ? (
        <div
          className={`rounded-md border p-3 text-xs ${
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
          ) : (
            <span>{busyMessage}</span>
          )}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <label className="text-xs text-slate-400">
          Sector
          <select
            value={sectorFilter}
            onChange={(e) => setSectorFilter(e.target.value)}
            className="ml-2 rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-slate-200"
          >
            {sectors.map((s) => (
              <option key={s} value={s}>
                {s === SECTOR_FILTER_ALL ? "All sectors" : s}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={topOnly}
            onChange={(e) => setTopOnly(e.target.checked)}
          />
          Top-K only
        </label>
      </div>

      {loading ? (
        <CardSkeletonGrid count={6} />
      ) : (
        <PageState
          error={error}
          onRetry={() => void load()}
          emptyMessage={
            rankedCount === 0
              ? "No rankings yet — run a refresh + retrain to populate the panel."
              : null
          }
        >
          <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-950/60">
            <table className="min-w-full divide-y divide-slate-900 text-sm">
              <thead className="bg-slate-900/60 text-left text-xs uppercase tracking-wide text-slate-400">
                <tr>
                  <th className="px-4 py-3">Rank</th>
                  <th className="px-4 py-3">Ticker</th>
                  <th className="px-4 py-3">Name</th>
                  <th className="px-4 py-3">Sector</th>
                  <th className="px-4 py-3 text-right">Score</th>
                  <th className="px-4 py-3 text-right">Last close</th>
                  <th className="px-4 py-3 text-center">In top-K</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-900 text-slate-200">
                {filteredRankings.map((r) => (
                  <tr
                    key={r.ticker}
                    className="cursor-pointer hover:bg-slate-900/60"
                    onClick={() => navigate(`/stocks/${encodeURIComponent(r.ticker)}`)}
                  >
                    <td className="px-4 py-2 font-mono text-xs text-slate-400">#{r.rank}</td>
                    <td className="px-4 py-2 font-semibold text-emerald-300">{r.ticker}</td>
                    <td className="px-4 py-2 text-slate-200">{r.name ?? r.ticker}</td>
                    <td className="px-4 py-2 text-slate-400">{r.sector ?? "—"}</td>
                    <td className="px-4 py-2 text-right font-mono">{r.score.toFixed(4)}</td>
                    <td className="px-4 py-2 text-right font-mono text-slate-300">
                      {r.last_close != null ? `$${r.last_close.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-4 py-2 text-center">
                      {r.in_topk ? (
                        <span className="rounded-full bg-emerald-900/40 px-2 py-0.5 text-xs text-emerald-200">
                          BUY
                        </span>
                      ) : (
                        <span className="text-xs text-slate-600">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </PageState>
      )}
    </main>
  );
}
