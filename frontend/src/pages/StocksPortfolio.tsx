/** Stocks portfolio: current top-K holdings + equity curve vs SPY benchmark. */

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
import type {
  StockBacktestSummary,
  StockPortfolioResponse,
} from "../api/types.generated";
import { DetailSkeleton, PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

function pct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function num(n: number | null | undefined, digits = 3): string {
  if (n == null || Number.isNaN(n)) return "—";
  return n.toFixed(digits);
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

  useEffect(() => {
    void load();
  }, [load]);

  const equityData = useMemo(() => {
    const list = portfolio?.equity_curve ?? [];
    return list.map((p) => ({
      date: p.date,
      strategy: Number(p.equity),
      benchmark: p.benchmark_equity != null ? Number(p.benchmark_equity) : null,
    }));
  }, [portfolio]);

  const holdings = useMemo(() => {
    const list = portfolio?.holdings ?? [];
    return [...list].sort((a, b) => b.weight - a.weight);
  }, [portfolio]);

  if (loading) {
    return (
      <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
        <DetailSkeleton />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-slate-100">Portfolio</h1>
        <p className="mt-1 text-sm text-slate-400">
          Top-K cross-sectional ranker portfolio. Equity curve and metrics computed from the most
          recent walk-forward backtest.
          {portfolio?.as_of ? ` Latest rebalance: ${portfolio.as_of}.` : ""}
        </p>
      </header>

      <PageState error={error} onRetry={() => void load()}>
        {backtest ? (
          <section className="grid gap-4 md:grid-cols-4">
            {[
              { label: "Total return", value: pct(backtest.total_return) },
              { label: "Sharpe", value: num(backtest.sharpe_ratio, 2) },
              { label: "Max drawdown", value: pct(backtest.max_drawdown) },
              { label: "Win rate", value: pct(backtest.win_rate) },
              { label: "Benchmark return", value: pct(backtest.benchmark_total_return) },
              { label: "Info ratio vs SPY", value: num(backtest.info_ratio_vs_benchmark, 2) },
              { label: "Rebalances", value: String(backtest.num_rebalances) },
              { label: "Horizon", value: backtest.horizon },
            ].map((m) => (
              <div
                key={m.label}
                className="rounded-xl border border-slate-800 bg-slate-950/60 p-4"
              >
                <p className="text-xs uppercase tracking-wide text-slate-500">{m.label}</p>
                <p className="mt-1 text-lg font-semibold text-slate-100">{m.value}</p>
              </div>
            ))}
          </section>
        ) : (
          <div className="rounded-md border border-slate-800 bg-slate-900/40 p-3 text-xs text-slate-400">
            No portfolio backtest yet — run "Retrain + backtest" from the Stocks dashboard.
          </div>
        )}

        <section className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
          <h2 className="text-sm font-semibold text-slate-200">Equity curve</h2>
          <div className="mt-2 h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equityData} margin={{ top: 6, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                <XAxis dataKey="date" stroke="#64748b" fontSize={11} minTickGap={36} />
                <YAxis stroke="#64748b" fontSize={11} tickFormatter={(v) => `$${Math.round(Number(v) / 1000)}k`} />
                <Tooltip
                  contentStyle={{ background: "#020617", border: "1px solid #1e293b", color: "#e2e8f0" }}
                  formatter={(v: number) =>
                    typeof v === "number"
                      ? `$${v.toFixed(0)}`
                      : v
                  }
                />
                <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 11 }} />
                <Line
                  type="monotone"
                  dataKey="strategy"
                  name="Top-K strategy"
                  stroke="#34d399"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  name="SPY benchmark"
                  stroke="#94a3b8"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="rounded-xl border border-slate-800 bg-slate-950/60">
          <header className="flex items-center justify-between border-b border-slate-900 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-200">Current holdings</h2>
            <span className="text-xs text-slate-500">{holdings.length} positions</span>
          </header>
          <table className="min-w-full divide-y divide-slate-900 text-sm">
            <thead className="bg-slate-900/40 text-left text-xs uppercase tracking-wide text-slate-400">
              <tr>
                <th className="px-4 py-3">Ticker</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">Sector</th>
                <th className="px-4 py-3 text-right">Weight</th>
                <th className="px-4 py-3 text-right">Last price</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-900 text-slate-200">
              {holdings.map((h) => (
                <tr
                  key={h.ticker}
                  className="cursor-pointer hover:bg-slate-900/60"
                  onClick={() => navigate(`/stocks/${encodeURIComponent(h.ticker)}`)}
                >
                  <td className="px-4 py-2 font-semibold text-emerald-300">{h.ticker}</td>
                  <td className="px-4 py-2">{h.name ?? h.ticker}</td>
                  <td className="px-4 py-2 text-slate-400">{h.sector ?? "—"}</td>
                  <td className="px-4 py-2 text-right font-mono">{pct(h.weight)}</td>
                  <td className="px-4 py-2 text-right font-mono text-slate-300">
                    {h.last_price != null ? `$${h.last_price.toFixed(2)}` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </PageState>
    </main>
  );
}
