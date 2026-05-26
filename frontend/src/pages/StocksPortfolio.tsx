import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiClientError, getStockBacktest, getStockPortfolio } from "../api/client";
import type { StockBacktestSummary, StockPortfolioResponse } from "../api/types.generated";
import { PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function num(n: number | null | undefined, digits = 2): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
}

function Stat({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="border border-outline-variant bg-surface-container p-4">
      <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">{label}</p>
      <p className={`mt-2 font-mono text-xl font-semibold ${
        positive === true ? "text-secondary" : positive === false ? "text-error" : "text-on-surface"
      }`}>
        {value}
      </p>
    </div>
  );
}

export default function StocksPortfolio(): ReactElement {
  const navigate = useNavigate();
  const [portfolio, setPortfolio] = useState<StockPortfolioResponse | null>(null);
  const [backtest, setBacktest] = useState<StockBacktestSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [p, b] = await Promise.all([
        getStockPortfolio(540),
        getStockBacktest().catch(() => null),
      ]);
      setPortfolio(p);
      setBacktest(b);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const equityData = useMemo(() =>
    (portfolio?.equity_curve ?? []).map((p) => ({
      date: p.date,
      strategy: Number(p.equity),
      benchmark: p.benchmark_equity != null ? Number(p.benchmark_equity) : null,
    })),
  [portfolio]);

  const holdings = useMemo(() =>
    [...(portfolio?.holdings ?? [])].sort((a, b) => b.weight - a.weight),
  [portfolio]);

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between border-b border-outline-variant pb-4">
        <div>
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Portfolio Overview</p>
          {portfolio?.as_of && (
            <p className="font-mono text-[10px] text-on-surface-variant opacity-60 mt-0.5">
              Last rebalance: {portfolio.as_of}
            </p>
          )}
        </div>
        <span className="font-mono text-[10px] text-on-surface-variant">{holdings.length} active positions</span>
      </div>

      <PageState error={error} onRetry={() => void load()}>
        {loading ? (
          <div className="space-y-4">
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map((i) => <div key={i} className="h-20 border border-outline-variant bg-surface-container animate-pulse" />)}
            </div>
            <div className="h-64 border border-outline-variant bg-surface-container animate-pulse" />
          </div>
        ) : (
          <>
            {backtest ? (
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                <Stat
                  label="Total Return"
                  value={pct(backtest.total_return)}
                  positive={backtest.total_return != null ? backtest.total_return > 0 : undefined}
                />
                <Stat label="Sharpe" value={num(backtest.sharpe_ratio)} />
                <Stat
                  label="Max Drawdown"
                  value={pct(backtest.max_drawdown)}
                  positive={false}
                />
                <Stat label="Win Rate" value={pct(backtest.win_rate)} positive={backtest.win_rate != null ? backtest.win_rate > 0.5 : undefined} />
                <Stat
                  label="vs Benchmark"
                  value={pct(backtest.benchmark_total_return)}
                />
                <Stat label="Info Ratio" value={num(backtest.info_ratio_vs_benchmark)} />
                <Stat label="Rebalances" value={String(backtest.num_rebalances)} />
                <Stat label="Horizon" value={backtest.horizon} />
              </div>
            ) : (
              <div className="border border-outline-variant bg-surface-container px-4 py-3 font-mono text-[11px] text-on-surface-variant">
                No backtest data — run "Retrain + Backtest" from the Equities screen.
              </div>
            )}

            <div className="border border-outline-variant bg-surface-container">
              <div className="px-4 py-3 border-b border-outline-variant">
                <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Equity Curve</p>
              </div>
              <div className="p-4 h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={equityData} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                    <CartesianGrid stroke="#444748" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="date" stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" minTickGap={40} />
                    <YAxis stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} />
                    <Tooltip
                      contentStyle={{ background: "#1f2020", border: "1px solid #444748", color: "#e5e2e1", fontFamily: "JetBrains Mono", fontSize: 11 }}
                      formatter={(v: number) => [`$${v.toFixed(0)}`]}
                    />
                    <Legend wrapperStyle={{ color: "#c4c7c8", fontSize: 10, fontFamily: "JetBrains Mono" }} />
                    <Line type="monotone" dataKey="strategy" name="Top-K Strategy" stroke="#5cde94" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="benchmark" name="SPY Benchmark" stroke="#8e9192" strokeDasharray="4 4" strokeWidth={1.5} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="border border-outline-variant bg-surface-container">
              <div className="flex items-center justify-between px-4 py-3 border-b border-outline-variant">
                <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Current Holdings</p>
                <span className="font-mono text-[10px] text-on-surface-variant">{holdings.length} positions</span>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left">
                  <thead className="border-b border-outline-variant bg-surface-container-high">
                    <tr>
                      {["TICKER", "NAME", "SECTOR", "WEIGHT", "LAST PRICE"].map((h) => (
                        <th key={h} className="px-4 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-outline-variant">
                    {holdings.map((h) => (
                      <tr
                        key={h.ticker}
                        className="cursor-pointer hover:bg-surface-container-high transition-colors"
                        onClick={() => navigate(`/stocks/${encodeURIComponent(h.ticker)}`)}
                      >
                        <td className="px-4 py-2.5 font-mono text-[13px] font-semibold text-secondary">{h.ticker}</td>
                        <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface max-w-[180px] truncate">{h.name ?? h.ticker}</td>
                        <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant">{h.sector ?? "—"}</td>
                        <td className="px-4 py-2.5 font-mono text-[12px] tabular-nums text-on-surface">{pct(h.weight)}</td>
                        <td className="px-4 py-2.5 font-mono text-[12px] tabular-nums text-on-surface">
                          {h.last_price != null ? `$${h.last_price.toFixed(2)}` : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </PageState>
    </div>
  );
}
