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
      <span
        className={`inline-block h-3.5 w-3.5 rounded-full bg-on-primary transition-transform ${enabled ? "translate-x-4" : "translate-x-1"}`}
      />
    </button>
  );
}

export default function SettingsPage(): ReactElement {
  const [notifications, setNotifications] = useState({
    signalAlerts: true,
    backtestComplete: true,
    weeklyDigest: false,
    errorAlerts: true,
  });

  const [thresholds, setThresholds] = useState({
    minConfidence: "0.72",
    maxDrawdown: "0.15",
    minSharpe: "1.0",
  });

  const [apiKeys] = useState([
    { name: "OpenAI GPT-4", key: "sk-...4x9f", status: "Active", added: "2025-04-12" },
    { name: "Polygon.io Market", key: "pg-...8k2m", status: "Active", added: "2025-03-08" },
    { name: "Alpha Vantage", key: "AV-...3n1q", status: "Inactive", added: "2025-01-20" },
  ]);

  return (
    <div className="p-6 space-y-4 max-w-3xl">
      <div className="border-b border-outline-variant pb-4">
        <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">System Settings</p>
        <p className="mt-1 font-mono text-xs text-on-surface-variant">Account profile, appearance, API credentials, and alert thresholds</p>
      </div>

      <Section title="Account Profile">
        <FieldRow label="Display Name">
          <input
            type="text"
            defaultValue="Brian Maina"
            className="bg-surface-container-high border border-outline-variant px-3 py-1.5 font-mono text-[12px] text-on-surface w-48 focus:outline-none focus:border-outline"
          />
        </FieldRow>
        <FieldRow label="Email">
          <span className="font-mono text-[12px] text-on-surface-variant">bmmaina@bu.edu</span>
        </FieldRow>
        <FieldRow label="Timezone">
          <select className="bg-surface-container-high border border-outline-variant px-3 py-1.5 font-mono text-[12px] text-on-surface focus:outline-none">
            <option>America/New_York (ET)</option>
            <option>UTC</option>
            <option>America/Chicago (CT)</option>
          </select>
        </FieldRow>
      </Section>

      <Section title="Appearance">
        <FieldRow label="Theme">
          <div className="flex gap-2">
            {["Terminal Dark", "High Contrast", "Dim"].map((t) => (
              <button
                key={t}
                type="button"
                className={`px-3 py-1 font-mono text-[10px] font-bold tracking-[0.06em] border transition-colors ${
                  t === "Terminal Dark"
                    ? "border-secondary bg-secondary/10 text-secondary"
                    : "border-outline-variant text-on-surface-variant hover:border-outline"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
        </FieldRow>
        <FieldRow label="Data Density">
          <div className="flex gap-2">
            {["Compact", "Default", "Comfortable"].map((d) => (
              <button
                key={d}
                type="button"
                className={`px-3 py-1 font-mono text-[10px] font-bold tracking-[0.06em] border transition-colors ${
                  d === "Default"
                    ? "border-secondary bg-secondary/10 text-secondary"
                    : "border-outline-variant text-on-surface-variant hover:border-outline"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </FieldRow>
      </Section>

      <Section title="Signal Thresholds">
        {[
          { key: "minConfidence", label: "Min Confidence Score", unit: "" },
          { key: "maxDrawdown", label: "Max Drawdown Limit", unit: "" },
          { key: "minSharpe", label: "Min Sharpe Ratio", unit: "" },
        ].map(({ key, label, unit }) => (
          <FieldRow key={key} label={label}>
            <div className="flex items-center gap-2">
              <input
                type="text"
                value={thresholds[key as keyof typeof thresholds]}
                onChange={(e) => setThresholds((p) => ({ ...p, [key]: e.target.value }))}
                className="bg-surface-container-high border border-outline-variant px-3 py-1.5 font-mono text-[12px] text-on-surface w-24 text-right focus:outline-none focus:border-outline"
              />
              {unit && <span className="font-mono text-[11px] text-on-surface-variant">{unit}</span>}
            </div>
          </FieldRow>
        ))}
      </Section>

      <Section title="Notifications">
        {[
          { key: "signalAlerts", label: "New signal alerts" },
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
        <div className="overflow-x-auto -mx-4 -mb-4">
          <table className="w-full text-left">
            <thead className="border-b border-outline-variant bg-surface-container-high">
              <tr>
                {["SERVICE", "KEY", "STATUS", "ADDED"].map((h) => (
                  <th key={h} className="px-4 py-2 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant">
              {apiKeys.map((k) => (
                <tr key={k.name}>
                  <td className="px-4 py-2.5 font-mono text-[12px] text-on-surface">{k.name}</td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant">{k.key}</td>
                  <td className="px-4 py-2.5">
                    <span className={`font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border ${
                      k.status === "Active"
                        ? "border-secondary/30 bg-secondary/10 text-secondary"
                        : "border-outline-variant text-on-surface-variant"
                    }`}>
                      {k.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-[11px] text-on-surface-variant">{k.added}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <div className="flex justify-end">
        <button
          type="button"
          className="px-5 py-2 bg-secondary text-on-secondary font-mono text-[11px] font-bold tracking-[0.08em] uppercase hover:bg-secondary-fixed-dim transition-colors"
        >
          Save Changes
        </button>
      </div>
    </div>
  );
}
