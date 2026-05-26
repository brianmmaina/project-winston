import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiClientError, getStockDetail, getStockHistory } from "../api/client";
import type { HistoryBar, StockDetailResponse } from "../api/types.generated";
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
      }`}>
        {value}
      </span>
    </div>
  );
}

export default function StockDetail(): ReactElement {
  const { ticker } = useParams<{ ticker: string }>();
  const [detail, setDetail] = useState<StockDetailResponse | null>(null);
  const [history, setHistory] = useState<HistoryBar[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!ticker) return;
    setLoading(true);
    setError(null);
    try {
      const [d, h] = await Promise.all([
        getStockDetail(ticker),
        getStockHistory(ticker, 365),
      ]);
      setDetail(d);
      setHistory(h);
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, [ticker]);

  useEffect(() => { void load(); }, [load]);

  const first = history?.[0]?.close;
  const last = history?.[history.length - 1]?.close;
  const pctChange = first && last ? ((last - first) / first) * 100 : null;

  return (
    <div className="p-6 space-y-4">
      <PageState error={error} onRetry={() => void load()}>
        {loading ? (
          <div className="space-y-4">
            <div className="h-8 w-48 bg-surface-container animate-pulse" />
            <div className="grid grid-cols-3 gap-3">
              {[1, 2, 3].map((i) => <div key={i} className="h-20 border border-outline-variant bg-surface-container animate-pulse" />)}
            </div>
            <div className="h-64 border border-outline-variant bg-surface-container animate-pulse" />
          </div>
        ) : detail ? (
          <>
            <div className="border-b border-outline-variant pb-4">
              <div className="flex items-baseline gap-3">
                <span className="font-mono text-xl font-bold text-on-surface">{detail.ticker}</span>
                <span className="font-mono text-[13px] text-on-surface-variant">{detail.name}</span>
              </div>
              <p className="font-mono text-[11px] text-on-surface-variant mt-1">
                {detail.sector ?? "—"}{detail.industry ? ` · ${detail.industry}` : ""}
              </p>
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="lg:col-span-2 space-y-4">
                <div className="flex items-end gap-6">
                  <div>
                    <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">Last Close</p>
                    <p className="font-mono text-3xl font-semibold text-on-surface mt-1">
                      {detail.last_close != null ? `$${detail.last_close.toFixed(2)}` : "—"}
                    </p>
                  </div>
                  {pctChange != null && (
                    <div className="mb-1">
                      <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">1Y Change</p>
                      <p className={`font-mono text-lg font-semibold ${pctChange >= 0 ? "text-secondary" : "text-error"}`}>
                        {pctChange >= 0 ? "+" : ""}{pctChange.toFixed(2)}%
                      </p>
                    </div>
                  )}
                  {detail.ranking && (
                    <div className="mb-1">
                      <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-on-surface-variant">Signal</p>
                      <span className={`font-mono text-[11px] font-bold tracking-[0.06em] px-2 py-0.5 border ${
                        detail.ranking.in_topk
                          ? "border-secondary/30 bg-secondary/10 text-secondary"
                          : "border-outline-variant text-on-surface-variant"
                      }`}>
                        {detail.ranking.in_topk ? "BUY" : "HOLD"}
                      </span>
                    </div>
                  )}
                </div>

                <div className="border border-outline-variant bg-surface-container">
                  <div className="px-4 py-3 border-b border-outline-variant">
                    <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Price History (1Y)</p>
                  </div>
                  <div className="p-4 h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={history ?? []} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
                        <CartesianGrid stroke="#444748" strokeDasharray="2 4" vertical={false} />
                        <XAxis dataKey="date" stroke="#8e9192" fontSize={10} fontFamily="JetBrains Mono" minTickGap={40} />
                        <YAxis
                          stroke="#8e9192"
                          fontSize={10}
                          fontFamily="JetBrains Mono"
                          domain={["auto", "auto"]}
                          tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
                        />
                        <Tooltip
                          contentStyle={{ background: "#1f2020", border: "1px solid #444748", color: "#e5e2e1", fontFamily: "JetBrains Mono", fontSize: 11 }}
                          formatter={(v: number) => [`$${v.toFixed(2)}`, "Close"]}
                        />
                        <Line type="monotone" dataKey="close" stroke="#5cde94" strokeWidth={2} dot={false} />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>

              <div className="space-y-3">
                <div className="border border-outline-variant bg-surface-container">
                  <div className="px-4 py-3 border-b border-outline-variant">
                    <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Key Metrics</p>
                  </div>
                  <div className="px-4 py-2">
                    <MetricRow label="Last Close" value={detail.last_close != null ? `$${detail.last_close.toFixed(2)}` : "—"} />
                    <MetricRow label="Rank" value={detail.ranking ? `#${detail.ranking.rank}` : "—"} />
                    <MetricRow label="Score" value={detail.ranking ? detail.ranking.score.toFixed(4) : "—"} />
                    <MetricRow label="Horizon" value={detail.ranking?.horizon ?? "—"} />
                    <MetricRow
                      label="Signal"
                      value={detail.ranking ? (detail.ranking.in_topk ? "BUY" : "HOLD") : "—"}
                      colored={detail.ranking?.in_topk ? "green" : undefined}
                    />
                    <MetricRow label="Ranked On" value={detail.ranking?.date ?? "—"} />
                  </div>
                </div>

                <div className="border border-outline-variant bg-surface-container">
                  <div className="px-4 py-3 border-b border-outline-variant">
                    <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Company Info</p>
                  </div>
                  <div className="px-4 py-2">
                    <MetricRow label="Sector" value={detail.sector ?? "—"} />
                    <MetricRow label="Industry" value={detail.industry ?? "—"} />
                    <MetricRow label="Country" value={(detail as unknown as Record<string, unknown>).country as string ?? "—"} />
                    <MetricRow label="Exchange" value={(detail as unknown as Record<string, unknown>).exchange as string ?? "—"} />
                  </div>
                </div>
              </div>
            </div>
          </>
        ) : null}
      </PageState>
    </div>
  );
}
