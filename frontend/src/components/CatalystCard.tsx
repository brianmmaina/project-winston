import type { ReactElement } from "react";
import type { CatalystParsed } from "../api/types.generated";

function setupBadge(q: string): string {
  switch (q) {
    case "excellent": return "bg-emerald-900/60 text-emerald-300";
    case "good": return "bg-emerald-900/30 text-emerald-500";
    case "fair": return "bg-amber-900/50 text-amber-400";
    default: return "bg-slate-800 text-slate-500";
  }
}

function biasBadge(b: string): string {
  switch (b) {
    case "bullish": return "text-emerald-400";
    case "bearish": return "text-rose-400";
    default: return "text-amber-400";
  }
}

interface CatalystCardProps {
  data: CatalystParsed;
}

export function CatalystCard({ data }: CatalystCardProps): ReactElement {
  return (
    <div className="space-y-4">
      {data.summary && (
        <p className="text-sm text-slate-300">{data.summary}</p>
      )}

      {data.catalyst_plays?.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.catalyst_plays.map((play, i) => (
            <div key={i} className="rounded-xl border border-violet-900/40 bg-slate-900/70 p-4">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-xs text-slate-500">{play.ticker}</p>
                  <p className={`text-xs font-semibold ${biasBadge(play.directional_bias)}`}>
                    {play.directional_bias} · {play.catalyst_type}
                  </p>
                </div>
                <span className={`rounded px-2 py-0.5 text-xs ${setupBadge(play.setup_quality)}`}>
                  {play.setup_quality}
                </span>
              </div>
              <p className="mt-2 text-xs text-slate-300">{play.catalyst_description}</p>
              {play.catalyst_date && (
                <p className="mt-1 text-xs text-violet-400">{play.catalyst_date}</p>
              )}
              {play.iv_hv_ratio != null && (
                <p className="mt-1 text-xs text-slate-500">
                  IV/HV: <span className={play.iv_hv_ratio > 1.3 ? "text-rose-400" : play.iv_hv_ratio < 0.8 ? "text-emerald-400" : "text-slate-400"}>
                    {play.iv_hv_ratio}x
                  </span>
                  {play.options_priced_in === true && <span className="ml-2 text-rose-500">priced in</span>}
                  {play.options_priced_in === false && <span className="ml-2 text-emerald-500">not priced in</span>}
                </p>
              )}
              <p className="mt-2 text-xs text-slate-500 italic">{play.rationale}</p>
            </div>
          ))}
        </div>
      )}

      {data.macro_events_next_4w?.length > 0 && (
        <div>
          <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Macro events next 4 weeks</p>
          <ul className="space-y-1">
            {data.macro_events_next_4w.map((e, i) => (
              <li key={i} className="text-xs text-slate-400">
                <span className="mr-2 text-slate-600">·</span>{e}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
