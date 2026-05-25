/** Sortable/filterable rollup of persisted vectorbt summaries (21d preferred per API). */

import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiClientError, getBacktestSummary } from "../api/client";
import type { BacktestSummaryRow } from "../api/types.generated";
import { PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) {
    return e.message;
  }
  return "Unexpected error";
}

type SortKey = "sharpe_ratio" | "win_rate" | "total_return" | "num_trades" | "ticker";

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
      const data = await getBacktestSummary();
      setRows(data);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const processed = useMemo(() => {
    let out = [...rows];
    if (strictFilter) {
      out = out.filter((r) => r.sharpe_ratio > 1.0 && r.win_rate > 0.55);
    }
    out.sort((a, b) => {
      const mul = sortDir === "desc" ? -1 : 1;
      switch (sortKey) {
        case "ticker":
          return mul * a.ticker.localeCompare(b.ticker);
        default:
          return mul * ((a[sortKey] as number) - (b[sortKey] as number));
      }
    });
    return out;
  }, [rows, strictFilter, sortDir, sortKey]);

  const cycleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir(key === "ticker" ? "asc" : "desc");
    }
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <header className="mb-8 flex flex-col gap-4 border-b border-slate-800 pb-6 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-50">Backtest report</h1>
          <p className="mt-2 text-sm text-slate-400">Latest stored OOS-aligned vectorbt summaries.</p>
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={strictFilter}
            onChange={(e) => setStrictFilter(e.target.checked)}
            className="rounded border-slate-600 bg-slate-900"
          />
          Only Sharpe &gt; 1.0 and win rate &gt; 55%
        </label>
      </header>

      <PageState error={error} onRetry={() => void load()} emptyMessage={!loading && rows.length === 0 ? "No backtests yet." : null}>
        {loading ? (
          <div className="animate-pulse space-y-2">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-10 rounded bg-slate-800" />
            ))}
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full divide-y divide-slate-800 text-left text-sm">
              <thead className="bg-slate-900/80">
                <tr>
                  <th className="px-3 py-2 font-mono text-xs text-slate-400">
                    <SortButton active={sortKey === "ticker"} label="Ticker" onClick={() => cycleSort("ticker")} />
                  </th>
                  <th className="px-3 py-2 text-xs text-slate-400">Name</th>
                  <th className="px-3 py-2 font-mono text-xs text-slate-400">
                    <SortButton active={sortKey === "win_rate"} label="Win rate" onClick={() => cycleSort("win_rate")} />
                  </th>
                  <th className="px-3 py-2 font-mono text-xs text-slate-400">
                    <SortButton active={sortKey === "sharpe_ratio"} label="Sharpe" onClick={() => cycleSort("sharpe_ratio")} />
                  </th>
                  <th className="px-3 py-2 font-mono text-xs text-slate-400">Max DD</th>
                  <th className="px-3 py-2 font-mono text-xs text-slate-400">
                    <SortButton active={sortKey === "total_return"} label="Tot ret" onClick={() => cycleSort("total_return")} />
                  </th>
                  <th className="px-3 py-2 font-mono text-xs text-slate-400">
                    <SortButton active={sortKey === "num_trades"} label="Trades" onClick={() => cycleSort("num_trades")} />
                  </th>
                  <th className="px-3 py-2 font-mono text-xs text-slate-400">Run at</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-900">
                {processed.map((row) => (
                  <tr
                    key={`${row.ticker}-${row.horizon}`}
                    className="cursor-pointer bg-slate-950/40 hover:bg-slate-900/80"
                    onClick={() => navigate(`/commodity/${encodeURIComponent(row.ticker)}`)}
                  >
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-emerald-300">{row.ticker}</td>
                    <td className="px-3 py-2 text-slate-200">{row.name}</td>
                    <td className="px-3 py-2 font-mono">{(row.win_rate * 100).toFixed(1)}%</td>
                    <td className="px-3 py-2 font-mono">{row.sharpe_ratio.toFixed(2)}</td>
                    <td className="px-3 py-2 font-mono">{row.max_drawdown.toFixed(2)}</td>
                    <td className="px-3 py-2 font-mono">{row.total_return.toFixed(3)}</td>
                    <td className="px-3 py-2 font-mono">{row.num_trades}</td>
                    <td className="whitespace-nowrap px-3 py-2 font-mono text-xs text-slate-500">{row.run_at ?? "—"}</td>
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

function SortButton({
  label,
  onClick,
  active,
}: {
  label: string;
  onClick: () => void;
  active: boolean;
}): ReactElement {
  return (
    <button type="button" className={`${active ? "text-emerald-300" : "text-slate-400"} underline-offset-4 hover:underline`} onClick={onClick}>
      {label}
    </button>
  );
}
