import type { ReactElement } from "react";
import type { BearParsed } from "../api/types.generated";

function strengthClass(s: string): string {
  switch (s) {
    case "high": return "text-error";
    case "medium": return "text-on-surface-variant";
    default: return "text-on-surface-variant opacity-60";
  }
}

interface BearCaseCardProps {
  data: BearParsed;
}

export function BearCaseCard({ data }: BearCaseCardProps): ReactElement {
  const cases = Object.entries(data.bear_cases ?? {});

  return (
    <div className="space-y-4">
      {data.summary && (
        <p className="font-mono text-[12px] text-on-surface">{data.summary}</p>
      )}

      {data.picks_to_avoid?.length > 0 && (
        <div className="border border-error/20 bg-error/5 px-4 py-3">
          <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-error mb-2">Picks to Avoid</p>
          <div className="flex flex-wrap gap-2">
            {data.picks_to_avoid.map((t) => (
              <span key={t} className="font-mono text-[11px] font-semibold text-error border border-error/30 px-2 py-0.5">
                {t}
              </span>
            ))}
          </div>
        </div>
      )}

      {cases.length > 0 && (
        <div className="space-y-3">
          {cases.map(([ticker, bc]) => (
            <div key={ticker} className="border border-error/20 bg-surface-container-high p-4 space-y-2">
              <div className="flex items-center gap-3">
                <span className="font-mono text-[13px] font-semibold text-on-surface">{ticker}</span>
                <span className={`font-mono text-[10px] font-bold ${strengthClass(bc.strength)}`}>
                  {bc.strength} risk
                </span>
              </div>
              <p className="font-mono text-[12px] text-error">{bc.key_objection}</p>
              {bc.valuation_concern && (
                <p className="font-mono text-[11px] text-on-surface-variant">
                  <span className="font-bold">Valuation: </span>{bc.valuation_concern}
                </p>
              )}
              {bc.what_breaks_thesis && (
                <p className="font-mono text-[11px] text-on-surface-variant">
                  <span className="font-bold">Breaks if: </span>{bc.what_breaks_thesis}
                </p>
              )}
              {bc.crowding_risk && (
                <p className="font-mono text-[11px] text-on-surface-variant">
                  <span className="font-bold">Crowding: </span>{bc.crowding_risk}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
