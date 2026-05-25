import { useState } from "react";
import type { ReactElement } from "react";
import type { AgentSignal, SubAgentReport } from "../api/types.generated";

const AGENT_LABELS: Record<string, string> = {
  energy_commodities: "Energy Commodities",
  metals: "Metals",
  agriculture: "Agriculture",
  tech_comms_stocks: "Tech & Communications",
  healthcare_stocks: "Healthcare",
  financials_stocks: "Financials",
  cyclicals_stocks: "Cyclicals",
  defensives_stocks: "Defensives",
  macro_rates: "Macro & Rates",
  geopolitics: "Geopolitics",
  sentiment_news: "Sentiment & News",
};

function viewBadgeClass(view: string): string {
  switch (view) {
    case "agree":
      return "bg-emerald-900/50 text-emerald-400";
    case "cautious":
      return "bg-amber-900/50 text-amber-400";
    case "disagree":
      return "bg-rose-900/50 text-rose-400";
    default:
      return "bg-slate-800 text-slate-500";
  }
}

function SignalRow({ signal }: { signal: AgentSignal }): ReactElement {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-slate-800 py-2 first:border-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs text-slate-400">{signal.ticker}</span>
        <span className={`rounded px-1.5 py-0.5 text-xs font-mono ${signal.ml_signal === "BUY" ? "text-emerald-400" : "text-slate-500"}`}>
          ML: {signal.ml_signal}
        </span>
        <span className={`rounded px-2 py-0.5 text-xs ${viewBadgeClass(signal.agent_view)}`}>
          {signal.agent_view}
        </span>
        <span className="text-xs text-slate-600">{signal.conviction}</span>
        {(signal.key_factors?.length > 0 || signal.risks?.length > 0) && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="ml-auto text-xs text-slate-600 hover:text-slate-400"
          >
            {open ? "less" : "more"}
          </button>
        )}
      </div>
      {open && (
        <div className="mt-2 space-y-2 pl-2">
          {signal.key_factors?.length > 0 && (
            <div>
              <p className="text-xs text-slate-600">Factors</p>
              <ul className="mt-1 space-y-0.5">
                {signal.key_factors.map((f, i) => (
                  <li key={i} className="text-xs text-slate-400">+ {f}</li>
                ))}
              </ul>
            </div>
          )}
          {signal.risks?.length > 0 && (
            <div>
              <p className="text-xs text-slate-600">Risks</p>
              <ul className="mt-1 space-y-0.5">
                {signal.risks.map((r, i) => (
                  <li key={i} className="text-xs text-slate-400">- {r}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function AgentPanel({ report }: { report: SubAgentReport }): ReactElement {
  const [open, setOpen] = useState(false);
  const label = AGENT_LABELS[report.name] ?? report.name;
  const parsed = report.parsed;
  const hasContent = parsed.summary || (parsed.signals && parsed.signals.length > 0);

  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        <span className={`h-2 w-2 shrink-0 rounded-full ${report.error ? "bg-rose-500" : "bg-emerald-500"}`} />
        <span className="flex-1 text-sm font-medium text-slate-200">{label}</span>
        {parsed.summary && (
          <span className="hidden max-w-xs truncate text-xs text-slate-500 md:block">
            {parsed.summary}
          </span>
        )}
        {parsed.top_picks && parsed.top_picks.length > 0 && (
          <span className="shrink-0 font-mono text-xs text-emerald-600">
            {parsed.top_picks.slice(0, 3).join(", ")}
          </span>
        )}
        <span className="ml-2 shrink-0 text-slate-600">{open ? "^" : "v"}</span>
      </button>

      {open && (
        <div className="border-t border-slate-800 px-4 py-4 space-y-4">
          {report.error && (
            <p className="text-xs text-rose-400">Agent failed: {report.error}</p>
          )}

          {parsed.summary && (
            <p className="text-sm text-slate-300">{parsed.summary}</p>
          )}

          {!hasContent && !report.error && (
            <p className="text-xs text-slate-600">No structured output — raw text only.</p>
          )}

          {parsed.signals && parsed.signals.length > 0 && (
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Signals reviewed</p>
              <div>
                {parsed.signals.map((s, i) => (
                  <SignalRow key={i} signal={s} />
                ))}
              </div>
            </div>
          )}

          {parsed.caution_flags && parsed.caution_flags.length > 0 && (
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">Caution flags</p>
              <div className="flex flex-wrap gap-2">
                {parsed.caution_flags.map((f, i) => (
                  <span key={i} className="rounded bg-amber-900/40 px-2 py-0.5 font-mono text-xs text-amber-400">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {parsed.news_highlights && parsed.news_highlights.length > 0 && (
            <div>
              <p className="mb-2 text-xs uppercase tracking-wide text-slate-500">News highlights</p>
              <ul className="space-y-1.5">
                {parsed.news_highlights.map((n, i) => (
                  <li key={i} className="text-xs text-slate-400">
                    <span className="mr-2 text-slate-600">{i + 1}.</span>
                    {n}
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

interface SubAgentAccordionProps {
  reports: SubAgentReport[];
}

export function SubAgentAccordion({ reports }: SubAgentAccordionProps): ReactElement {
  const succeeded = reports.filter((r) => !r.error).length;

  return (
    <div className="space-y-2">
      <p className="text-xs text-slate-500">
        Sub-agent reports — {succeeded}/{reports.length} succeeded
      </p>
      {reports.map((r) => (
        <AgentPanel key={r.name} report={r} />
      ))}
    </div>
  );
}
