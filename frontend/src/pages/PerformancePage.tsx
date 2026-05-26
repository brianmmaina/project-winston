import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import { ApiClientError, getAgentPerformance } from "../api/client";
import type { PerformanceSummary, RecommendationRecord } from "../api/types.generated";
import { PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

function fmt(n: number | null | undefined, suffix = "%", digits = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}${suffix}`;
}

function Stat({ label, value, positive }: { label: string; value: string; positive?: boolean }) {
  return (
    <div className="border border-outline-variant bg-surface-container p-4">
      <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">{label}</p>
      <p className={`mt-2 font-mono text-2xl font-semibold ${
        positive === true ? "text-secondary" : positive === false ? "text-error" : "text-on-surface"
      }`}>
        {value}
      </p>
    </div>
  );
}

function alphaColor(n: number | null | undefined): string {
  if (n == null) return "text-on-surface-variant";
  return n > 0 ? "text-secondary" : "text-error";
}

function RecordRow({ rec }: { rec: RecommendationRecord }) {
  const signal = rec.final_recommendation?.toUpperCase() ?? "—";
  return (
    <tr className="hover:bg-surface-container-high transition-colors">
      <td className="px-4 py-2.5 font-mono text-[13px] font-semibold text-secondary">{rec.ticker}</td>
      <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant">{rec.sector ?? "—"}</td>
      <td className="px-4 py-2.5">
        <span className={`font-mono text-[10px] font-bold tracking-[0.06em] ${
          signal === "BUY" ? "text-secondary" : signal === "SELL" ? "text-error" : "text-on-surface-variant"
        }`}>{signal}</span>
      </td>
      <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant">{rec.conviction ?? "—"}</td>
      <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant">{rec.entry_date ?? "—"}</td>
      <td className={`px-4 py-2.5 font-mono text-[12px] font-medium ${alphaColor(rec.return_2w_pct)}`}>
        {fmt(rec.return_2w_pct)}
      </td>
      <td className={`px-4 py-2.5 font-mono text-[12px] font-medium ${alphaColor(rec.return_4w_pct)}`}>
        {fmt(rec.return_4w_pct)}
      </td>
      <td className={`px-4 py-2.5 font-mono text-[12px] font-medium ${alphaColor(rec.return_8w_pct)}`}>
        {fmt(rec.return_8w_pct)}
      </td>
    </tr>
  );
}

export default function PerformancePage(): ReactElement {
  const [data, setData] = useState<PerformanceSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getAgentPerformance());
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="p-6 space-y-6">
      <div className="border-b border-outline-variant pb-4">
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Agent Performance</p>
        <p className="mt-1 font-mono text-xs text-on-surface-variant">Walk-forward out-of-sample returns across all recommendation horizons</p>
      </div>

      <PageState error={error} onRetry={() => void load()}>
        {loading ? (
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div key={i} className="h-24 border border-outline-variant bg-surface-container animate-pulse" />
            ))}
          </div>
        ) : data ? (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
              <Stat label="Total Recommendations" value={String(data.total_recommendations)} />
              <Stat
                label="2W Alpha vs SPX"
                value={fmt(data.avg_alpha_2w_pct)}
                positive={data.avg_alpha_2w_pct != null ? data.avg_alpha_2w_pct > 0 : undefined}
              />
              <Stat
                label="4W Alpha vs SPX"
                value={fmt(data.avg_alpha_4w_pct)}
                positive={data.avg_alpha_4w_pct != null ? data.avg_alpha_4w_pct > 0 : undefined}
              />
              <Stat label="Avg 2W Return" value={fmt(data.avg_return_2w_pct)} />
              <Stat label="Avg 4W Return" value={fmt(data.avg_return_4w_pct)} />
              <Stat label="SPX 2W Avg" value={fmt(data.avg_spx_return_2w_pct)} />
            </div>

            {data.records.length > 0 && (
              <div className="border border-outline-variant bg-surface-container">
                <div className="px-4 py-3 border-b border-outline-variant flex items-center justify-between">
                  <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Recommendation History</p>
                  <span className="font-mono text-[10px] text-on-surface-variant">{data.records.length} records</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left">
                    <thead className="border-b border-outline-variant bg-surface-container-high">
                      <tr>
                        {["TICKER", "SECTOR", "SIGNAL", "CONVICTION", "ENTRY", "2W RET", "4W RET", "8W RET"].map((h) => (
                          <th key={h} className="px-4 py-2 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-outline-variant">
                      {data.records.map((rec) => <RecordRow key={rec.id} rec={rec} />)}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </>
        ) : null}
      </PageState>
    </div>
  );
}
