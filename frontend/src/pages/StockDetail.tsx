/** Single-stock detail: price chart + latest ranking position. */

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
import { DetailSkeleton, PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
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

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <main className="mx-auto max-w-5xl space-y-6 px-4 py-6">
        <DetailSkeleton />
      </main>
    );
  }

  return (
    <main className="mx-auto max-w-5xl space-y-6 px-4 py-6">
      <PageState error={error} onRetry={() => void load()}>
        {detail ? (
          <>
            <header>
              <h1 className="text-2xl font-semibold tracking-tight text-slate-100">
                {detail.ticker} <span className="text-slate-500">·</span>{" "}
                <span className="text-slate-300">{detail.name}</span>
              </h1>
              <p className="mt-1 text-sm text-slate-400">
                {detail.sector ?? "Sector unknown"}
                {detail.industry ? ` · ${detail.industry}` : ""}
              </p>
            </header>

            <section className="grid gap-4 md:grid-cols-3">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">Last close</p>
                <p className="mt-1 text-xl font-semibold text-slate-100">
                  {detail.last_close != null ? `$${detail.last_close.toFixed(2)}` : "—"}
                </p>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">Rank</p>
                <p className="mt-1 text-xl font-semibold text-slate-100">
                  {detail.ranking ? `#${detail.ranking.rank}` : "—"}
                </p>
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">Signal</p>
                <p className="mt-1 text-xl font-semibold">
                  {detail.ranking?.in_topk ? (
                    <span className="text-emerald-300">BUY (top-K)</span>
                  ) : detail.ranking ? (
                    <span className="text-slate-300">HOLD</span>
                  ) : (
                    <span className="text-slate-500">—</span>
                  )}
                </p>
                {detail.ranking ? (
                  <p className="mt-1 text-xs text-slate-500">
                    Score {detail.ranking.score.toFixed(4)} · horizon {detail.ranking.horizon} ·{" "}
                    {detail.ranking.date}
                  </p>
                ) : null}
              </div>
            </section>

            <section className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
              <h2 className="text-sm font-semibold text-slate-200">Price (1y)</h2>
              <div className="mt-2 h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={history ?? []}
                    margin={{ top: 6, right: 16, left: 0, bottom: 4 }}
                  >
                    <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                    <XAxis dataKey="date" stroke="#64748b" fontSize={11} minTickGap={32} />
                    <YAxis
                      stroke="#64748b"
                      fontSize={11}
                      domain={["auto", "auto"]}
                      tickFormatter={(v) => `$${Number(v).toFixed(0)}`}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "#020617",
                        border: "1px solid #1e293b",
                        color: "#e2e8f0",
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="close"
                      stroke="#34d399"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
          </>
        ) : null}
      </PageState>
    </main>
  );
}
