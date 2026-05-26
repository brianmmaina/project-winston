import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";

import { ApiClientError, getAlerts, acknowledgeAlert, getMeta, getRawSignals, triggerRefresh } from "./api/client";
import type { MarketAlert, SignalPayload } from "./api/types.generated";
import CommodityDetail from "./pages/CommodityDetail";
import Dashboard from "./pages/Dashboard";
import BacktestReport from "./pages/BacktestReport";
import StockDetail from "./pages/StockDetail";
import StocksDashboard from "./pages/StocksDashboard";
import StocksPortfolio from "./pages/StocksPortfolio";
import AgentAnalysisPage from "./pages/AgentAnalysisPage";
import PerformancePage from "./pages/PerformancePage";
import SettingsPage from "./pages/SettingsPage";
import AgentConfigPage from "./pages/AgentConfigPage";
import PaperTradingPage from "./pages/PaperTradingPage";
import { isTimestampStale } from "./utils/stale";
import { useLivePrices } from "./hooks/useLivePrices";

const DAY_MS = 24 * 60 * 60 * 1000;

const NAV_ITEMS = [
  { to: "/commodities", end: true, icon: "inventory_2", label: "Commodities" },
  { to: "/stocks", end: true, icon: "candlestick_chart", label: "Equities" },
  { to: "/stocks/portfolio", end: false, icon: "account_balance_wallet", label: "Portfolio" },
  { to: "/backtest", end: false, icon: "history", label: "Backtest" },
  { to: "/performance", end: false, icon: "bar_chart", label: "Performance" },
  { to: "/agent-analysis", end: false, icon: "psychology", label: "Agent Analysis" },
  { to: "/paper-trading", end: false, icon: "science", label: "Paper Trading" },
];

const BOTTOM_ITEMS = [
  { to: "/agent-config", end: false, icon: "tune", label: "Agent Config" },
  { to: "/settings", end: false, icon: "settings", label: "Settings" },
];

function Sidebar(): ReactElement {
  const navCls = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-2.5 text-label-caps tracking-[0.05em] uppercase transition-colors ${
      isActive
        ? "bg-surface-container-highest border-r-2 border-secondary text-on-surface"
        : "text-on-surface-variant hover:bg-surface-container hover:text-on-surface border-r-2 border-transparent"
    }`;

  return (
    <aside className="flex h-full w-64 flex-col bg-surface-container-low border-r border-outline-variant shrink-0">
      <div className="flex items-center gap-3 px-4 h-12 border-b border-outline-variant shrink-0">
        <div className="flex items-center justify-center w-7 h-7 bg-secondary rounded">
          <span className="text-on-secondary font-mono font-bold text-xs">W</span>
        </div>
        <div className="flex flex-col leading-none">
          <span className="text-on-surface font-mono font-semibold text-xs tracking-widest uppercase">Winston</span>
          <span className="text-on-surface-variant font-mono text-[9px] tracking-widest uppercase mt-0.5">Advisor Terminal</span>
        </div>
      </div>

      <nav className="flex flex-col flex-1 py-2 overflow-y-auto">
        <div className="mb-1">
          <div className="px-4 py-1.5">
            <span className="text-[9px] font-mono font-bold tracking-[0.12em] uppercase text-on-surface-variant opacity-60">Markets</span>
          </div>
          {NAV_ITEMS.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={navCls}>
              <span className="material-symbols-outlined text-[18px] leading-none">{item.icon}</span>
              <span className="font-mono text-[11px] font-bold tracking-[0.05em]">{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>

      <div className="border-t border-outline-variant py-2 shrink-0">
        <div className="px-4 py-1.5">
          <span className="text-[9px] font-mono font-bold tracking-[0.12em] uppercase text-on-surface-variant opacity-60">System</span>
        </div>
        {BOTTOM_ITEMS.map((item) => (
          <NavLink key={item.to} to={item.to} end={item.end} className={navCls}>
            <span className="material-symbols-outlined text-[18px] leading-none">{item.icon}</span>
            <span className="font-mono text-[11px] font-bold tracking-[0.05em]">{item.label}</span>
          </NavLink>
        ))}
      </div>
    </aside>
  );
}

function AlertsDropdown({ alerts, onAck }: { alerts: MarketAlert[]; onAck: (id: number) => void }): ReactElement {
  const [open, setOpen] = useState(false);
  const unacked = alerts.filter((a) => !a.acknowledged);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center gap-1.5 px-2.5 py-1 border border-outline-variant text-on-surface-variant hover:text-on-surface hover:border-outline transition-colors rounded"
      >
        <span className="material-symbols-outlined text-[14px] leading-none">notifications</span>
        <span className="font-mono text-[10px] uppercase tracking-widest font-bold">Alerts</span>
        {unacked.length > 0 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-error text-on-error text-[9px] font-mono font-bold flex items-center justify-center">
            {unacked.length > 9 ? "9+" : unacked.length}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-9 z-50 w-96 max-h-80 overflow-y-auto bg-surface-container border border-outline-variant rounded shadow-lg">
          <div className="px-3 py-2 border-b border-outline-variant flex items-center justify-between">
            <span className="font-mono text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
              Market Alerts {unacked.length > 0 && `· ${unacked.length} unread`}
            </span>
            <button type="button" onClick={() => setOpen(false)}>
              <span className="material-symbols-outlined text-[14px] text-on-surface-variant">close</span>
            </button>
          </div>
          {alerts.length === 0 ? (
            <div className="px-3 py-4 text-center font-mono text-[11px] text-on-surface-variant">No recent alerts</div>
          ) : (
            alerts.slice(0, 20).map((a) => (
              <div key={a.id} className={`px-3 py-2.5 border-b border-outline-variant last:border-0 ${a.acknowledged ? "opacity-50" : ""}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5 min-w-0">
                    <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${a.severity === "high" ? "bg-error" : a.severity === "medium" ? "bg-warning" : "bg-secondary"}`} />
                    <span className="font-mono text-[10px] font-bold text-on-surface">{a.ticker}</span>
                    <span className="font-mono text-[9px] text-on-surface-variant uppercase">{a.alert_type.replace("_", " ")}</span>
                  </div>
                  {!a.acknowledged && (
                    <button
                      type="button"
                      onClick={() => onAck(a.id)}
                      className="shrink-0 font-mono text-[9px] text-on-surface-variant hover:text-on-surface uppercase tracking-widest"
                    >
                      Ack
                    </button>
                  )}
                </div>
                <p className="font-mono text-[10px] text-on-surface mt-0.5 leading-snug">{a.message}</p>
                <p className="font-mono text-[9px] text-on-surface-variant mt-0.5">
                  {new Date(a.triggered_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

function Topbar({ stale, onRefresh, refreshing, alerts, onAckAlert }: {
  stale: boolean;
  onRefresh: () => void;
  refreshing: boolean;
  alerts: MarketAlert[];
  onAckAlert: (id: number) => void;
}): ReactElement {
  const location = useLocation();
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const title = useMemo(() => {
    const p = location.pathname;
    if (p.startsWith("/stocks/portfolio")) return "Portfolio";
    if (p.startsWith("/stocks/")) {
      const ticker = p.split("/").pop()?.toUpperCase() ?? "";
      return ticker ? `Equity · ${ticker}` : "Equity Detail";
    }
    if (p === "/stocks") return "Equities";
    if (p.startsWith("/commodity/")) {
      const ticker = p.split("/").pop()?.toUpperCase() ?? "";
      return ticker ? `Commodity · ${ticker}` : "Commodity Detail";
    }
    if (p === "/commodities" || p === "/") return "Commodities";
    if (p === "/backtest") return "Backtest Report";
    if (p === "/performance") return "Performance";
    if (p === "/agent-analysis") return "Agent Analysis";
    if (p === "/agent-config") return "Agent Configuration";
    if (p === "/settings") return "Settings";
    if (p === "/paper-trading") return "Paper Trading";
    return "Dashboard";
  }, [location.pathname]);

  const timeStr = now.toLocaleTimeString("en-US", { hour12: false });
  const dateStr = now.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }).toUpperCase();

  return (
    <header className="flex items-center justify-between h-12 px-4 bg-surface-container-low border-b border-outline-variant shrink-0">
      <span className="font-mono font-semibold text-sm text-on-surface tracking-tight">{title}</span>
      <div className="flex items-center gap-4">
        {stale && (
          <button
            type="button"
            disabled={refreshing}
            onClick={onRefresh}
            className="flex items-center gap-1.5 px-2.5 py-1 border border-outline-variant text-on-surface-variant hover:text-on-surface hover:border-outline transition-colors rounded"
          >
            <span className="material-symbols-outlined text-[14px] leading-none">refresh</span>
            <span className="font-mono text-[10px] uppercase tracking-widest font-bold">
              {refreshing ? "Refreshing…" : "Stale · Refresh"}
            </span>
          </button>
        )}
        <AlertsDropdown alerts={alerts} onAck={onAckAlert} />
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse" />
          <span className="font-mono text-[10px] text-on-surface-variant tracking-wider">LIVE</span>
        </div>
        <span className="font-mono text-[11px] text-on-surface-variant">{dateStr} · {timeStr}</span>
      </div>
    </header>
  );
}

function Footer(): ReactElement {
  const [signals, setSignals] = useState<SignalPayload[]>([]);

  useEffect(() => {
    getRawSignals().then(setSignals).catch(() => {});
  }, []);

  const items = signals
    .slice()
    .sort((a, b) => b.avg_confidence - a.avg_confidence)
    .slice(0, 12);

  const tickers = items.map((s) => s.ticker);
  const livePrices = useLivePrices(tickers);

  return (
    <footer className="flex items-center h-8 bg-surface-container-lowest border-t border-outline-variant px-4 gap-6 overflow-hidden shrink-0">
      {items.length === 0 ? (
        <span className="font-mono text-[10px] text-on-surface-variant opacity-50">No price data — run a refresh</span>
      ) : (
        items.map((s) => {
          const isBuy = s.signal === "BUY";
          const price = livePrices[s.ticker] ?? s.current_price;
          const isLive = livePrices[s.ticker] != null;
          return (
            <div key={s.ticker} className="flex items-center gap-2 shrink-0">
              <span className="font-mono text-[10px] font-bold text-on-surface-variant tracking-[0.06em]">{s.ticker}</span>
              <span className="font-mono text-[11px] text-on-surface flex items-center gap-1">
                ${price.toFixed(2)}
                {isLive && <span className="w-1 h-1 rounded-full bg-secondary animate-pulse" />}
              </span>
              <span className={`font-mono text-[10px] ${isBuy ? "text-secondary" : "text-on-surface-variant"}`}>
                {s.avg_confidence.toFixed(2)}
              </span>
            </div>
          );
        })
      )}
    </footer>
  );
}

function Shell(): ReactElement {
  const [stale, setStale] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [alerts, setAlerts] = useState<MarketAlert[]>([]);

  const probe = useCallback(async () => {
    try {
      const meta = await getMeta();
      const iso = meta.last_refresh ?? meta.refreshed_at;
      setStale(isTimestampStale(iso, DAY_MS));
    } catch (err) {
      if (err instanceof ApiClientError) {
        setStale(true);
      }
    }
  }, []);

  const fetchAlerts = useCallback(async () => {
    try {
      const data = await getAlerts(50);
      setAlerts(data);
    } catch {
      // alerts are non-critical
    }
  }, []);

  useEffect(() => { void probe(); void fetchAlerts(); }, [probe, fetchAlerts]);

  // Re-fetch alerts every 5 minutes
  useEffect(() => {
    const id = setInterval(() => { void fetchAlerts(); }, 5 * 60 * 1000);
    return () => clearInterval(id);
  }, [fetchAlerts]);

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await triggerRefresh();
      await probe();
    } finally {
      setRefreshing(false);
    }
  };

  const onAckAlert = async (id: number) => {
    try {
      await acknowledgeAlert(id);
      setAlerts((prev) => prev.map((a) => a.id === id ? { ...a, acknowledged: true } : a));
    } catch {
      // best-effort
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar stale={stale} onRefresh={() => void onRefresh()} refreshing={refreshing} alerts={alerts} onAckAlert={onAckAlert} />
        <main className="flex-1 overflow-y-auto overflow-x-hidden bg-surface">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/commodities" element={<Dashboard />} />
            <Route path="/commodity/:ticker" element={<CommodityDetail />} />
            <Route path="/stocks" element={<StocksDashboard />} />
            <Route path="/stocks/portfolio" element={<StocksPortfolio />} />
            <Route path="/stocks/:ticker" element={<StockDetail />} />
            <Route path="/backtest" element={<BacktestReport />} />
            <Route path="/agent-analysis" element={<AgentAnalysisPage />} />
            <Route path="/performance" element={<PerformancePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/agent-config" element={<AgentConfigPage />} />
            <Route path="/paper-trading" element={<PaperTradingPage />} />
          </Routes>
        </main>
        <Footer />
      </div>
    </div>
  );
}

export default function App(): ReactElement {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}
