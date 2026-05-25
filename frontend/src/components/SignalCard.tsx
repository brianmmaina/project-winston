/** Card showing one commodity signal: regimes, horizons, sentiment, Kelly (BUY). */

import type { ReactElement } from "react";

import type { SignalPayload } from "../api/types.generated";

function barHue(conf: number): string {
  if (conf >= 0.7) {
    return "bg-emerald-500";
  }
  if (conf >= 0.6) {
    return "bg-lime-400";
  }
  if (conf >= 0.55) {
    return "bg-amber-400";
  }
  return "bg-slate-600";
}

function regimeStyles(label: string): { bg: string; text: string } {
  if (label.includes("Trending")) {
    return { bg: "bg-emerald-900/60", text: "text-emerald-300" };
  }
  if (label.includes("Volatility")) {
    return { bg: "bg-rose-900/60", text: "text-rose-300" };
  }
  return { bg: "bg-amber-900/60", text: "text-amber-300" };
}

interface SignalCardProps {
  signal: SignalPayload;
  muted: boolean;
  onOpen: (ticker: string) => void;
  /** When false, render as a static panel without click navigation. */
  interactive?: boolean;
}

export function SignalCard({ signal, muted, onOpen, interactive = true }: SignalCardProps): ReactElement {
  const rg = regimeStyles(signal.regime_label);
  const buy = signal.signal === "BUY";
  const border = buy ? "border-emerald-800/70" : "border-slate-800";
  const dim = muted ? "opacity-60" : "";

  const inner = (
    <>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-mono text-xs text-slate-500">{signal.ticker}</p>
          <p className="font-semibold text-slate-100">{signal.name}</p>
          <p className="font-mono text-lg text-slate-200">${signal.current_price.toFixed(2)}</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            buy ? "bg-emerald-900/70 text-emerald-200" : "bg-slate-800 text-slate-400"
          }`}
        >
          {signal.signal}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        {(
          [
            ["5d", signal.confidence_5d],
            ["10d", signal.confidence_10d],
            ["21d", signal.confidence_21d],
          ] as const
        ).map(([label, conf]) => (
          <div key={label} className="space-y-1">
            <p className="text-center text-[10px] uppercase tracking-wide text-slate-500">{label}</p>
            <div className="h-2 w-full overflow-hidden rounded bg-slate-800">
              <div className={`h-2 rounded ${barHue(conf)}`} style={{ width: `${Math.min(100, conf * 100)}%` }} />
            </div>
            <p className="font-mono text-center text-xs text-slate-400">{conf.toFixed(2)}</p>
          </div>
        ))}
      </div>

      <div className="mt-3">
        <p className="text-[10px] uppercase text-slate-500">Sentiment (1d)</p>
        <div className="mt-1 h-2 w-full overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-2 rounded-full bg-cyan-500"
            style={{ width: `${Math.min(100, Math.max(0, ((signal.sentiment.score_1d + 1) / 2) * 100))}%` }}
          />
        </div>
        <div className="mt-1 flex justify-between font-mono text-[10px] text-slate-500">
          <span>-1</span>
          <span>{signal.sentiment.score_1d.toFixed(2)}</span>
          <span>+1</span>
        </div>
      </div>

      <div className={`mt-3 inline-flex rounded-md px-2 py-1 text-xs ${rg.bg} ${rg.text}`}>{signal.regime_label}</div>

      {buy ? (
        <p className="mt-3 font-mono text-sm text-emerald-300">
          Kelly sizing: {(signal.position_size_pct * 100).toFixed(2)}%
        </p>
      ) : null}
    </>
  );

  if (!interactive) {
    return (
      <div className={`w-full rounded-xl border ${border} bg-slate-900/80 p-4 text-left shadow-sm ${dim}`}>{inner}</div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onOpen(signal.ticker)}
      className={`w-full rounded-xl border ${border} bg-slate-900/80 p-4 text-left shadow-sm transition hover:border-slate-600 ${dim}`}
    >
      {inner}
    </button>
  );
}
