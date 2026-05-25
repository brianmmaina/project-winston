import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import {
  ApiClientError,
  getAgentAnalysisLatest,
  triggerAgentAnalysis,
} from "../api/client";
import type { AgentAnalysisResult } from "../api/types.generated";
import { OverseerCard } from "../components/OverseerCard";
import { SubAgentAccordion } from "../components/SubAgentAccordion";
import { useJob } from "../hooks/useJob";

function formatTs(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

function JobProgress({ message, state }: { message: string | null; state: string }): ReactElement {
  const running = state === "pending" || state === "running";
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      <div className="flex items-center gap-3">
        {running && (
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-slate-600 border-t-emerald-400" />
        )}
        <div>
          <p className="text-sm font-medium text-slate-200">
            {state === "completed" ? "Analysis complete" : state === "failed" ? "Analysis failed" : "Running analysis"}
          </p>
          {message && <p className="mt-0.5 text-xs text-slate-500">{message}</p>}
        </div>
      </div>
      {running && (
        <div className="mt-3 h-1 w-full overflow-hidden rounded-full bg-slate-800">
          <div className="h-1 animate-pulse rounded-full bg-emerald-600" style={{ width: "60%" }} />
        </div>
      )}
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
      const data = await getAgentAnalysisLatest();
      setResult(data);
      setLoadError(null);
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 404) {
        setResult(null);
      } else {
        setLoadError(err instanceof Error ? err.message : "Failed to load analysis.");
      }
    }
  }, []);

  useEffect(() => {
    void fetchLatest();
  }, [fetchLatest]);

  useEffect(() => {
    if (job?.state === "completed") {
      void fetchLatest();
    }
  }, [job?.state, fetchLatest]);

  const onRunAnalysis = async () => {
    setTriggerError(null);
    setTriggering(true);
    try {
      const resp = await triggerAgentAnalysis();
      startJob(resp.job_id);
    } catch (err) {
      setTriggerError(err instanceof Error ? err.message : "Failed to start analysis.");
    } finally {
      setTriggering(false);
    }
  };

  const isRunning = isPolling || triggering;
  const overseerParsed = result?.overseer?.parsed;
  const hasOverseerOutput =
    overseerParsed &&
    (overseerParsed.market_overview || (overseerParsed.verified_trades?.length ?? 0) > 0);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold text-slate-100">Agent Analysis</h1>
          {result?.generated_at && (
            <p className="mt-1 text-xs text-slate-500">
              Last run: {formatTs(result.generated_at)} — {result.sub_agent_success_count}/{result.sub_agent_count} agents succeeded
            </p>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <button
            type="button"
            disabled={isRunning}
            onClick={() => void onRunAnalysis()}
            className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-emerald-50 hover:bg-emerald-600 disabled:opacity-50"
          >
            {isRunning ? "Running…" : "Run analysis"}
          </button>
          {triggerError && (
            <p className="text-xs text-rose-400">{triggerError}</p>
          )}
        </div>
      </div>

      {job && (
        <JobProgress message={job.message} state={job.state} />
      )}

      {loadError && (
        <div className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-4 text-sm text-rose-300">
          {loadError}
        </div>
      )}

      {!result && !loadError && !isRunning && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-10 text-center">
          <p className="text-slate-400">No analysis yet.</p>
          <p className="mt-1 text-sm text-slate-600">
            Run an analysis to get recommendations from all 11 agents and the overseer.
          </p>
        </div>
      )}

      {result && (
        <div className="space-y-8">
          {hasOverseerOutput ? (
            <div>
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Overseer
              </h2>
              <OverseerCard data={overseerParsed!} />
            </div>
          ) : result.overseer?.error ? (
            <div className="rounded-lg border border-rose-900/60 bg-rose-950/40 p-4 text-sm text-rose-300">
              Overseer failed: {result.overseer.error}
            </div>
          ) : null}

          {result.sub_reports?.length > 0 && (
            <div>
              <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-slate-500">
                Sub-agents
              </h2>
              <SubAgentAccordion reports={result.sub_reports} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
