import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiClientError, getBacktestDetail, getCommodityCot, getCommodityHistory, getSignalDetail } from "../api/client";
import type { BacktestStatsBlock, CotResponse, SignalPayload } from "../api/types.generated";
import { PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

function MetricRow({ label, value, colored }: { label: string; value: string; colored?: "green" | "red" }) {
  return (
    <div className="flex items-center justify-between py-2 border-b border-outline-variant last:border-0">
      <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">{label}</span>
      <span className={`font-mono text-[12px] font-semibold tabular-nums ${
        colored === "green" ? "text-secondary" : colored === "red" ? "text-error" : "text-on-surface"
      }`}>{value}</span>
    </div>
  );
}

export default function CommodityDetail(): ReactElement {
  const params = useParams<{ ticker: string }>();
  const navigate = useNavigate();
  const ticker = decodeURIComponent(params.ticker ?? "");

  const [signal, setSignal] = useState<SignalPayload | null>(null);
  const [history, setHistory] = useState<{ date: string; close: number }[]>([]);
  const [backtest, setBacktest] = useState<BacktestStatsBlock | null>(null);
  const [cot, setCot] = useState<CotResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!ticker) { setError("Missing ticker."); setLoading(false); return; }
    setLoading(true);
    setError(null);
    try {
      const [sig, hist, bt, cotData] = await Promise.all([
        getSignalDetail(ticker),
        getCommodityHistory(ticker, 180),
        getBacktestDetail(ticker),
        getCommodityCot(ticker).catch(() => null),
      ]);
      setSignal(sig);
      setHistory(hist);
      setBacktest(bt);
      setCot(cotData);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { void load(); }, [load]);

  const chartPoints = useMemo(() =>
    history.map((h) => ({ date: h.date.slice(0, 10), px: h.close })),
  [history]);

  const shapData = useMemo(() =>
    [...(signal?.shap_features ?? [])]
      .sort((a, b) => Math.abs(b.importance) - Math.abs(a.importance))
      .slice(0, 10),
  [signal]);

  const kellyPct = signal ? (signal.position_size_pct * 100).toFixed(1) : "0";

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-2 mb-2">
        <button
          type="button"
          onClick={() => navigate("/commodities")}
          className="flex items-center gap-1 font-mono text-[10px] font-bold uppercase tracking-[0.06em] text-on-surface-variant hover:text-on-surface transition-colors"
        >
          <span className="material-symbols-outlined text-[14px] leading-none">arrow_back</span>
          Commodities
        </button>
      </div>

      <PageState error={error} onRetry={() => void load()} emptyMessage={!loading && !signal ? "Signal not found." : null}>
        {loading ? (
          <div className="space-y-4">
            <div className="h-8 w-48 bg-surface-container animate-pulse" />
            <div className="h-64 border border-outline-variant bg-surface-container animate-pulse" />
          </div>
        ) : signal ? (
          <div className="space-y-4">
            <div className="border-b border-outline-variant pb-4">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-xl font-bold text-on-surface">{signal.ticker}</span>
                <span className="font-mono text-[13px] text-on-surface-variant">{signal.name}</span>
                <span className={`ml-2 font-mono text-[11px] font-bold tracking-[0.06em] px-2 py-0.5 border ${
                  signal.signal === "BUY"
                    ? "border-secondary/30 bg-secondary/10 text-secondary"
                    : "border-outline-variant text-on-surface-variant"
                }`}>
                  {signal.signal}
                </span>
              </div>
              <p className="font-mono text-[11px] text-on-surface-variant mt-1">
                Confidence {signal.avg_confidence.toFixed(3)} · Regime {signal.regime_label} · Kelly size {kellyPct}%
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-4">
                <div className="border border-outline-variant bg-surface-container">
                  <div className="px-4 py-3 border-b border-outline-variant">
                    <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Price History (180d)</p>
                  </div>
                  <div className="p-4 h-60">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={chartPoints} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                        <CartesianGrid stroke="#444748" strokeDasharray="2 4" vertical={false} />
                        <XAxis dataKey="date" stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" minTickGap={40} />
                        <YAxis stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" domain={["auto", "auto"]} tickFormatter={(v) => `$${Number(v).toFixed(0)}`} />
                        <Tooltip contentStyle={{ background: "#1f2020", border: "1px solid #444748", color: "#e5e2e1", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                        <Line type="monotone" dataKey="px" name="Close" stroke="#5cde94" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>

                {shapData.length > 0 && (
                  <div className="border border-outline-variant bg-surface-container">
                    <div className="px-4 py-3 border-b border-outline-variant">
                      <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">SHAP Feature Importance</p>
                    </div>
                    <div className="p-4 h-72">
                      <ResponsiveContainer width="100%" height="100%">
                        <BarChart layout="vertical" data={shapData} margin={{ left: 0, right: 16 }}>
                          <CartesianGrid stroke="#444748" strokeDasharray="2 4" horizontal={false} />
                          <XAxis type="number" stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" />
                          <YAxis type="category" dataKey="feature" width={120} stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" />
                          <Tooltip contentStyle={{ background: "#1f2020", border: "1px solid #444748", color: "#e5e2e1", fontFamily: "JetBrains Mono", fontSize: 11 }} />
                          <Bar dataKey="importance" fill="#5cde94" radius={0} />
                        </BarChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                )}

                {cot && cot.history.length > 1 && (() => {
                  const cotPoints = cot.history
                    .filter((h) => h.spec_pct_long !== null)
                    .map((h) => ({ date: h.report_date.slice(0, 10), specLong: +(h.spec_pct_long! * 100).toFixed(1) }));
                  return cotPoints.length > 1 ? (
                    <div className="border border-outline-variant bg-surface-container">
                      <div className="px-4 py-3 border-b border-outline-variant">
                        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">COT Speculative Long %</p>
                      </div>
                      <div className="p-4 h-48">
                        <ResponsiveContainer width="100%" height="100%">
                          <LineChart data={cotPoints} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                            <CartesianGrid stroke="#444748" strokeDasharray="2 4" vertical={false} />
                            <XAxis dataKey="date" stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" minTickGap={60} />
                            <YAxis stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" domain={[0, 100]} tickFormatter={(v) => `${v}%`} />
                            <Tooltip contentStyle={{ background: "#1f2020", border: "1px solid #444748", color: "#e5e2e1", fontFamily: "JetBrains Mono", fontSize: 11 }} formatter={(v) => [`${v}%`, "Spec Long"]} />
                            <Line type="monotone" dataKey="specLong" name="Spec Long %" stroke="#5cde94" strokeWidth={2} dot={false} />
                          </LineChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  ) : null;
                })()}
              </div>

              <div className="space-y-3">
                <div className="border border-outline-variant bg-surface-container">
                  <div className="px-4 py-3 border-b border-outline-variant">
                    <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Signal Metrics</p>
                  </div>
                  <div className="px-4 py-2">
                    <MetricRow label="Signal" value={signal.signal} colored={signal.signal === "BUY" ? "green" : undefined} />
                    <MetricRow label="Avg Confidence" value={signal.avg_confidence.toFixed(3)} />
                    <MetricRow label="5d Confidence" value={signal.confidence_5d.toFixed(3)} />
                    <MetricRow label="10d Confidence" value={signal.confidence_10d.toFixed(3)} />
                    <MetricRow label="21d Confidence" value={signal.confidence_21d.toFixed(3)} />
                    <MetricRow label="Sentiment" value={signal.sentiment.label} />
                    <MetricRow label="Sent. Score 1d" value={signal.sentiment.score_1d.toFixed(3)} />
                    <MetricRow label="Kelly Size" value={`${kellyPct}%`} />
                    <MetricRow label="Regime" value={signal.regime_label} />
                    {signal.expected_return_pct !== undefined && (
                      <MetricRow
                        label="Expected Return"
                        value={`${(signal.expected_return_pct * 100).toFixed(2)}%`}
                        colored={signal.expected_return_pct > 0 ? "green" : "red"}
                      />
                    )}
                    {signal.downside_risk_pct !== undefined && (
                      <MetricRow
                        label="Downside Risk"
                        value={`${(signal.downside_risk_pct * 100).toFixed(2)}%`}
                        colored="red"
                      />
                    )}
                    {signal.risk_flags && signal.risk_flags.length > 0 && (
                      <div className="py-2 border-b border-outline-variant last:border-0">
                        <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-on-surface-variant block mb-1">Risk Flags</span>
                        <div className="flex flex-wrap gap-1">
                          {signal.risk_flags.map((flag) => (
                            <span key={flag} className="font-mono text-[9px] px-1.5 py-0.5 border border-error/30 bg-error/10 text-error">
                              {flag}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {backtest && (
                  <div className="border border-outline-variant bg-surface-container">
                    <div className="px-4 py-3 border-b border-outline-variant">
                      <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Backtest</p>
                    </div>
                    <div className="px-4 py-2">
                      <MetricRow label="Win Rate" value={`${(backtest.win_rate * 100).toFixed(1)}%`} colored={backtest.win_rate > 0.55 ? "green" : undefined} />
                      <MetricRow label="Sharpe" value={backtest.sharpe_ratio.toFixed(2)} colored={backtest.sharpe_ratio > 1 ? "green" : undefined} />
                      <MetricRow label="Max Drawdown" value={backtest.max_drawdown.toFixed(3)} colored="red" />
                      {backtest.total_return !== undefined && (
                        <MetricRow label="Total Return" value={backtest.total_return.toFixed(3)} colored={backtest.total_return > 0 ? "green" : "red"} />
                      )}
                      <MetricRow label="Trades" value={String(backtest.num_trades)} />
                    </div>
                  </div>
                )}

                {cot?.latest && (
                  <div className="border border-outline-variant bg-surface-container">
                    <div className="px-4 py-3 border-b border-outline-variant">
                      <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">COT Positioning</p>
                      <p className="font-mono text-[9px] text-on-surface-variant opacity-60 mt-0.5">as of {cot.latest.report_date}</p>
                    </div>
                    <div className="px-4 py-2">
                      {cot.latest.spec_pct_long !== null && (
                        <div className="py-2 border-b border-outline-variant">
                          <div className="flex justify-between mb-1">
                            <span className="font-mono text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">Spec Long %</span>
                            <span className={`font-mono text-[12px] font-semibold ${cot.latest.spec_pct_long > 0.6 ? "text-secondary" : cot.latest.spec_pct_long < 0.4 ? "text-error" : "text-on-surface"}`}>
                              {(cot.latest.spec_pct_long * 100).toFixed(1)}%
                            </span>
                          </div>
                          <div className="w-full h-1.5 bg-surface-container-high rounded-none overflow-hidden">
                            <div className="h-full bg-secondary" style={{ width: `${Math.round(cot.latest.spec_pct_long * 100)}%` }} />
                          </div>
                        </div>
                      )}
                      <MetricRow label="Comm. Net" value={cot.latest.comm_net !== null ? cot.latest.comm_net.toLocaleString() : "—"} colored={cot.latest.comm_net !== null && cot.latest.comm_net > 0 ? "green" : "red"} />
                      <MetricRow label="Spec. Net" value={cot.latest.spec_net !== null ? cot.latest.spec_net.toLocaleString() : "—"} colored={cot.latest.spec_net !== null && cot.latest.spec_net > 0 ? "green" : "red"} />
                      <MetricRow label="Open Interest" value={cot.latest.open_interest !== null ? cot.latest.open_interest.toLocaleString() : "—"} />
                    </div>
                  </div>
                )}

                <div className="border border-outline-variant bg-surface-container px-4 py-3">
                  <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant mb-2">Execution Note</p>
                  <p className="font-mono text-[11px] text-on-surface-variant leading-relaxed">
                    Execute via IBKR TWS or web portal. Symbol:{" "}
                    <span className="text-secondary">{ticker}</span>.
                    Target hold: 21–30 trading days.
                  </p>
                </div>
              </div>
            </div>
          </div>
        ) : null}
      </PageState>
    </div>
  );
}
