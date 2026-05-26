import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";
import type React from "react";
import { isMarketHours } from "../utils/marketHours";

import {
  ApiClientError,
  closePaperPosition,
  getPaperPortfolio,
  openPaperPosition,
  resetPaperPortfolio,
  triggerPaperMtm,
} from "../api/client";
import type { PaperPortfolioResponse, PaperPosition, PaperTrade } from "../api/types.generated";
import { PageState } from "../components/PageState";

function errMsg(e: unknown): string {
  if (e instanceof ApiClientError) return e.message;
  return "Unexpected error";
}

function fmt(n: number | null | undefined, digits = 2, suffix = "%"): string {
  if (n == null) return "—";
  return `${n >= 0 ? "+" : ""}${n.toFixed(digits)}${suffix}`;
}

function fmtUsd(n: number | null | undefined): string {
  if (n == null) return "—";
  return `$${n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function PnlCell({ value }: { value: number | null | undefined }) {
  if (value == null) return <span className="text-on-surface-variant">—</span>;
  return (
    <span className={value >= 0 ? "text-secondary" : "text-error"}>
      {fmt(value)}
    </span>
  );
}

function RecBadge({ rec }: { rec: string }) {
  const cls =
    rec === "STRONG_BUY"
      ? "border-secondary/50 bg-secondary/15 text-secondary"
      : rec === "BUY"
      ? "border-secondary/30 bg-secondary/10 text-secondary"
      : "border-outline-variant text-on-surface-variant";
  return (
    <span className={`font-mono text-[9px] font-bold tracking-[0.08em] px-2 py-0.5 border ${cls}`}>
      {rec.replace("_", " ")}
    </span>
  );
}

function StatCard({
  label,
  value,
  sub,
  positive,
}: {
  label: string;
  value: string;
  sub?: string;
  positive?: boolean;
}) {
  const color =
    positive === true ? "text-secondary" : positive === false ? "text-error" : "text-on-surface";
  return (
    <div className="border border-outline-variant bg-surface-container p-4 space-y-1">
      <p className="font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">{label}</p>
      <p className={`font-mono text-2xl font-semibold ${color}`}>{value}</p>
      {sub && <p className="font-mono text-[10px] text-on-surface-variant opacity-70">{sub}</p>}
    </div>
  );
}

function PositionsTable({
  positions,
  onClose,
  closing,
}: {
  positions: PaperPosition[];
  onClose: (ticker: string) => void;
  closing: string | null;
}) {
  if (positions.length === 0)
    return (
      <p className="font-mono text-[11px] text-on-surface-variant py-4 text-center">
        No open positions — agent recommendations will auto-open positions on the next run.
      </p>
    );

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead className="border-b border-outline-variant bg-surface-container-high">
          <tr>
            {["Ticker", "Name", "Rec", "Entry", "Current", "P&L", "Size", "Stop", "Thesis"].map((h) => (
              <th key={h} className="px-3 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">
                {h}
              </th>
            ))}
            <th className="px-3 py-2.5" />
          </tr>
        </thead>
        <tbody className="divide-y divide-outline-variant">
          {positions.map((p) => (
            <tr key={p.id} className="hover:bg-surface-container-high transition-colors">
              <td className="px-3 py-2.5 font-mono text-[13px] font-semibold text-secondary">{p.ticker}</td>
              <td className="px-3 py-2.5 font-mono text-[11px] text-on-surface max-w-[140px] truncate">{p.name ?? "—"}</td>
              <td className="px-3 py-2.5"><RecBadge rec={p.recommendation} /></td>
              <td className="px-3 py-2.5 font-mono text-[11px] tabular-nums text-on-surface">${p.entry_price.toFixed(2)}</td>
              <td className="px-3 py-2.5 font-mono text-[11px] tabular-nums text-on-surface">${p.current_price.toFixed(2)}</td>
              <td className="px-3 py-2.5 font-mono text-[12px] tabular-nums font-semibold">
                <PnlCell value={p.unrealized_pnl_pct} />
              </td>
              <td className="px-3 py-2.5 font-mono text-[11px] tabular-nums text-on-surface-variant">{p.position_size_pct.toFixed(1)}%</td>
              <td className="px-3 py-2.5 font-mono text-[11px] tabular-nums text-error">${p.stop_loss_price.toFixed(2)}</td>
              <td className="px-3 py-2.5 font-mono text-[10px] text-on-surface-variant max-w-[200px] truncate" title={p.thesis ?? ""}>
                {p.thesis ?? "—"}
              </td>
              <td className="px-3 py-2.5">
                <button
                  type="button"
                  disabled={closing === p.ticker}
                  onClick={() => onClose(p.ticker)}
                  className="font-mono text-[9px] font-bold tracking-[0.06em] uppercase px-2 py-1 border border-error/40 text-error hover:bg-error/10 disabled:opacity-40 transition-colors"
                >
                  {closing === p.ticker ? "Closing…" : "Close"}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClosedTable({ positions }: { positions: PaperPosition[] }) {
  if (positions.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left">
        <thead className="border-b border-outline-variant bg-surface-container-high">
          <tr>
            {["Ticker", "Rec", "Entry", "Exit", "P&L", "Reason"].map((h) => (
              <th key={h} className="px-3 py-2.5 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-outline-variant">
          {positions.map((p) => (
            <tr key={p.id} className="opacity-70 hover:opacity-100 transition-opacity">
              <td className="px-3 py-2 font-mono text-[12px] font-semibold text-on-surface-variant">{p.ticker}</td>
              <td className="px-3 py-2"><RecBadge rec={p.recommendation} /></td>
              <td className="px-3 py-2 font-mono text-[11px] tabular-nums">${p.entry_price.toFixed(2)}</td>
              <td className="px-3 py-2 font-mono text-[11px] tabular-nums">${(p.current_price ?? 0).toFixed(2)}</td>
              <td className="px-3 py-2 font-mono text-[12px] tabular-nums font-semibold">
                <PnlCell value={p.realized_pnl_pct} />
              </td>
              <td className="px-3 py-2 font-mono text-[10px] text-on-surface-variant">{p.close_reason ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TradeLog({ trades }: { trades: PaperTrade[] }) {
  return (
    <div className="overflow-x-auto max-h-64 overflow-y-auto">
      <table className="w-full text-left">
        <thead className="border-b border-outline-variant bg-surface-container-high sticky top-0">
          <tr>
            {["Time", "Ticker", "Dir", "Price", "Shares", "Value", "P&L"].map((h) => (
              <th key={h} className="px-3 py-2 font-mono text-[9px] font-bold tracking-[0.1em] uppercase text-on-surface-variant whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-outline-variant">
          {trades.map((t) => (
            <tr key={t.id}>
              <td className="px-3 py-2 font-mono text-[10px] text-on-surface-variant whitespace-nowrap">
                {t.traded_at ? new Date(t.traded_at).toLocaleString() : "—"}
              </td>
              <td className="px-3 py-2 font-mono text-[12px] font-semibold text-on-surface">{t.ticker}</td>
              <td className="px-3 py-2">
                <span className={`font-mono text-[9px] font-bold tracking-[0.06em] px-1.5 py-0.5 border ${
                  t.direction === "BUY"
                    ? "border-secondary/30 bg-secondary/10 text-secondary"
                    : "border-error/30 bg-error/10 text-error"
                }`}>
                  {t.direction}
                </span>
              </td>
              <td className="px-3 py-2 font-mono text-[11px] tabular-nums">${t.price.toFixed(2)}</td>
              <td className="px-3 py-2 font-mono text-[11px] tabular-nums text-on-surface-variant">{t.shares.toFixed(4)}</td>
              <td className="px-3 py-2 font-mono text-[11px] tabular-nums">{fmtUsd(t.value)}</td>
              <td className="px-3 py-2 font-mono text-[11px] tabular-nums">
                <PnlCell value={t.pnl_pct} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OpenForm({ onOpened }: { onOpened: (msg: string) => void }): ReactElement {
  const [open, setOpen] = useState(false);
  const [ticker, setTicker] = useState("");
  const [rec, setRec] = useState<"BUY" | "STRONG_BUY">("BUY");
  const [sizePct, setSizePct] = useState("5");
  const [thesis, setThesis] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    const t = ticker.trim().toUpperCase();
    if (!t) { setErr("Ticker required"); return; }
    const size = parseFloat(sizePct);
    if (isNaN(size) || size < 0.5 || size > 15) { setErr("Size must be 0.5–15%"); return; }
    setSubmitting(true);
    try {
      const r = await openPaperPosition(t, rec, size, thesis.trim() || undefined);
      onOpened(`Opened ${r.opened} @ $${r.entry_price.toFixed(2)} · ${r.position_size_pct.toFixed(1)}% · ${r.shares.toFixed(4)} shares`);
      setTicker(""); setThesis(""); setSizePct("5"); setOpen(false);
    } catch (e2) {
      setErr(e2 instanceof ApiClientError ? e2.message : "Failed to open position");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-3 py-1.5 border border-secondary/40 bg-secondary/10 text-secondary hover:bg-secondary/20 font-mono text-[10px] font-bold tracking-[0.06em] uppercase transition-colors"
      >
        <span className="material-symbols-outlined text-[14px] leading-none">add</span>
        Open Position
      </button>
      {open && (
        <form
          onSubmit={(e) => void onSubmit(e)}
          className="mt-2 border border-outline-variant bg-surface-container p-4 flex flex-wrap gap-3 items-end"
        >
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant">Ticker</label>
            <input
              className="w-24 px-2 py-1.5 border border-outline-variant bg-surface font-mono text-[12px] text-on-surface uppercase focus:outline-none focus:border-secondary"
              placeholder="AAPL"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              maxLength={10}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant">Rec</label>
            <select
              className="px-2 py-1.5 border border-outline-variant bg-surface font-mono text-[11px] text-on-surface focus:outline-none focus:border-secondary"
              value={rec}
              onChange={(e) => setRec(e.target.value as "BUY" | "STRONG_BUY")}
            >
              <option value="BUY">BUY</option>
              <option value="STRONG_BUY">STRONG BUY</option>
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant">Size %</label>
            <input
              type="number"
              className="w-20 px-2 py-1.5 border border-outline-variant bg-surface font-mono text-[12px] text-on-surface focus:outline-none focus:border-secondary"
              min="0.5" max="15" step="0.5"
              value={sizePct}
              onChange={(e) => setSizePct(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1 flex-1 min-w-[180px]">
            <label className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant">Thesis (optional)</label>
            <input
              className="px-2 py-1.5 border border-outline-variant bg-surface font-mono text-[11px] text-on-surface focus:outline-none focus:border-secondary w-full"
              placeholder="e.g. WWDC catalyst play"
              value={thesis}
              onChange={(e) => setThesis(e.target.value)}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              type="submit"
              disabled={submitting}
              className="px-4 py-1.5 bg-secondary text-on-secondary font-mono text-[10px] font-bold tracking-[0.06em] uppercase disabled:opacity-50 hover:bg-secondary-fixed-dim transition-colors"
            >
              {submitting ? "Opening…" : "Open"}
            </button>
            <button
              type="button"
              onClick={() => { setOpen(false); setErr(null); }}
              className="px-3 py-1.5 border border-outline-variant text-on-surface-variant font-mono text-[10px] font-bold uppercase hover:border-outline transition-colors"
            >
              Cancel
            </button>
          </div>
          {err && <p className="w-full font-mono text-[10px] text-error">{err}</p>}
        </form>
      )}
    </div>
  );
}

export default function PaperTradingPage(): ReactElement {
  const [data, setData] = useState<PaperPortfolioResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [closing, setClosing] = useState<string | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [tab, setTab] = useState<"open" | "closed" | "trades">("open");
  const [live, setLive] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getPaperPortfolio());
    } catch (e) {
      setError(errMsg(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  // Poll every 2 min during market hours to stay in sync with the scheduler job
  useEffect(() => {
    const tick = () => {
      const mh = isMarketHours();
      setLive(mh);
      if (mh) void load();
    };
    const id = setInterval(tick, 2 * 60 * 1000);
    setLive(isMarketHours());
    return () => clearInterval(id);
  }, [load]);

  const onClose = async (ticker: string) => {
    setClosing(ticker);
    setActionMsg(null);
    try {
      const r = await closePaperPosition(ticker);
      setActionMsg(`Closed ${r.closed}${r.pnl_pct != null ? ` · P&L ${fmt(r.pnl_pct)}` : ""}`);
      void load();
    } catch (e) {
      setActionMsg(errMsg(e));
    } finally {
      setClosing(null);
    }
  };

  const onMtm = async () => {
    setActionMsg(null);
    try {
      const r = await triggerPaperMtm();
      setActionMsg(`Updated ${r.updated} positions${r.stopped_out.length ? ` · stopped out: ${r.stopped_out.join(", ")}` : ""}`);
      void load();
    } catch (e) {
      setActionMsg(errMsg(e));
    }
  };

  const onReset = async () => {
    if (!confirm("Reset the paper portfolio to $100,000? This deletes all positions and trade history.")) return;
    setActionMsg(null);
    try {
      await resetPaperPortfolio();
      setActionMsg("Portfolio reset to $100,000.");
      void load();
    } catch (e) {
      setActionMsg(errMsg(e));
    }
  };

  const port = data?.portfolio;

  return (
    <div className="p-6 space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <p className="font-mono text-[10px] font-bold tracking-[0.1em] uppercase text-on-surface-variant">
              Paper Trading · Simulated $100,000 portfolio
            </p>
            {live ? (
              <span className="flex items-center gap-1 font-mono text-[9px] font-bold uppercase tracking-widest text-secondary">
                <span className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
                Live · 2 min
              </span>
            ) : (
              <span className="font-mono text-[9px] text-on-surface-variant opacity-40 uppercase tracking-widest">Market closed</span>
            )}
          </div>
          {port?.updated_at && (
            <p className="font-mono text-[10px] text-on-surface-variant opacity-60 mt-0.5">
              Prices as of: {new Date(port.updated_at).toLocaleString()}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <OpenForm onOpened={(msg) => { setActionMsg(msg); void load(); }} />
          <button
            type="button"
            onClick={() => void onMtm()}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-secondary/40 text-secondary hover:bg-secondary/10 font-mono text-[10px] font-bold tracking-[0.06em] uppercase transition-colors"
          >
            <span className="material-symbols-outlined text-[14px] leading-none">price_check</span>
            Mark to Market
          </button>
          <button
            type="button"
            onClick={() => void onReset()}
            className="flex items-center gap-1.5 px-3 py-1.5 border border-outline-variant text-on-surface-variant hover:border-error hover:text-error font-mono text-[10px] font-bold tracking-[0.06em] uppercase transition-colors"
          >
            <span className="material-symbols-outlined text-[14px] leading-none">restart_alt</span>
            Reset
          </button>
        </div>
      </div>

      {actionMsg && (
        <div className="border border-outline-variant bg-surface-container px-3 py-2 font-mono text-[11px] text-on-surface-variant">
          {actionMsg}
        </div>
      )}

      <PageState error={error} onRetry={() => void load()}>
        {loading ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="border border-outline-variant bg-surface-container p-4 h-20 animate-pulse" />
            ))}
          </div>
        ) : port ? (
          <>
            {/* Stats row */}
            <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-7 gap-3">
              <StatCard label="Total Value" value={fmtUsd(port.total_value)} />
              <StatCard
                label="Total P&L"
                value={fmt(port.total_pnl_pct)}
                positive={port.total_pnl_pct > 0 ? true : port.total_pnl_pct < 0 ? false : undefined}
              />
              <StatCard
                label="vs SPY"
                value={fmt(port.spx_pnl_pct)}
                sub={port.alpha_pct != null ? `Alpha ${fmt(port.alpha_pct)}` : undefined}
                positive={port.spx_pnl_pct != null ? port.spx_pnl_pct > 0 : undefined}
              />
              <StatCard label="Cash" value={fmtUsd(port.current_cash)} sub={`of ${fmtUsd(port.initial_capital)}`} />
              <StatCard label="Invested" value={fmtUsd(port.positions_value)} sub={`${port.open_positions_count} positions`} />
              <StatCard
                label="Win Rate"
                value={port.win_rate != null ? `${port.win_rate.toFixed(0)}%` : "—"}
                sub={`${port.closed_positions_count} closed`}
                positive={port.win_rate != null ? port.win_rate >= 50 : undefined}
              />
              <StatCard
                label="Avg Closed P&L"
                value={fmt(port.avg_closed_pnl_pct)}
                positive={port.avg_closed_pnl_pct != null ? port.avg_closed_pnl_pct > 0 : undefined}
              />
            </div>

            {/* Tabs */}
            <div className="flex gap-0 border-b border-outline-variant">
              {(["open", "closed", "trades"] as const).map((t) => {
                const counts = { open: data?.open_positions.length ?? 0, closed: data?.closed_positions.length ?? 0, trades: data?.trades.length ?? 0 };
                const labels = { open: "Open Positions", closed: "Closed", trades: "Trade Log" };
                return (
                  <button
                    key={t}
                    type="button"
                    onClick={() => setTab(t)}
                    className={`px-4 py-2.5 font-mono text-[10px] font-bold tracking-[0.08em] uppercase border-b-2 transition-colors ${
                      tab === t
                        ? "border-secondary text-secondary"
                        : "border-transparent text-on-surface-variant hover:text-on-surface"
                    }`}
                  >
                    {labels[t]} ({counts[t]})
                  </button>
                );
              })}
            </div>

            {/* Tab content */}
            <div className="border border-outline-variant bg-surface-container">
              {tab === "open" && (
                <PositionsTable
                  positions={data?.open_positions ?? []}
                  onClose={(t) => void onClose(t)}
                  closing={closing}
                />
              )}
              {tab === "closed" && <ClosedTable positions={data?.closed_positions ?? []} />}
              {tab === "trades" && <TradeLog trades={data?.trades ?? []} />}
            </div>

            {/* Thesis panel for open positions */}
            {tab === "open" && (data?.open_positions ?? []).some((p) => p.what_breaks_thesis) && (
              <div className="border border-outline-variant bg-surface-container px-4 py-3 space-y-2">
                <p className="font-mono text-[9px] font-bold uppercase tracking-[0.1em] text-on-surface-variant">Exit Conditions</p>
                {(data?.open_positions ?? []).filter((p) => p.what_breaks_thesis).map((p) => (
                  <div key={p.id} className="flex gap-3">
                    <span className="font-mono text-[11px] font-bold text-secondary w-12 shrink-0">{p.ticker}</span>
                    <span className="font-mono text-[10px] text-on-surface-variant">{p.what_breaks_thesis}</span>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : null}
      </PageState>
    </div>
  );
}
