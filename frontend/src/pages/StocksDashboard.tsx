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
import { PageState } from "../components/PageState";
import { useJob } from "../hooks/useJob";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

const SECTOR_ALL = "__all__";

type SortKey = "rank" | "score" | "last_close";
type SortDir = "asc" | "desc";

export default function StocksDashboard(): ReactElement {
  const navigate = useNavigate();
  const [rankings, setRankings] = useState<StockRankingRow[] | null>(null);
  const [universe, setUniverse] = useState<StockUniverseRow[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sectorFilter, setSectorFilter] = useState(SECTOR_ALL);
  const [topOnly, setTopOnly] = useState(false);
  const [sortKey, setSortKey] = useState<SortKey>("rank");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
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

  useEffect(() => { void load(); }, [load]);

  const sectors = useMemo(() => {
    const set = new Set<string>();
    for (const row of universe ?? []) {
      if (row.sector) set.add(row.sector);
    }
    return [SECTOR_ALL, ...Array.from(set).sort()];
  }, [universe]);

  const rows = useMemo(() => {
    let list = [...(rankings ?? [])];
    if (topOnly) list = list.filter((r) => r.in_topk);
    if (sectorFilter !== SECTOR_ALL) list = list.filter((r) => r.sector === sectorFilter);
    list.sort((a, b) => {
      const mul = sortDir === "asc" ? 1 : -1;
      if (sortKey === "rank") return mul * (a.rank - b.rank);
      if (sortKey === "score") return mul * (a.score - b.score);
      if (sortKey === "last_close") return mul * ((a.last_close ?? 0) - (b.last_close ?? 0));
      return 0;
    });
    return list;
  }, [rankings, sectorFilter, topOnly, sortKey, sortDir]);

  const cycleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir(key === "rank" ? "asc" : "desc"); }
  };

  const onRefresh = async () => {
    resetJob(); setBusy("refresh"); setBusyMessage(null);
    try { startJob((await triggerStockRefresh()).job_id); }
    catch (e) { setBusyMessage(errMsg(e)); setBusy(null); }
  };

  const onRetrain = async () => {
    resetJob(); setBusy("retrain"); setBusyMessage(null);
    try { startJob((await triggerStockRetrain()).job_id); }
    catch (e) { setBusyMessage(errMsg(e)); setBusy(null); }
  };

  useEffect(() => {
    if (job && job.is_terminal) {
      setBusy(null);
      if (job.state === "completed") void load();
    }
  }, [job, load]);

  const universeCount = universe?.length ?? 0;
  const topKCount = (rankings ?? []).filter((r) => r.in_topk).length;

  const SortIcon = ({ col }: { col: SortKey }) =>
    sortKey === col ? (
      <span className="material-symbols-outlined text-[12px] leading-none text-secondary ml-1">
        {sortDir === "asc" ? "arrow_upward" : "arrow_downward"}
      </span>
    ) : null;

  const SortTh = ({ col, label, right }: { col: SortKey; label: string; right?: boolean }) => (
    <th
      className={`px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant cursor-pointer hover:text-on-surface transition-colors whitespace-nowrap ${right ? "text-right" : ""}`}
      onClick={() => cycleSort(col)}
    >
      {label}<SortIcon col={col} />
    </th>
  );

  return (
    <div className="p-6 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
            Universe {universeCount} · Ranked {rankings?.length ?? 0} · Top-K {topKCount}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void onRefresh()}
            disabled={busy !== null}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-secondary/40 text-secondary hover:bg-secondary/10 font-mono text-[10px] font-bold tracking-[0.06em] uppercase transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[14px] leading-none">refresh</span>
            {busy === "refresh" ? "Refreshing…" : "Refresh + Rank"}
          </button>
          <button
            type="button"
            onClick={() => void onRetrain()}
            disabled={busy !== null}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-outline-variant text-on-surface-variant hover:border-outline hover:text-on-surface font-mono text-[10px] font-bold tracking-[0.06em] uppercase transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[14px] leading-none">model_training</span>
            {busy === "retrain" ? "Retraining…" : "Retrain"}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setSectorFilter(SECTOR_ALL)}
          className={`px-3 py-1 font-mono text-[9px] font-bold tracking-[0.06em] uppercase border transition-colors ${
            sectorFilter === SECTOR_ALL
              ? "border-secondary/40 bg-secondary/10 text-secondary"
              : "border-outline-variant text-on-surface-variant hover:border-outline"
          }`}
        >
          All Sectors
        </button>
        {sectors.filter((s) => s !== SECTOR_ALL).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setSectorFilter(s)}
            className={`px-3 py-1 font-mono text-[9px] font-bold tracking-[0.06em] uppercase border transition-colors ${
              sectorFilter === s
                ? "border-secondary/40 bg-secondary/10 text-secondary"
                : "border-outline-variant text-on-surface-variant hover:border-outline"
            }`}
          >
            {s}
          </button>
        ))}
        <div className="ml-2 flex items-center gap-2">
          <input
            type="checkbox"
            checked={topOnly}
            onChange={(e) => setTopOnly(e.target.checked)}
            className="w-3 h-3 accent-secondary"
          />
          <span className="font-mono text-[10px] text-on-surface-variant uppercase tracking-[0.06em]">Top-K Only</span>
        </div>
      </div>

      {(job || jobError || busyMessage) && (
        <div className={`border px-3 py-2 font-mono text-[11px] ${
          job?.state === "failed" ? "border-error/30 bg-error/10 text-error"
          : job?.state === "completed" ? "border-secondary/30 bg-secondary/10 text-secondary"
          : "border-outline-variant text-on-surface-variant"
        }`}>
          {jobError ? `Polling error: ${jobError}` : busyMessage ?? (job ? (
            <span>
              <strong>{job.name}</strong> · {job.state}
              {job.message ? ` — ${job.message}` : ""}
              {isPolling ? <span className="ml-2 animate-pulse opacity-60">polling…</span> : null}
            </span>
          ) : null)}
        </div>
      )}

      <PageState
        error={error}
        onRetry={() => void load()}
        emptyMessage={!loading && (rankings?.length ?? 0) === 0 ? "No rankings yet — run Refresh + Rank." : null}
      >
        {loading ? (
          <div className="border border-outline-variant">
            {Array.from({ length: 10 }).map((_, i) => (
              <div key={i} className="border-b border-outline-variant px-4 py-3 flex gap-6">
                {[60, 100, 160, 100, 80, 80, 60].map((w, j) => (
                  <div key={j} className="h-3 bg-surface-container animate-pulse rounded" style={{ width: w }} />
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="border border-outline-variant bg-surface-container overflow-x-auto">
            <table className="w-full text-left">
              <thead className="border-b border-outline-variant bg-surface-container-high">
                <tr>
                  <SortTh col="rank" label="Rank" />
                  <th className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">Ticker</th>
                  <th className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">Name</th>
                  <th className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">Sector</th>
                  <SortTh col="score" label="Score" right />
                  <SortTh col="last_close" label="Last" right />
                  <th className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant text-center whitespace-nowrap">Signal</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant">
                {rows.map((r) => (
                  <tr
                    key={r.ticker}
                    className="cursor-pointer hover:bg-surface-container-high transition-colors"
                    onClick={() => navigate(`/stocks/${encodeURIComponent(r.ticker)}`)}
                  >
                    <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant tabular-nums">
                      #{r.rank}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-[13px] font-semibold text-secondary">{r.ticker}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface max-w-[180px] truncate">{r.name ?? r.ticker}</td>
                    <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant">{r.sector ?? "—"}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-right tabular-nums text-on-surface">{r.score.toFixed(4)}</td>
                    <td className="px-4 py-2.5 font-mono text-[12px] text-right tabular-nums text-on-surface">
                      {r.last_close != null ? `$${r.last_close.toFixed(2)}` : "—"}
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      {r.in_topk ? (
                        <span className="font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border border-secondary/30 bg-secondary/10 text-secondary">BUY</span>
                      ) : (
                        <span className="font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border border-outline-variant text-on-surface-variant">HOLD</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </PageState>
    </div>
  );
}
