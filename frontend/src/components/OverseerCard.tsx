import { useState } from "react";
import type { ReactElement } from "react";
import type { OverseerParsed, VerifiedTrade } from "../api/types.generated";

function recoBadgeClass(rec: string): string {
  switch (rec) {
    case "STRONG_BUY": return "border-secondary/40 bg-secondary/20 text-secondary";
    case "BUY": return "border-secondary/30 bg-secondary/10 text-secondary";
    case "AVOID": return "border-error/30 bg-error/10 text-error";
    default: return "border-outline-variant text-on-surface-variant";
  }
}

function consensusClass(consensus: string): string {
  switch (consensus) {
    case "strong_agree": return "text-secondary";
    case "agree": return "text-secondary/80";
    case "mixed": return "text-on-surface-variant";
    case "disagree": return "text-error";
    default: return "text-on-surface-variant";
  }
}

function TradeCard({ trade }: { trade: VerifiedTrade }): ReactElement {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-outline-variant bg-surface-container-high p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[13px] font-semibold text-on-surface">{trade.ticker}</p>
          <p className="font-mono text-[10px] text-on-surface-variant mt-0.5">{trade.sector} · {trade.asset_class}</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <span className={`font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border ${recoBadgeClass(trade.final_recommendation)}`}>
            {trade.final_recommendation.replace("_", " ")}
          </span>
          {trade.horizon && (
            <span className="font-mono text-[9px] text-on-surface-variant">{trade.horizon}-term</span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-outline-variant pt-2">
        <span className="font-mono text-[10px] text-on-surface-variant">
          ML: <span className={trade.ml_signal === "BUY" ? "text-secondary font-semibold" : "text-on-surface-variant"}>{trade.ml_signal}</span>
        </span>
        <span className={`font-mono text-[10px] ${consensusClass(trade.agent_consensus)}`}>
          {trade.agent_consensus.replace("_", " ")}
        </span>
        {trade.position_size_pct != null && (
          <span className="font-mono text-[10px] text-on-surface-variant">
            size: <span className="text-secondary font-semibold">{trade.position_size_pct}%</span>
          </span>
        )}
        <span className="font-mono text-[10px] text-on-surface-variant">{trade.conviction} conviction</span>
      </div>

      {trade.catalyst && (
        <div className="border border-outline-variant bg-surface-container px-3 py-2">
          <p className="font-mono text-[10px] text-on-surface-variant">
            <span className="font-bold uppercase tracking-[0.06em]">Catalyst: </span>{trade.catalyst}
            {trade.catalyst_date && <span className="ml-2 opacity-60">{trade.catalyst_date}</span>}
          </p>
        </div>
      )}

      <p className="font-mono text-[11px] text-on-surface">{trade.suggested_action}</p>

      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="font-mono text-[10px] text-on-surface-variant hover:text-on-surface transition-colors flex items-center gap-1"
      >
        <span className="material-symbols-outlined text-[12px] leading-none">
          {expanded ? "expand_less" : "expand_more"}
        </span>
        {expanded ? "Hide detail" : "Show detail"}
      </button>

      {expanded && (
        <div className="space-y-3 border-t border-outline-variant pt-3">
          {trade.what_breaks_thesis && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-error mb-1">Exit Condition</p>
              <p className="font-mono text-[11px] text-error/80">{trade.what_breaks_thesis}</p>
            </div>
          )}
          {trade.supporting_themes.length > 0 && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-on-surface-variant mb-2">Supporting Themes</p>
              <ul className="space-y-1">
                {trade.supporting_themes.map((t, i) => (
                  <li key={i} className="flex gap-2 font-mono text-[11px] text-on-surface">
                    <span className="text-secondary shrink-0">+</span>{t}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {trade.risk_factors.length > 0 && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.08em] text-on-surface-variant mb-2">Risk Factors</p>
              <ul className="space-y-1">
                {trade.risk_factors.map((r, i) => (
                  <li key={i} className="flex gap-2 font-mono text-[11px] text-on-surface">
                    <span className="text-error shrink-0">-</span>{r}
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
    <div className="space-y-4">
      {data.market_overview && (
        <div className="border border-outline-variant bg-surface-container p-4">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-2">Market Overview</p>
          <p className="font-mono text-[12px] text-on-surface leading-relaxed">{data.market_overview}</p>
        </div>
      )}

      {data.portfolio_thesis && (
        <div className="border border-outline-variant bg-surface-container p-4">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-2">Portfolio Thesis</p>
          <p className="font-mono text-[12px] text-on-surface leading-relaxed">{data.portfolio_thesis}</p>
        </div>
      )}

      {(data.top_risks?.length > 0 || data.cross_asset_themes?.length > 0) && (
        <div className="grid gap-3 md:grid-cols-2">
          {data.top_risks?.length > 0 && (
            <div className="border border-outline-variant bg-surface-container p-4">
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-3">Top Risks</p>
              <ul className="space-y-2">
                {data.top_risks.map((r, i) => (
                  <li key={i} className="flex gap-2 font-mono text-[11px] text-on-surface">
                    <span className="text-error shrink-0">-</span>{r}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {data.cross_asset_themes?.length > 0 && (
            <div className="border border-outline-variant bg-surface-container p-4">
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-3">Cross-Asset Themes</p>
              <ul className="space-y-2">
                {data.cross_asset_themes.map((t, i) => (
                  <li key={i} className="flex gap-2 font-mono text-[11px] text-on-surface">
                    <span className="text-secondary shrink-0">*</span>{t}
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
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-secondary mb-3">Buy Signals ({buys.length})</p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {buys.map((t) => <TradeCard key={t.ticker} trade={t} />)}
              </div>
            </div>
          )}
          {holds.length > 0 && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-3">Hold ({holds.length})</p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {holds.map((t) => <TradeCard key={t.ticker} trade={t} />)}
              </div>
            </div>
          )}
          {avoids.length > 0 && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-error mb-3">Avoid ({avoids.length})</p>
              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                {avoids.map((t) => <TradeCard key={t.ticker} trade={t} />)}
              </div>
            </div>
          )}
        </div>
      )}

      {data.watchlist?.length > 0 && (
        <div className="border border-outline-variant bg-surface-container p-4">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-3">Watchlist</p>
          <div className="space-y-2">
            {data.watchlist.map((w, i) => (
              <div key={i} className="flex gap-3">
                <span className="font-mono text-[12px] font-semibold text-secondary shrink-0">{w.ticker}</span>
                <div>
                  <span className="font-mono text-[11px] text-on-surface">{w.reason}</span>
                  {w.trigger && <p className="font-mono text-[10px] text-on-surface-variant mt-0.5">Trigger: {w.trigger}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
