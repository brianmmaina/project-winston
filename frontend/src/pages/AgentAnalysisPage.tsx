import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import {
  ApiClientError,
  getAgentAnalysisLatest,
  triggerAgentAnalysis,
} from "../api/client";
import type { AgentAnalysisResult, BearParsed, CatalystParsed, OverseerParsed } from "../api/types.generated";
import { BearCaseCard } from "../components/BearCaseCard";
import { CatalystCard } from "../components/CatalystCard";
import { OverseerCard } from "../components/OverseerCard";
import { SubAgentAccordion } from "../components/SubAgentAccordion";
import { useJob } from "../hooks/useJob";

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function SectionHeader({ label }: { label: string }) {
  return (
    <div className="border-b border-outline-variant pb-2 mb-4">
      <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">{label}</p>
    </div>
  );
}

export default function AgentAnalysisPage(): ReactElement {
  const [result, setResult] = useState<AgentAnalysisResult | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);

  const { job, isPolling, start: startJob } = useJob(2000);

  const fetchLatest = useCallback(async () => {
    try {
      setResult(await getAgentAnalysisLatest());
      setLoadError(null);
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 404) {
        setResult(null);
      } else {
        setLoadError(err instanceof Error ? err.message : "Failed to load analysis.");
      }
    }
  }, []);

  useEffect(() => { void fetchLatest(); }, [fetchLatest]);

  useEffect(() => {
    if (job?.state === "completed") void fetchLatest();
  }, [job?.state, fetchLatest]);

  const onRunAnalysis = async () => {
    setTriggerError(null);
    setTriggering(true);
    try {
      startJob((await triggerAgentAnalysis()).job_id);
    } catch (err) {
      setTriggerError(err instanceof Error ? err.message : "Failed to start analysis.");
    } finally {
      setTriggering(false);
    }
  };

  const isRunning = isPolling || triggering;
  const overseerParsed = result?.overseer?.parsed;
  const hasOverseer = overseerParsed && (overseerParsed.market_overview || (overseerParsed.verified_trades?.length ?? 0) > 0);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-start justify-between border-b border-outline-variant pb-4">
        <div>
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Agent Analysis</p>
          {result?.generated_at && (
            <p className="font-mono text-[10px] text-on-surface-variant opacity-60 mt-0.5">
              Last run: {formatTs(result.generated_at)} · {result.sub_agent_success_count}/{result.sub_agent_count} agents succeeded
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <button
            type="button"
            disabled={isRunning}
            onClick={() => void onRunAnalysis()}
            className="flex items-center gap-1.5 px-4 py-2 bg-secondary text-on-secondary font-mono text-[10px] font-bold tracking-[0.06em] uppercase hover:bg-secondary-fixed-dim transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[14px] leading-none">
              {isRunning ? "hourglass_top" : "play_arrow"}
            </span>
            {isRunning ? "Running…" : "Run Analysis"}
          </button>
          {triggerError && <p className="font-mono text-[10px] text-error">{triggerError}</p>}
        </div>
      </div>

      {job && (
        <div className={`border px-4 py-3 font-mono text-[11px] flex items-center gap-3 ${
          job.state === "failed" ? "border-error/30 bg-error/10 text-error"
          : job.state === "completed" ? "border-secondary/30 bg-secondary/10 text-secondary"
          : "border-outline-variant text-on-surface-variant"
        }`}>
          {(job.state === "pending" || job.state === "running") && (
            <div className="w-3 h-3 border-2 border-current border-t-transparent rounded-full animate-spin shrink-0" />
          )}
          <span>
            {job.state === "completed" ? "Analysis complete" : job.state === "failed" ? "Analysis failed" : "Running analysis…"}
            {job.message ? ` — ${job.message}` : ""}
          </span>
        </div>
      )}

      {loadError && (
        <div className="border border-error/30 bg-error/10 px-4 py-3 font-mono text-[11px] text-error">
          {loadError}
        </div>
      )}

      {!result && !loadError && !isRunning && (
        <div className="border border-outline-variant bg-surface-container py-16 text-center">
          <span className="material-symbols-outlined text-4xl text-on-surface-variant opacity-40">psychology</span>
          <p className="font-mono text-[13px] text-on-surface-variant mt-3">No analysis yet.</p>
          <p className="font-mono text-[11px] text-on-surface-variant opacity-60 mt-1">
            Run an analysis to get recommendations from all agents and the overseer.
          </p>
        </div>
      )}

      {result && (
        <div className="space-y-8">
          {hasOverseer ? (
            <div>
              <SectionHeader label="Overseer" />
              <OverseerCard data={overseerParsed as OverseerParsed} />
            </div>
          ) : result.overseer?.error ? (
            <div className="border border-error/30 bg-error/10 px-4 py-3 font-mono text-[11px] text-error">
              Overseer failed: {result.overseer.error}
            </div>
          ) : null}

          {result.catalyst_report?.parsed?.catalyst_plays && result.catalyst_report.parsed.catalyst_plays.length > 0 && (
            <div>
              <SectionHeader label="Catalyst Plays" />
              <CatalystCard data={result.catalyst_report.parsed as CatalystParsed} />
            </div>
          )}

          {result.bear_report?.parsed?.bear_cases && Object.keys(result.bear_report.parsed.bear_cases).length > 0 && (
            <div>
              <SectionHeader label="Bear Cases" />
              <BearCaseCard data={result.bear_report.parsed as BearParsed} />
            </div>
          )}

          {result.sub_reports?.length > 0 && (
            <div>
              <SectionHeader label="Sub-Agents" />
              <SubAgentAccordion reports={result.sub_reports} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
