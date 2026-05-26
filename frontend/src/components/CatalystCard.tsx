import type { ReactElement } from "react";
import type { CatalystParsed } from "../api/types.generated";

function setupClass(q: string): string {
  switch (q) {
    case "excellent": return "border-secondary/40 bg-secondary/10 text-secondary";
    case "good": return "border-secondary/25 bg-secondary/10 text-secondary";
    case "fair": return "border-outline-variant text-on-surface-variant";
    default: return "border-outline-variant text-on-surface-variant";
  }
}

function biasClass(b: string): string {
  switch (b) {
    case "bullish": return "text-secondary";
    case "bearish": return "text-error";
    default: return "text-on-surface-variant";
  }
}

interface CatalystCardProps {
  data: CatalystParsed;
}

export function CatalystCard({ data }: CatalystCardProps): ReactElement {
  return (
    <div className="space-y-4">
      {data.summary && (
        <p className="font-mono text-[12px] text-on-surface">{data.summary}</p>
      )}

      {data.catalyst_plays?.length > 0 && (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {data.catalyst_plays.map((play, i) => (
            <div key={i} className="border border-outline-variant bg-surface-container-high p-4 space-y-2">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="font-mono text-[13px] font-semibold text-on-surface">{play.ticker}</p>
                  <p className={`font-mono text-[10px] font-semibold ${biasClass(play.directional_bias)}`}>
                    {play.directional_bias} · {play.catalyst_type}
                  </p>
                </div>
                <span className={`font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border ${setupClass(play.setup_quality)}`}>
                  {play.setup_quality}
                </span>
              </div>
              <p className="font-mono text-[11px] text-on-surface">{play.catalyst_description}</p>
              {play.catalyst_date && (
                <p className="font-mono text-[10px] text-on-surface-variant">{play.catalyst_date}</p>
              )}
              {play.iv_hv_ratio != null && (
                <p className="font-mono text-[10px] text-on-surface-variant">
                  IV/HV: <span className={play.iv_hv_ratio > 1.3 ? "text-error" : play.iv_hv_ratio < 0.8 ? "text-secondary" : "text-on-surface-variant"}>
                    {play.iv_hv_ratio}x
                  </span>
                  {play.options_priced_in === true && <span className="ml-2 text-error">priced in</span>}
                  {play.options_priced_in === false && <span className="ml-2 text-secondary">not priced in</span>}
                </p>
              )}
              {play.rationale && (
                <p className="font-mono text-[10px] text-on-surface-variant italic">{play.rationale}</p>
              )}
            </div>
          ))}
        </div>
      )}

      {data.macro_events_next_4w?.length > 0 && (
        <div className="border border-outline-variant bg-surface-container p-4">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-3">Macro Events Next 4 Weeks</p>
          <ul className="space-y-1.5">
            {data.macro_events_next_4w.map((e, i) => (
              <li key={i} className="flex gap-2 font-mono text-[11px] text-on-surface">
                <span className="text-on-surface-variant shrink-0">·</span>{e}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
