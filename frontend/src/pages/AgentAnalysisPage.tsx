import { useCallback, useEffect, useState } from "react";
import type { ReactElement } from "react";

import {
  ApiClientError,
  getAgentAnalysisLatest,
  getAgentDailyScan,
  triggerAgentAnalysis,
  triggerDailyScan,
} from "../api/client";
import type { AgentAnalysisResult, BearParsed, BullDebateResult, BearRebuttalResult, CatalystParsed, DailyScan, OverseerParsed } from "../api/types.generated";
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

const HEALTH_COLOR: Record<string, string> = {
  healthy: "border-secondary/30 bg-secondary/10 text-secondary",
  some_concerns: "border-yellow-500/30 bg-yellow-500/10 text-yellow-400",
  deteriorating: "border-error/30 bg-error/10 text-error",
};
const SEV_COLOR: Record<string, string> = {
  high: "border-error/40 bg-error/10 text-error",
  medium: "border-yellow-500/40 bg-yellow-500/10 text-yellow-400",
  low: "border-outline-variant text-on-surface-variant",
};
const ACTION_COLOR: Record<string, string> = {
  exit: "text-error",
  reduce: "text-yellow-400",
  hold: "text-on-surface-variant",
  add: "text-secondary",
};

function DailyScanSection({ scan, onRunScan, scanning }: { scan: DailyScan | null; onRunScan: () => void; scanning: boolean }) {
  const sorted = [...(scan?.alerts ?? [])].sort((a, b) => {
    const ord: Record<string, number> = { high: 0, medium: 1, low: 2 };
    return (ord[a.severity] ?? 3) - (ord[b.severity] ?? 3);
  });
  return (
    <div className="border border-outline-variant bg-surface-container">
      <div className="px-4 py-3 border-b border-outline-variant flex items-center justify-between">
        <div className="flex items-center gap-3">
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Daily Scan</p>
          {scan && (
            <span className={`font-mono text-[9px] font-bold px-2 py-0.5 border ${HEALTH_COLOR[scan.portfolio_health] ?? "border-outline-variant text-on-surface-variant"}`}>
              {scan.portfolio_health.replace("_", " ")}
            </span>
          )}
          {scan?.scanned_at && (
            <span className="font-mono text-[9px] text-on-surface-variant opacity-60">
              {new Date(scan.scanned_at).toLocaleString(undefined, { dateStyle: "short", timeStyle: "short" })}
            </span>
          )}
        </div>
        <button
          type="button"
          disabled={scanning}
          onClick={onRunScan}
          className="flex items-center gap-1 px-3 py-1.5 border border-outline-variant text-on-surface-variant hover:text-on-surface font-mono text-[9px] font-bold uppercase tracking-[0.06em] transition-colors disabled:opacity-50"
        >
          <span className="material-symbols-outlined text-[12px] leading-none">refresh</span>
          {scanning ? "Scanning…" : "Run Scan"}
        </button>
      </div>
      {scan?.market_note && (
        <div className="px-4 py-2.5 border-b border-outline-variant">
          <p className="font-mono text-[11px] text-on-surface-variant leading-relaxed">{scan.market_note}</p>
        </div>
      )}
      {sorted.length === 0 ? (
        <div className="px-4 py-6 text-center font-mono text-[11px] text-on-surface-variant opacity-50">
          {scan ? "No alerts" : "No scan data — run a scan to see alerts."}
        </div>
      ) : (
        <div className="divide-y divide-outline-variant">
          {sorted.map((a, i) => (
            <div key={i} className="px-4 py-3 flex items-start gap-3">
              <span className="font-mono text-[11px] font-bold text-on-surface shrink-0 w-14">{a.ticker}</span>
              <span className={`font-mono text-[9px] font-bold px-1.5 py-0.5 border shrink-0 ${SEV_COLOR[a.severity] ?? ""}`}>{a.severity}</span>
              <div className="flex-1 min-w-0">
                <p className="font-mono text-[11px] text-on-surface">{a.alert}</p>
                <p className="font-mono text-[10px] text-on-surface-variant opacity-70 mt-0.5">{a.rationale}</p>
              </div>
              <span className={`font-mono text-[10px] font-bold uppercase shrink-0 ${ACTION_COLOR[a.action] ?? ""}`}>{a.action}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const VERDICT_COLOR: Record<string, string> = {
  CONFIRM_BUY: "text-secondary",
  REDUCE_CONVICTION: "text-warning",
  HOLD: "text-on-surface-variant",
  CONFIRM_AVOID: "text-error",
  WATCH: "text-warning",
  RECONSIDER: "text-secondary",
};

function DebateSection({ debate }: { debate: NonNullable<AgentAnalysisResult["debate_report"]> }) {
  const bullEntries = Object.entries(debate.bull_debates);
  const bearEntries = Object.entries(debate.bear_rebuttals);
  if (bullEntries.length === 0 && bearEntries.length === 0) return null;

  return (
    <div className="space-y-4">
      {bullEntries.map(([ticker, d]) => {
        const data = d as Partial<BullDebateResult>;
        return (
          <div key={ticker} className="border border-outline-variant bg-surface-container p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold text-on-surface">{ticker}</span>
                <span className="font-mono text-[9px] uppercase tracking-widest px-1.5 py-0.5 bg-secondary/20 text-secondary">Bull Debate</span>
              </div>
              {data.verdict && (
                <span className={`font-mono text-[10px] font-bold uppercase ${VERDICT_COLOR[data.verdict] ?? ""}`}>{data.verdict.replace("_", " ")}</span>
              )}
            </div>
            {data.bull_rebuttal && (
              <p className="font-mono text-[11px] text-on-surface leading-relaxed">{data.bull_rebuttal}</p>
            )}
            {data.supporting_catalysts && data.supporting_catalysts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {data.supporting_catalysts.map((c, i) => (
                  <span key={i} className="font-mono text-[9px] px-2 py-0.5 border border-secondary/30 text-secondary">{c}</span>
                ))}
              </div>
            )}
            {data.risk_reward && (
              <p className="font-mono text-[10px] text-on-surface-variant"><span className="font-bold">Risk/Reward:</span> {data.risk_reward}</p>
            )}
          </div>
        );
      })}
      {bearEntries.map(([ticker, d]) => {
        const data = d as Partial<BearRebuttalResult>;
        return (
          <div key={ticker} className="border border-outline-variant bg-surface-container p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs font-bold text-on-surface">{ticker}</span>
                <span className="font-mono text-[9px] uppercase tracking-widest px-1.5 py-0.5 bg-error/20 text-error">Bear Rebuttal</span>
              </div>
              {data.verdict && (
                <span className={`font-mono text-[10px] font-bold uppercase ${VERDICT_COLOR[data.verdict] ?? ""}`}>{data.verdict.replace("_", " ")}</span>
              )}
            </div>
            {data.steelman_bull_case && (
              <p className="font-mono text-[11px] text-on-surface leading-relaxed">{data.steelman_bull_case}</p>
            )}
            {data.bull_catalysts && data.bull_catalysts.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {data.bull_catalysts.map((c, i) => (
                  <span key={i} className="font-mono text-[9px] px-2 py-0.5 border border-outline text-on-surface-variant">{c}</span>
                ))}
              </div>
            )}
            {data.entry_price_that_works && (
              <p className="font-mono text-[10px] text-on-surface-variant"><span className="font-bold">Entry that works:</span> {data.entry_price_that_works}</p>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default function AgentAnalysisPage(): ReactElement {
  const [result, setResult] = useState<AgentAnalysisResult | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [triggerError, setTriggerError] = useState<string | null>(null);
  const [triggering, setTriggering] = useState(false);
  const [dailyScan, setDailyScan] = useState<DailyScan | null>(null);
  const [scanning, setScanning] = useState(false);

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

  const fetchScan = useCallback(async () => {
    try { setDailyScan(await getAgentDailyScan()); } catch { /* no scan yet */ }
  }, []);

  useEffect(() => { void fetchLatest(); void fetchScan(); }, [fetchLatest, fetchScan]);

  useEffect(() => {
    if (job?.state === "completed") void fetchLatest();
  }, [job?.state, fetchLatest]);

  const onRunScan = async () => {
    setScanning(true);
    try { await triggerDailyScan(); await fetchScan(); } catch { /* ignore */ } finally { setScanning(false); }
  };

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

      <DailyScanSection scan={dailyScan} onRunScan={() => void onRunScan()} scanning={scanning} />

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

          {result.debate_report && (
            (Object.keys(result.debate_report.bull_debates).length > 0 || Object.keys(result.debate_report.bear_rebuttals).length > 0)
          ) && (
            <div>
              <SectionHeader label="Debate Round" />
              <DebateSection debate={result.debate_report!} />
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
