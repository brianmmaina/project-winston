import type { ReactElement } from "react";
import { useEffect, useRef, useState } from "react";

const AGENTS = [
  {
    id: "alpha_parser",
    name: "Alpha Parser",
    description: "Scans news, filings, and alt-data for fundamental alpha signals",
    status: "running",
    model: "gpt-4o",
    lastRun: "2 min ago",
    runCount: 1847,
    successRate: 0.97,
  },
  {
    id: "sentiment_analyzer",
    name: "Sentiment Analyzer",
    description: "NLP scoring of earnings calls, analyst notes, and social data",
    status: "running",
    model: "gpt-4o-mini",
    lastRun: "8 min ago",
    runCount: 3201,
    successRate: 0.99,
  },
  {
    id: "risk_sentinel",
    name: "Risk Sentinel",
    description: "Monitors position-level and portfolio-level risk flags in real time",
    status: "idle",
    model: "gpt-4o",
    lastRun: "1h ago",
    runCount: 422,
    successRate: 0.94,
  },
  {
    id: "catalyst_tracker",
    name: "Catalyst Tracker",
    description: "Identifies upcoming events, earnings dates, and macro catalysts",
    status: "error",
    model: "gpt-4o",
    lastRun: "3h ago",
    runCount: 311,
    successRate: 0.82,
  },
];

const GLOBAL_PARAMS = [
  { key: "confidence_threshold", label: "Confidence Threshold", min: 0.5, max: 1.0, step: 0.01, value: 0.72, unit: "" },
  { key: "max_positions", label: "Max Concurrent Positions", min: 5, max: 50, step: 1, value: 20, unit: "" },
  { key: "lookback_days", label: "Lookback Window", min: 14, max: 252, step: 7, value: 90, unit: "d" },
  { key: "rebalance_freq", label: "Rebalance Frequency", min: 1, max: 21, step: 1, value: 5, unit: "d" },
];

const MOCK_LOG = [
  "[14:32:01] Alpha Parser — scanned 142 SEC filings for NVDA, MSFT, AAPL",
  "[14:32:04] Sentiment Analyzer — processed Q2 earnings call transcript (NVDA): bullish",
  "[14:31:58] Alpha Parser — flagged insider buy pattern in SMCI ($2.1M)",
  "[14:31:52] Risk Sentinel — portfolio VaR (95%): $48,200 within limits",
  "[14:31:44] Alpha Parser — news scan complete: 3 BUY signals, 1 HOLD",
  "[14:31:38] Catalyst Tracker — ERROR: rate limit exceeded on news API, retry in 180s",
  "[14:30:59] Sentiment Analyzer — scored 28 analyst reports across Energy sector",
  "[14:30:44] Alpha Parser — momentum signal detected: WTI crude breakout +2.1%",
  "[14:30:31] Risk Sentinel — drawdown alert cleared for GOLD position",
  "[14:30:18] Alpha Parser — started scheduled scan cycle #1847",
];

function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, string> = {
    running: "border-secondary/30 bg-secondary/10 text-secondary",
    idle: "border-outline-variant text-on-surface-variant",
    error: "border-error/30 bg-error/10 text-error",
  };
  return (
    <span className={`font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border ${cfg[status] ?? cfg.idle}`}>
      {status.toUpperCase()}
    </span>
  );
}

function AgentCard({ agent }: { agent: typeof AGENTS[0] }) {
  return (
    <div className="border border-outline-variant bg-surface-container p-4 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-mono text-[13px] font-semibold text-on-surface">{agent.name}</p>
          <p className="font-mono text-[10px] text-on-surface-variant mt-0.5">{agent.description}</p>
        </div>
        <StatusBadge status={agent.status} />
      </div>
      <div className="grid grid-cols-3 gap-3 pt-1 border-t border-outline-variant">
        <div>
          <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-on-surface-variant">Model</p>
          <p className="font-mono text-[11px] text-on-surface mt-0.5">{agent.model}</p>
        </div>
        <div>
          <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-on-surface-variant">Runs</p>
          <p className="font-mono text-[11px] text-on-surface mt-0.5">{agent.runCount.toLocaleString()}</p>
        </div>
        <div>
          <p className="font-mono text-[9px] uppercase tracking-[0.08em] text-on-surface-variant">Success</p>
          <p className={`font-mono text-[11px] mt-0.5 ${agent.successRate > 0.9 ? "text-secondary" : "text-error"}`}>
            {(agent.successRate * 100).toFixed(0)}%
          </p>
        </div>
      </div>
      <div className="flex items-center justify-between pt-1">
        <span className="font-mono text-[10px] text-on-surface-variant">Last run: {agent.lastRun}</span>
        <div className="flex gap-2">
          <button type="button" className="font-mono text-[9px] font-bold tracking-[0.06em] uppercase px-2.5 py-1 border border-outline-variant text-on-surface-variant hover:border-outline hover:text-on-surface transition-colors">
            Logs
          </button>
          <button type="button" className={`font-mono text-[9px] font-bold tracking-[0.06em] uppercase px-2.5 py-1 border transition-colors ${
            agent.status === "running"
              ? "border-error/40 text-error hover:bg-error/10"
              : "border-secondary/40 text-secondary hover:bg-secondary/10"
          }`}>
            {agent.status === "running" ? "Stop" : "Start"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AgentConfigPage(): ReactElement {
  const [params, setParams] = useState(Object.fromEntries(GLOBAL_PARAMS.map((p) => [p.key, p.value])));
  const [logLines] = useState(MOCK_LOG);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [logLines]);

  return (
    <div className="p-6 space-y-6">
      <div className="border-b border-outline-variant pb-4">
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Agent Configuration</p>
        <p className="mt-1 font-mono text-xs text-on-surface-variant">Manage agent status, global parameters, and monitor the live logic stream</p>
      </div>

      <div>
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant mb-3">Agent Status</p>
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          {AGENTS.map((agent) => <AgentCard key={agent.id} agent={agent} />)}
        </div>
      </div>

      <div className="border border-outline-variant bg-surface-container">
        <div className="px-4 py-3 border-b border-outline-variant">
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Global Parameters</p>
        </div>
        <div className="p-4 space-y-5">
          {GLOBAL_PARAMS.map((param) => (
            <div key={param.key}>
              <div className="flex justify-between mb-2">
                <span className="font-mono text-[11px] text-on-surface-variant">{param.label}</span>
                <span className="font-mono text-[12px] font-semibold text-on-surface">
                  {params[param.key]}{param.unit}
                </span>
              </div>
              <input
                type="range"
                min={param.min}
                max={param.max}
                step={param.step}
                value={params[param.key]}
                onChange={(e) => setParams((p) => ({ ...p, [param.key]: Number(e.target.value) }))}
                className="w-full h-1 appearance-none bg-surface-container-high rounded-none accent-secondary cursor-pointer"
              />
              <div className="flex justify-between mt-1">
                <span className="font-mono text-[9px] text-on-surface-variant">{param.min}{param.unit}</span>
                <span className="font-mono text-[9px] text-on-surface-variant">{param.max}{param.unit}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="px-4 py-3 border-t border-outline-variant flex justify-end">
          <button type="button" className="px-5 py-2 bg-secondary text-on-secondary font-mono text-[11px] font-bold tracking-[0.08em] uppercase hover:bg-secondary-fixed-dim transition-colors">
            Apply Parameters
          </button>
        </div>
      </div>

      <div className="border border-outline-variant bg-surface-container">
        <div className="flex items-center justify-between px-4 py-3 border-b border-outline-variant">
          <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">Live Logic Log</p>
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
            <span className="font-mono text-[9px] text-on-surface-variant uppercase tracking-widest">Live</span>
          </div>
        </div>
        <div
          ref={logRef}
          className="h-52 overflow-y-auto p-4 space-y-1 bg-surface-container-lowest font-mono text-[11px]"
        >
          {logLines.map((line, i) => {
            const isError = line.includes("ERROR");
            const timestamp = line.match(/\[[\d:]+\]/)?.[0] ?? "";
            const rest = line.replace(timestamp, "").trim();
            return (
              <div key={i} className="flex gap-2">
                <span className="text-on-surface-variant shrink-0">{timestamp}</span>
                <span className={isError ? "text-error" : "text-on-surface"}>{rest}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
