import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiClientError, getBacktestSummary } from "../api/client";
import type { BacktestSummaryRow } from "../api/types.generated";
import { PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

type SortKey = "sharpe_ratio" | "win_rate" | "total_return" | "num_trades" | "ticker";

function pct(n: number): string { return `${(n * 100).toFixed(1)}%`; }

export default function BacktestReport(): ReactElement {
  const navigate = useNavigate();
  const [rows, setRows] = useState<BacktestSummaryRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("sharpe_ratio");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [strictFilter, setStrictFilter] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setRows(await getBacktestSummary());
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const processed = useMemo(() => {
    let out = [...rows];
    if (strictFilter) out = out.filter((r) => r.sharpe_ratio > 1.0 && r.win_rate > 0.55);
    out.sort((a, b) => {
      const mul = sortDir === "desc" ? -1 : 1;
      if (sortKey === "ticker") return mul * a.ticker.localeCompare(b.ticker);
      return mul * ((a[sortKey] as number) - (b[sortKey] as number));
    });
    return out;
  }, [rows, strictFilter, sortDir, sortKey]);

  const cycleSort = (key: SortKey) => {
    if (sortKey === key) setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    else { setSortKey(key); setSortDir(key === "ticker" ? "asc" : "desc"); }
  };

  const avgSharpe = rows.length > 0 ? (rows.reduce((s, r) => s + r.sharpe_ratio, 0) / rows.length).toFixed(2) : "—";
  const avgWinRate = rows.length > 0 ? pct(rows.reduce((s, r) => s + r.win_rate, 0) / rows.length) : "—";
  const totalTrades = rows.reduce((s, r) => s + r.num_trades, 0);

  const Th = ({ col, label, right }: { col: SortKey; label: string; right?: boolean }) => (
    <th
      className={`px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant cursor-pointer hover:text-on-surface transition-colors whitespace-nowrap ${right ? "text-right" : ""}`}
      onClick={() => cycleSort(col)}
    >
      {label}
      {sortKey === col && (
        <span className="material-symbols-outlined text-[11px] leading-none text-secondary ml-1">
          {sortDir === "asc" ? "arrow_upward" : "arrow_downward"}
        </span>
      )}
    </th>
  );

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between border-b border-outline-variant pb-4">
        <div>
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Backtest Report</p>
          <p className="font-mono text-[10px] text-on-surface-variant opacity-60 mt-0.5">
            Out-of-sample vectorbt summaries · {rows.length} instruments
          </p>
        </div>
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={strictFilter}
            onChange={(e) => setStrictFilter(e.target.checked)}
            className="w-3 h-3 accent-secondary"
          />
          <span className="font-mono text-[10px] font-bold tracking-[0.06em] uppercase text-on-surface-variant">
            Sharpe &gt; 1.0 · Win &gt; 55%
          </span>
        </label>
      </div>

      {!loading && rows.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { label: "Avg Sharpe", value: avgSharpe },
            { label: "Avg Win Rate", value: avgWinRate },
            { label: "Total Trades", value: totalTrades.toLocaleString() },
          ].map((s) => (
            <div key={s.label} className="border border-outline-variant bg-surface-container p-4">
              <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">{s.label}</p>
              <p className="mt-2 font-mono text-xl font-semibold text-on-surface">{s.value}</p>
            </div>
          ))}
        </div>
      )}

      <PageState error={error} onRetry={() => void load()} emptyMessage={!loading && rows.length === 0 ? "No backtests yet." : null}>
        {loading ? (
          <div className="border border-outline-variant">
            {Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="border-b border-outline-variant px-4 py-3 flex gap-6">
                {[60, 120, 80, 70, 70, 80, 70, 100].map((w, j) => (
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
                  <Th col="ticker" label="Ticker" />
                  <th className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">Name</th>
                  <Th col="win_rate" label="Win Rate" right />
                  <Th col="sharpe_ratio" label="Sharpe" right />
                  <th className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant text-right whitespace-nowrap">Max DD</th>
                  <Th col="total_return" label="Tot Ret" right />
                  <Th col="num_trades" label="Trades" right />
                  <th className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">Run At</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-outline-variant">
                {processed.map((row) => {
                  const goodSharpe = row.sharpe_ratio > 1.0;
                  const goodWin = row.win_rate > 0.55;
                  return (
                    <tr
                      key={`${row.ticker}-${row.horizon}`}
                      className="cursor-pointer hover:bg-surface-container-high transition-colors"
                      onClick={() => navigate(`/commodity/${encodeURIComponent(row.ticker)}`)}
                    >
                      <td className="px-4 py-2.5 font-mono text-[13px] font-semibold text-secondary">{row.ticker}</td>
                      <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface max-w-[140px] truncate">{row.name}</td>
                      <td className={`px-4 py-2.5 font-mono text-[12px] text-right tabular-nums ${goodWin ? "text-secondary" : "text-on-surface"}`}>
                        {pct(row.win_rate)}
                      </td>
                      <td className={`px-4 py-2.5 font-mono text-[12px] text-right tabular-nums ${goodSharpe ? "text-secondary" : "text-on-surface"}`}>
                        {row.sharpe_ratio.toFixed(2)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-[12px] text-right tabular-nums text-error">
                        {row.max_drawdown.toFixed(2)}
                      </td>
                      <td className={`px-4 py-2.5 font-mono text-[12px] text-right tabular-nums ${row.total_return > 0 ? "text-secondary" : "text-error"}`}>
                        {row.total_return.toFixed(3)}
                      </td>
                      <td className="px-4 py-2.5 font-mono text-[12px] text-right tabular-nums text-on-surface">{row.num_trades}</td>
                      <td className="px-4 py-2.5 font-mono text-[10px] text-on-surface-variant whitespace-nowrap">
                        {row.run_at ?? "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </PageState>
    </div>
  );
}
