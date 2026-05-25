import type { ReactElement } from "react";
import type { BearParsed } from "../api/types.generated";

function strengthColor(s: string): string {
  switch (s) {
    case "high": return "text-rose-400";
    case "medium": return "text-amber-400";
    default: return "text-slate-500";
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
        <p className="text-sm text-slate-300">{data.summary}</p>
      )}

      {data.picks_to_avoid?.length > 0 && (
        <div className="flex flex-wrap gap-2">
          <p className="w-full text-xs uppercase tracking-wide text-rose-600">Avoid</p>
          {data.picks_to_avoid.map((t) => (
            <span key={t} className="rounded bg-rose-950/50 px-2 py-0.5 font-mono text-xs text-rose-400">
              {t}
            </span>
          ))}
        </div>
      )}

      {cases.length > 0 && (
        <div className="space-y-3">
          {cases.map(([ticker, bc]) => (
            <div key={ticker} className="rounded-xl border border-rose-900/30 bg-slate-900/60 p-4">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-slate-400">{ticker}</span>
                <span className={`text-xs font-semibold ${strengthColor(bc.strength)}`}>
                  {bc.strength} risk
                </span>
              </div>
              <p className="mt-2 text-sm text-rose-300">{bc.key_objection}</p>
              {bc.valuation_concern && (
                <p className="mt-1 text-xs text-slate-500"><span className="text-slate-600">Valuation: </span>{bc.valuation_concern}</p>
              )}
              {bc.what_breaks_thesis && (
                <p className="mt-1 text-xs text-slate-500"><span className="text-slate-600">Breaks if: </span>{bc.what_breaks_thesis}</p>
              )}
              {bc.crowding_risk && (
                <p className="mt-1 text-xs text-slate-500"><span className="text-slate-600">Crowding: </span>{bc.crowding_risk}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
