import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import {
  getRecentJobs,
  triggerAgentAnalysis,
  triggerDailyScan,
  triggerRefreshAsync,
  triggerRetrain,
  triggerAlertScan,
  triggerEconomicIngest,
  triggerEarningsIngest,
} from "../api/client";
import type { JobStatus } from "../api/types.generated";

const REAL_AGENTS = [
  { id: "energy_commodities", name: "Energy Commodities", description: "WTI, Brent, NatGas, Heating Oil, Gasoline — supply/demand and macro flows" },
  { id: "metals", name: "Metals", description: "Gold, Silver, Copper, Platinum, Palladium — demand and industrial cycle" },
  { id: "agriculture", name: "Agriculture", description: "Corn, Wheat, Soybeans, Coffee, Cotton, Sugar, Cocoa — weather and supply chains" },
  { id: "tech_comms_stocks", name: "Tech & Comms", description: "Top-N tech and communications stocks by ML rank" },
  { id: "healthcare_stocks", name: "Healthcare", description: "Top-N healthcare stocks including biotech and pharma" },
  { id: "financials_stocks", name: "Financials", description: "Top-N financials — banks, insurance, asset managers" },
  { id: "cyclicals_stocks", name: "Cyclicals", description: "Consumer discretionary, industrials, materials" },
  { id: "defensives_stocks", name: "Defensives", description: "Consumer staples, utilities, real estate" },
  { id: "macro_rates", name: "Macro & Rates", description: "Fed policy, yield curve, DXY, cross-asset correlations" },
  { id: "geopolitics", name: "Geopolitics", description: "Trade policy, sanctions, supply disruptions, country risk" },
  { id: "sentiment_news", name: "Sentiment & News", description: "RSS feeds, FinBERT scoring, news momentum" },
];

const SCHEDULED_JOBS = [
  { id: "commodity_refresh_weekday", label: "Commodity Refresh", schedule: "Mon–Fri 06:30 ET" },
  { id: "daily_agent_scan", label: "Daily Agent Scan", schedule: "Mon–Fri 08:00 ET" },
  { id: "daily_outcome_check", label: "Outcome Check", schedule: "Mon–Fri 08:30 ET" },
  { id: "price_alert_scan", label: "Price Alert Scan", schedule: "Mon–Fri every 30 min (9–4 ET)" },
  { id: "stock_refresh_weekday", label: "Stock Refresh", schedule: "Mon–Fri 07:15 ET" },
  { id: "weekly_retrain", label: "Weekly Retrain", schedule: "Sun 02:00 ET" },
  { id: "weekly_backtest", label: "Weekly Backtest", schedule: "Sun 04:00 ET" },
  { id: "weekly_stock_retrain", label: "Stock Retrain + Backtest", schedule: "Sat 03:00 ET" },
  { id: "weekly_cot", label: "COT Ingest", schedule: "Wed 09:00 ET" },
  { id: "weekly_eia", label: "EIA Ingest", schedule: "Wed 10:30 ET" },
  { id: "weekly_calendar", label: "Calendar Ingest", schedule: "Sun 06:00 ET" },
  { id: "monthly_tuning", label: "Monthly Hyperparameter Tuning", schedule: "1st of month 01:00 ET" },
];

function StateColor(state: string) {
  if (state === "completed") return "text-secondary border-secondary/30 bg-secondary/10";
  if (state === "failed") return "text-error border-error/30 bg-error/10";
  if (state === "running") return "text-warning border-warning/40 bg-warning/10";
  return "text-on-surface-variant border-outline-variant";
}

function JobRow({ job }: { job: JobStatus }) {
  const ts = job.updated_at ? new Date(job.updated_at).toLocaleTimeString("en-US", { hour12: false }) : "—";
  return (
    <div className="flex items-center justify-between px-4 py-2 border-b border-outline-variant last:border-0">
      <div className="flex items-center gap-3 min-w-0">
        {(job.state === "running" || job.state === "pending") && (
          <div className="w-2 h-2 rounded-full border border-current border-t-transparent animate-spin shrink-0 text-warning" />
        )}
        <span className="font-mono text-[11px] text-on-surface truncate">{job.name}</span>
        {job.message && <span className="font-mono text-[10px] text-on-surface-variant truncate max-w-xs">{job.message}</span>}
      </div>
      <div className="flex items-center gap-3 shrink-0 ml-4">
        <span className="font-mono text-[9px] text-on-surface-variant">{ts}</span>
        <span className={`font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border ${StateColor(job.state)}`}>
          {job.state.toUpperCase()}
        </span>
      </div>
    </div>
  );
}

type TriggerFn = () => Promise<unknown>;

function TriggerButton({ label, fn, className = "" }: { label: string; fn: TriggerFn; className?: string }) {
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const run = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fn() as Record<string, unknown>;
      const detail = res?.job_id ? `job ${String(res.job_id).slice(0, 8)}…` : JSON.stringify(res);
      setMsg(detail);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        disabled={busy}
        onClick={() => void run()}
        className={`font-mono text-[9px] font-bold tracking-[0.06em] uppercase px-3 py-1.5 border transition-colors disabled:opacity-50 ${className || "border-outline-variant text-on-surface-variant hover:border-outline hover:text-on-surface"}`}
      >
        {busy ? "Running…" : label}
      </button>
      {msg && <span className="font-mono text-[9px] text-on-surface-variant">{msg}</span>}
    </div>
  );
}

export default function AgentConfigPage(): ReactElement {
  const [jobs, setJobs] = useState<JobStatus[]>([]);

  const fetchJobs = useCallback(async () => {
    try { setJobs(await getRecentJobs(30)); } catch { /* non-critical */ }
  }, []);

  useEffect(() => { void fetchJobs(); }, [fetchJobs]);
  useEffect(() => {
    const id = setInterval(() => { void fetchJobs(); }, 10000);
    return () => clearInterval(id);
  }, [fetchJobs]);

  return (
    <div className="p-6 space-y-6">
      <div className="border-b border-outline-variant pb-4">
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Agent Configuration</p>
        <p className="mt-1 font-mono text-xs text-on-surface-variant">Pipeline agents, scheduled jobs, and manual triggers</p>
      </div>

      {/* Manual triggers */}
      <div className="border border-outline-variant bg-surface-container">
        <div className="px-4 py-3 border-b border-outline-variant">
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Manual Triggers</p>
        </div>
        <div className="p-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <TriggerButton label="Run Full Analysis" fn={triggerAgentAnalysis} className="border-secondary/40 text-secondary hover:bg-secondary/10" />
          <TriggerButton label="Daily Scan" fn={triggerDailyScan} />
          <TriggerButton label="Commodity Refresh" fn={triggerRefreshAsync} />
          <TriggerButton label="Retrain Models" fn={triggerRetrain} />
          <TriggerButton label="Price Alert Scan" fn={triggerAlertScan} />
          <TriggerButton label="Ingest Economic Cal." fn={triggerEconomicIngest} />
          <TriggerButton label="Ingest Earnings Cal." fn={triggerEarningsIngest} />
        </div>
      </div>

      {/* Agent roster */}
      <div>
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant mb-3">Agent Roster</p>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {REAL_AGENTS.map((agent) => (
            <div key={agent.id} className="border border-outline-variant bg-surface-container p-4">
              <p className="font-mono text-[12px] font-semibold text-on-surface">{agent.name}</p>
              <p className="font-mono text-[10px] text-on-surface-variant mt-0.5">{agent.description}</p>
              <p className="font-mono text-[9px] text-on-surface-variant opacity-50 mt-2 uppercase tracking-widest">{agent.id}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Scheduled jobs */}
      <div className="border border-outline-variant bg-surface-container">
        <div className="px-4 py-3 border-b border-outline-variant">
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Scheduled Jobs (APScheduler · America/New_York)</p>
        </div>
        <div className="divide-y divide-outline-variant">
          {SCHEDULED_JOBS.map((j) => (
            <div key={j.id} className="flex items-center justify-between px-4 py-2.5">
              <span className="font-mono text-[11px] text-on-surface">{j.label}</span>
              <span className="font-mono text-[10px] text-on-surface-variant">{j.schedule}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Recent job history */}
      <div className="border border-outline-variant bg-surface-container">
        <div className="flex items-center justify-between px-4 py-3 border-b border-outline-variant">
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Recent Job History</p>
          <button type="button" onClick={() => void fetchJobs()} className="font-mono text-[9px] text-on-surface-variant hover:text-on-surface uppercase tracking-widest">
            Refresh
          </button>
        </div>
        <div className="max-h-72 overflow-y-auto">
          {jobs.length === 0 ? (
            <p className="px-4 py-4 font-mono text-[11px] text-on-surface-variant text-center">No recent jobs</p>
          ) : (
            jobs.map((j) => <JobRow key={j.job_id} job={j} />)
          )}
        </div>
      </div>
    </div>
  );
}
