import { useState } from "react";
import type { ReactElement } from "react";
import type { OverseerParsed, VerifiedTrade } from "../api/types.generated";

function recoBadgeClass(rec: string): string {
  switch (rec) {
    case "STRONG_BUY":
      return "bg-emerald-600 text-emerald-50";
    case "BUY":
      return "bg-emerald-900/70 text-emerald-300";
    case "HOLD":
      return "bg-slate-800 text-slate-400";
    case "AVOID":
      return "bg-rose-900/70 text-rose-300";
    default:
      return "bg-slate-800 text-slate-400";
  }
}

function convictionClass(conviction: string): string {
  switch (conviction) {
    case "high":
      return "text-slate-100";
    case "medium":
      return "text-slate-400";
    default:
      return "text-slate-600";
  }
}

function consensusBadgeClass(consensus: string): string {
  switch (consensus) {
    case "strong_agree":
      return "bg-emerald-900/50 text-emerald-400";
    case "agree":
      return "bg-emerald-900/30 text-emerald-500";
    case "mixed":
      return "bg-amber-900/50 text-amber-400";
    case "disagree":
      return "bg-rose-900/50 text-rose-400";
    default:
      return "bg-slate-800 text-slate-500";
  }
}

function tradeBorderClass(rec: string): string {
  switch (rec) {
    case "STRONG_BUY":
      return "border-emerald-700/60";
    case "BUY":
      return "border-emerald-900/60";
    case "AVOID":
      return "border-rose-900/60";
    default:
      return "border-slate-800";
  }
}

function TradeCard({ trade }: { trade: VerifiedTrade }): ReactElement {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={`rounded-xl border ${tradeBorderClass(trade.final_recommendation)} bg-slate-900/70 p-4`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-slate-500">{trade.ticker}</p>
          <p className="text-sm font-medium text-slate-300">{trade.sector}</p>
          <p className="mt-0.5 text-xs text-slate-500 capitalize">{trade.asset_class}</p>
        </div>
        <div className="flex flex-col items-end gap-1.5">
          <span className={`rounded-full px-3 py-1 text-xs font-semibold ${recoBadgeClass(trade.final_recommendation)}`}>
            {trade.final_recommendation.replace("_", " ")}
          </span>
          <span className={`rounded px-2 py-0.5 text-xs ${consensusBadgeClass(trade.agent_consensus)}`}>
            {trade.agent_consensus.replace("_", " ")}
          </span>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <span className="text-xs text-slate-500">
          ML: <span className={`font-mono font-semibold ${trade.ml_signal === "BUY" ? "text-emerald-400" : "text-slate-400"}`}>{trade.ml_signal}</span>
        </span>
        <span className={`text-xs font-medium ${convictionClass(trade.conviction)}`}>
          {trade.conviction} conviction
        </span>
      </div>

      <p className="mt-3 text-sm text-slate-300">{trade.suggested_action}</p>

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="mt-3 text-xs text-slate-500 hover:text-slate-300"
      >
        {expanded ? "Hide detail" : "Show detail"}
      </button>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-slate-800 pt-3">
          {trade.supporting_themes.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs uppercase tracking-wide text-slate-500">Supporting themes</p>
              <ul className="space-y-1">
                {trade.supporting_themes.map((t, i) => (
                  <li key={i} className="flex gap-2 text-xs text-slate-300">
                    <span className="mt-0.5 shrink-0 text-emerald-500">+</span>
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {trade.risk_factors.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs uppercase tracking-wide text-slate-500">Risk factors</p>
              <ul className="space-y-1">
                {trade.risk_factors.map((r, i) => (
                  <li key={i} className="flex gap-2 text-xs text-slate-300">
                    <span className="mt-0.5 shrink-0 text-rose-500">-</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

interface OverseerCardProps {
  data: OverseerParsed;
}

export function OverseerCard({ data }: OverseerCardProps): ReactElement {
  const buys = data.verified_trades?.filter((t) => t.final_recommendation === "STRONG_BUY" || t.final_recommendation === "BUY") ?? [];
  const holds = data.verified_trades?.filter((t) => t.final_recommendation === "HOLD") ?? [];
  const avoids = data.verified_trades?.filter((t) => t.final_recommendation === "AVOID") ?? [];

  return (
    <div className="space-y-6">
      {data.market_overview && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/80 p-5">
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Market overview</p>
          <p className="text-slate-200">{data.market_overview}</p>
        </div>
      )}

      {(data.top_risks?.length > 0 || data.cross_asset_themes?.length > 0) && (
        <div className="grid gap-4 md:grid-cols-2">
          {data.top_risks?.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">Top risks</p>
              <ul className="space-y-2">
                {data.top_risks.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-300">
                    <span className="mt-0.5 shrink-0 text-rose-500">-</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.cross_asset_themes?.length > 0 && (
            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
              <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">Cross-asset themes</p>
              <ul className="space-y-2">
                {data.cross_asset_themes.map((t, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-300">
                    <span className="mt-0.5 shrink-0 text-cyan-500">*</span>
                    {t}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {data.verified_trades?.length > 0 && (
        <div className="space-y-4">
          {buys.length > 0 && (
            <div>
              <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">
                Buy signals ({buys.length})
              </p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {buys.map((t) => (
                  <TradeCard key={t.ticker} trade={t} />
                ))}
              </div>
            </div>
          )}

          {holds.length > 0 && (
            <div>
              <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">
                Hold ({holds.length})
              </p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {holds.map((t) => (
                  <TradeCard key={t.ticker} trade={t} />
                ))}
              </div>
            </div>
          )}

          {avoids.length > 0 && (
            <div>
              <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">
                Avoid ({avoids.length})
              </p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {avoids.map((t) => (
                  <TradeCard key={t.ticker} trade={t} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {data.watchlist?.length > 0 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-4">
          <p className="mb-3 text-xs uppercase tracking-wide text-slate-500">Watchlist</p>
          <div className="space-y-2">
            {data.watchlist.map((w, i) => (
              <div key={i} className="flex gap-3 text-sm">
                <span className="shrink-0 font-mono text-slate-400">{w.ticker}</span>
                <span className="text-slate-400">{w.reason}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
