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

function viewClass(view: string): string {
  switch (view) {
    case "agree": return "text-secondary";
    case "cautious": return "text-on-surface-variant";
    case "disagree": return "text-error";
    default: return "text-on-surface-variant";
  }
}

function SignalRow({ signal }: { signal: AgentSignal }): ReactElement {
  const [open, setOpen] = useState(false);

  return (
    <div className="border-t border-outline-variant py-2 first:border-0">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-[12px] font-semibold text-secondary">{signal.ticker}</span>
        <span className={`font-mono text-[10px] font-bold ${signal.ml_signal === "BUY" ? "text-secondary" : "text-on-surface-variant"}`}>
          ML: {signal.ml_signal}
        </span>
        <span className={`font-mono text-[10px] font-bold ${viewClass(signal.agent_view)}`}>
          {signal.agent_view}
        </span>
        <span className="font-mono text-[10px] text-on-surface-variant">{signal.conviction}</span>
        {(signal.key_factors?.length > 0 || signal.risks?.length > 0) && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="ml-auto font-mono text-[10px] text-on-surface-variant hover:text-on-surface transition-colors"
          >
            {open ? "less" : "more"}
          </button>
        )}
      </div>
      {open && (
        <div className="mt-2 space-y-2 pl-3 border-l border-outline-variant">
          {signal.key_factors?.length > 0 && (
            <div>
              <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-on-surface-variant mb-1">Factors</p>
              <ul className="space-y-0.5">
                {signal.key_factors.map((f, i) => (
                  <li key={i} className="flex gap-2 font-mono text-[11px] text-on-surface">
                    <span className="text-secondary shrink-0">+</span>{f}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {signal.risks?.length > 0 && (
            <div>
              <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-on-surface-variant mb-1">Risks</p>
              <ul className="space-y-0.5">
                {signal.risks.map((r, i) => (
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

function AgentPanel({ report }: { report: SubAgentReport }): ReactElement {
  const [open, setOpen] = useState(false);
  const label = AGENT_LABELS[report.name] ?? report.name;
  const parsed = report.parsed;
  const hasContent = parsed.summary || (parsed.signals && parsed.signals.length > 0);

  return (
    <div className="border border-outline-variant bg-surface-container">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-surface-container-high transition-colors"
      >
        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${report.error ? "bg-error" : "bg-secondary"}`} />
        <span className="flex-1 font-mono text-[12px] font-semibold text-on-surface">{label}</span>
        {parsed.summary && (
          <span className="hidden max-w-xs truncate font-mono text-[10px] text-on-surface-variant md:block">
            {parsed.summary}
          </span>
        )}
        {parsed.top_picks && parsed.top_picks.length > 0 && (
          <span className="shrink-0 font-mono text-[10px] text-secondary">
            {parsed.top_picks.slice(0, 3).join(", ")}
          </span>
        )}
        <span className="material-symbols-outlined text-[16px] leading-none text-on-surface-variant ml-2 shrink-0">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>

      {open && (
        <div className="border-t border-outline-variant px-4 py-4 space-y-4">
          {report.error && (
            <p className="font-mono text-[11px] text-error">Agent failed: {report.error}</p>
          )}

          {parsed.summary && (
            <p className="font-mono text-[12px] text-on-surface">{parsed.summary}</p>
          )}

          {!hasContent && !report.error && (
            <p className="font-mono text-[11px] text-on-surface-variant opacity-60">No structured output — raw text only.</p>
          )}

          {parsed.signals && parsed.signals.length > 0 && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-2">Signals Reviewed</p>
              <div>
                {parsed.signals.map((s, i) => (
                  <SignalRow key={i} signal={s} />
                ))}
              </div>
            </div>
          )}

          {parsed.caution_flags && parsed.caution_flags.length > 0 && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-2">Caution Flags</p>
              <div className="flex flex-wrap gap-2">
                {parsed.caution_flags.map((f, i) => (
                  <span key={i} className="font-mono text-[10px] font-bold text-on-surface-variant border border-outline-variant px-2 py-0.5">
                    {f}
                  </span>
                ))}
              </div>
            </div>
          )}

          {parsed.news_highlights && parsed.news_highlights.length > 0 && (
            <div>
              <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant mb-2">News Highlights</p>
              <ul className="space-y-1.5">
                {parsed.news_highlights.map((n, i) => (
                  <li key={i} className="flex gap-2 font-mono text-[11px] text-on-surface">
                    <span className="text-on-surface-variant shrink-0">{i + 1}.</span>{n}
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
      <p className="font-mono text-[10px] text-on-surface-variant mb-3">
        {succeeded}/{reports.length} agents succeeded
      </p>
      {reports.map((r) => (
        <AgentPanel key={r.name} report={r} />
      ))}
    </div>
  );
}
