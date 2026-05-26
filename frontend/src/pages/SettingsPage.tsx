import type { ReactElement } from "react";
import { useState } from "react";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="border border-outline-variant bg-surface-container">
      <div className="px-4 py-3 border-b border-outline-variant">
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">{title}</p>
      </div>
      <div className="p-4">{children}</div>
    </div>
  );
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-outline-variant last:border-0">
      <span className="font-mono text-[11px] text-on-surface-variant">{label}</span>
      <div>{children}</div>
    </div>
  );
}

function Toggle({ enabled, onChange }: { enabled: boolean; onChange: (v: boolean) => void }) {
  return (
    <button
      type="button"
      onClick={() => onChange(!enabled)}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors ${enabled ? "bg-secondary" : "bg-surface-variant"}`}
    >
      <span className={`inline-block h-3.5 w-3.5 rounded-full bg-on-primary transition-transform ${enabled ? "translate-x-4" : "translate-x-1"}`} />
    </button>
  );
}

function MaskedKey({ value }: { value: string }) {
  const [show, setShow] = useState(false);
  const display = show ? value : value.slice(0, 8) + "…" + value.slice(-4);
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[11px] text-on-surface-variant">{display}</span>
      <button
        type="button"
        onClick={() => setShow((v) => !v)}
        className="font-mono text-[9px] text-on-surface-variant hover:text-on-surface uppercase tracking-widest"
      >
        {show ? "Hide" : "Show"}
      </button>
    </div>
  );
}

const API_KEYS = [
  { name: "Anthropic Claude", key: "sk-ant-api03-UZ_YQ0vgJ2jZ…", status: "Active", env: "ANTHROPIC_API_KEY" },
  { name: "FRED (Federal Reserve)", key: "2aa765e1ebaa2d19f6f7b4f42cab5789", status: "Active", env: "FRED_API_KEY" },
  { name: "EIA Open Data", key: "RecpLatgJC1oRHzTv6PMgXNDl54uyVNHJov8Cstz", status: "Active", env: "EIA_API_KEY" },
  { name: "Tavily Search", key: "tvly-dev-2EV9yk-0LCutdCNBxLmygREe0kRngeEo…", status: "Active", env: "TAVILY_API_KEY" },
];

const DATA_SOURCES = [
  { name: "CFTC COT Data", description: "Disaggregated futures positioning (weekly ZIP)", status: "Active", latency: "Weekly Wed" },
  { name: "EIA Inventories", description: "Crude oil, nat gas, distillate, gasoline stocks", status: "Active", latency: "Weekly Wed" },
  { name: "FRED Macro", description: "Fed funds rate, CPI, unemployment, yield spread", status: "Active", latency: "Weekly Sun" },
  { name: "Yahoo Finance (yfinance)", description: "Price history, earnings calendar, stock universe", status: "Active", latency: "Daily" },
  { name: "RSS / FinBERT Sentiment", description: "News feeds scored by FinBERT NLP model", status: "Active", latency: "Intraday" },
  { name: "CFTC COT (current year)", description: "Current-year ZIP from cftc.gov", status: "Active", latency: "Weekly" },
];

export default function SettingsPage(): ReactElement {
  const [notifications, setNotifications] = useState({
    signalAlerts: true,
    backtestComplete: true,
    weeklyDigest: false,
    errorAlerts: true,
  });

  const [thresholds, setThresholds] = useState({
    minConfidence: "0.55",
    maxDrawdown: "0.15",
    minSharpe: "1.0",
    spikePctDaily: "2.5",
    spikePctWeekly: "5.0",
  });

  return (
    <div className="p-6 space-y-4 max-w-3xl">
      <div className="border-b border-outline-variant pb-4">
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">System Settings</p>
        <p className="mt-1 font-mono text-xs text-on-surface-variant">Data sources, API credentials, signal thresholds, and alert preferences</p>
      </div>

      <Section title="Signal Thresholds">
        {[
          { key: "minConfidence", label: "Min Confidence Score (BUY filter)" },
          { key: "maxDrawdown", label: "Max Drawdown Limit" },
          { key: "minSharpe", label: "Min Sharpe Ratio" },
          { key: "spikePctDaily", label: "Price Alert — Daily Spike %" },
          { key: "spikePctWeekly", label: "Price Alert — Weekly Spike %" },
        ].map(({ key, label }) => (
          <FieldRow key={key} label={label}>
            <input
              type="text"
              value={thresholds[key as keyof typeof thresholds]}
              onChange={(e) => setThresholds((p) => ({ ...p, [key]: e.target.value }))}
              className="bg-surface-container-high border border-outline-variant px-3 py-1.5 font-mono text-[12px] text-on-surface w-24 text-right focus:outline-none focus:border-outline"
            />
          </FieldRow>
        ))}
        <div className="pt-3 flex justify-end">
          <p className="font-mono text-[10px] text-on-surface-variant opacity-60">Thresholds are read-only here — edit in backend/app/services/alerts_service.py and app/core/config.py</p>
        </div>
      </Section>

      <Section title="Notifications">
        {[
          { key: "signalAlerts", label: "New BUY signal alerts" },
          { key: "backtestComplete", label: "Backtest job completed" },
          { key: "weeklyDigest", label: "Weekly performance digest" },
          { key: "errorAlerts", label: "Pipeline error alerts" },
        ].map(({ key, label }) => (
          <FieldRow key={key} label={label}>
            <Toggle
              enabled={notifications[key as keyof typeof notifications]}
              onChange={(v) => setNotifications((p) => ({ ...p, [key]: v }))}
            />
          </FieldRow>
        ))}
      </Section>

      <Section title="API Keys">
        <p className="font-mono text-[10px] text-on-surface-variant mb-3 opacity-60">Keys are loaded from .env at startup. Rotate by updating .env and restarting the backend.</p>
        <div className="overflow-x-auto -mx-4 -mb-4">
          <table className="w-full text-left">
            <thead className="border-b border-outline-variant bg-surface-container-high">
              <tr>
                {["Service", "Env Var", "Key Preview", "Status"].map((h) => (
                  <th key={h} className="px-4 py-2 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant">
              {API_KEYS.map((k) => (
                <tr key={k.name}>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface">{k.name}</td>
                  <td className="px-4 py-2.5 font-mono text-[10px] text-on-surface-variant">{k.env}</td>
                  <td className="px-4 py-2.5"><MaskedKey value={k.key} /></td>
                  <td className="px-4 py-2.5">
                    <span className="font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border border-secondary/30 bg-secondary/10 text-secondary">
                      {k.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="Data Sources">
        <div className="space-y-0 -mx-4 -mb-4">
          {DATA_SOURCES.map((ds) => (
            <div key={ds.name} className="flex items-start justify-between px-4 py-3 border-b border-outline-variant last:border-0">
              <div>
                <p className="font-mono text-[11px] text-on-surface">{ds.name}</p>
                <p className="font-mono text-[10px] text-on-surface-variant mt-0.5">{ds.description}</p>
              </div>
              <div className="shrink-0 ml-4 text-right">
                <span className="font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border border-secondary/30 bg-secondary/10 text-secondary">
                  {ds.status}
                </span>
                <p className="font-mono text-[9px] text-on-surface-variant mt-1">{ds.latency}</p>
              </div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Environment">
        <FieldRow label="Backend Port"><span className="font-mono text-[12px] text-on-surface">8000</span></FieldRow>
        <FieldRow label="Frontend Port"><span className="font-mono text-[12px] text-on-surface">5173</span></FieldRow>
        <FieldRow label="Database"><span className="font-mono text-[12px] text-on-surface">PostgreSQL (asyncpg)</span></FieldRow>
        <FieldRow label="Cache"><span className="font-mono text-[12px] text-on-surface">Redis</span></FieldRow>
        <FieldRow label="Scheduler"><span className="font-mono text-[12px] text-secondary">Enabled (APScheduler)</span></FieldRow>
        <FieldRow label="Timezone"><span className="font-mono text-[12px] text-on-surface">America/New_York</span></FieldRow>
      </Section>
    </div>
  );
}
