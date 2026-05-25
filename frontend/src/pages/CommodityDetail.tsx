/** Commodity drill-down: signal recap, price + SHAP charts, backtest tiles, IBKR disclaimer. */

import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiClientError, getBacktestDetail, getCommodityHistory, getSignalDetail } from "../api/client";
import type { SignalPayload, BacktestStatsBlock } from "../api/types.generated";
import { DetailSkeleton, PageState } from "../components/PageState";
import { SignalCard } from "../components/SignalCard";
import {
  CHART_AXIS,
  CHART_GRID,
  CHART_NEGATIVE,
  CHART_PRIMARY,
  tooltipOuterStyle,
} from "../theme/charts";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) {
    return e.message;
  }
  return "Unexpected error";
}

export default function CommodityDetail(): ReactElement {
  const params = useParams<{ ticker: string }>();
  const navigate = useNavigate();
  const ticker = decodeURIComponent(params.ticker ?? "");

  const [signal, setSignal] = useState<SignalPayload | null>(null);
  const [history, setHistory] = useState<{ date: string; close: number }[]>([]);
  const [backtest, setBacktest] = useState<BacktestStatsBlock | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!ticker) {
      setError("Missing ticker.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [sig, hist, bt] = await Promise.all([
        getSignalDetail(ticker),
        getCommodityHistory(ticker, 180),
        getBacktestDetail(ticker),
      ]);
      setSignal(sig);
      setHistory(hist);
      setBacktest(bt);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => {
    void load();
  }, [load]);

  const chartPoints = useMemo(() => history.map((h) => ({ date: h.date.slice(0, 10), px: h.close })), [history]);

  const shapData = useMemo(() => {
    const rows = signal?.shap_features ?? [];
    return [...rows].sort((a, b) => Math.abs(b.importance) - Math.abs(a.importance)).slice(0, 10);
  }, [signal]);

  const winPct = backtest ? Math.round(backtest.win_rate * 100) : 0;
  const kellyPct = signal ? (signal.position_size_pct * 100).toFixed(1) : "0";

  const kellyExplain =
    signal && signal.signal === "BUY"
      ? `Based on this commodity's historical ${winPct}% win rate, allocate approximately ${kellyPct}% of your portfolio to this position (Kelly sizing with safeguards).`
      : "Kelly sizing applies only when the ensemble consensus is BUY.";

  return (
    <div className="mx-auto max-w-7xl px-4 py-8">
      <button type="button" className="mb-6 text-sm text-emerald-400 hover:underline" onClick={() => navigate("/")}>
        ← Dashboard
      </button>

      {loading ? <DetailSkeleton /> : null}

      <PageState error={error} onRetry={() => void load()} emptyMessage={!loading && !signal ? "Signal not found." : null}>
        {signal ? (
          <div className="space-y-8">
            <section className="max-w-xl">
              <SignalCard signal={signal} muted={false} interactive={false} onOpen={() => undefined} />
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <h3 className="font-semibold text-slate-200">180-day spot / continuous</h3>
              <div className="mt-4 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={chartPoints}>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                    <XAxis dataKey="date" tick={{ fill: CHART_AXIS }} />
                    <YAxis tick={{ fill: CHART_AXIS }} domain={["auto", "auto"]} />
                    <Tooltip contentStyle={tooltipOuterStyle} />
                    <Legend />
                    <Line type="monotone" dataKey="px" name="Close" stroke={CHART_PRIMARY} strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
              <h3 className="font-semibold text-slate-200">SHAP importance (tree leg)</h3>
              <div className="mt-4 h-96">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart layout="vertical" data={shapData} margin={{ left: 12, right: 24 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke={CHART_GRID} />
                    <XAxis type="number" tick={{ fill: CHART_AXIS }} />
                    <YAxis type="category" dataKey="feature" width={140} tick={{ fill: CHART_AXIS }} />
                    <Tooltip contentStyle={tooltipOuterStyle} />
                    <Bar dataKey="importance" fill={CHART_NEGATIVE} radius={[0, 4, 4, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>

            <section>
              <h3 className="mb-3 font-semibold text-slate-200">Backtest (latest stored run)</h3>
              {backtest ? (
                <div className="grid gap-3 md:grid-cols-3">
                  <Stat label="Win rate" value={`${(backtest.win_rate * 100).toFixed(1)}%`} />
                  <Stat label="Sharpe ratio" value={backtest.sharpe_ratio.toFixed(2)} />
                  <Stat label="Max drawdown" value={backtest.max_drawdown.toFixed(2)} />
                  <Stat
                    label="Total return"
                    value={
                      backtest.total_return !== undefined ? backtest.total_return.toFixed(3) : "—"
                    }
                  />
                  <Stat label="Trade count" value={String(backtest.num_trades)} />
                </div>
              ) : null}
            </section>

            <p className="text-sm text-slate-400">{kellyExplain}</p>

            <p className="rounded-md border border-slate-800 bg-slate-900/70 p-4 text-sm text-slate-300">
              Execute manually in Interactive Brokers TWS or web portal. Suggested symbol:{" "}
              <span className="font-mono text-emerald-300">{ticker}</span>. Target hold: 21–30 trading days.
            </p>
          </div>
        ) : null}
      </PageState>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }): ReactElement {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/80 p-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 font-mono text-xl text-slate-100">{value}</p>
    </div>
  );
}
