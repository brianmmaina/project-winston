import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes, useLocation } from "react-router-dom";

import { ApiClientError, getMeta, triggerRefresh } from "./api/client";
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
import { isTimestampStale } from "./utils/stale";

const DAY_MS = 24 * 60 * 60 * 1000;

const NAV_ITEMS = [
  { to: "/commodities", end: true, icon: "inventory_2", label: "Commodities" },
  { to: "/stocks", end: true, icon: "candlestick_chart", label: "Equities" },
  { to: "/stocks/portfolio", end: false, icon: "account_balance_wallet", label: "Portfolio" },
  { to: "/backtest", end: false, icon: "history", label: "Backtest" },
  { to: "/performance", end: false, icon: "bar_chart", label: "Performance" },
  { to: "/agent-analysis", end: false, icon: "psychology", label: "Agent Analysis" },
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

function Topbar({ stale, onRefresh, refreshing }: {
  stale: boolean;
  onRefresh: () => void;
  refreshing: boolean;
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
  const tickers = [
    { label: "SPX", value: "5,892.34", chg: "+0.41%" },
    { label: "VIX", value: "14.72", chg: "-2.31%" },
    { label: "10Y", value: "4.418%", chg: "+0.02" },
    { label: "DXY", value: "99.84", chg: "-0.18%" },
    { label: "BTC", value: "108,420", chg: "+1.23%" },
    { label: "WTI", value: "72.14", chg: "-0.54%" },
    { label: "GOLD", value: "3,315.80", chg: "+0.37%" },
    { label: "EUR/USD", value: "1.0812", chg: "+0.09%" },
  ];

  return (
    <footer className="flex items-center h-8 bg-surface-container-lowest border-t border-outline-variant px-4 gap-6 overflow-hidden shrink-0">
      {tickers.map((t) => {
        const positive = t.chg.startsWith("+");
        return (
          <div key={t.label} className="flex items-center gap-2 shrink-0">
            <span className="font-mono text-[10px] font-bold text-on-surface-variant tracking-[0.06em]">{t.label}</span>
            <span className="font-mono text-[11px] text-on-surface">{t.value}</span>
            <span className={`font-mono text-[10px] ${positive ? "text-secondary" : "text-error"}`}>{t.chg}</span>
          </div>
        );
      })}
    </footer>
  );
}

function Shell(): ReactElement {
  const [stale, setStale] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

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

  useEffect(() => { void probe(); }, [probe]);

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await triggerRefresh();
      await probe();
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-surface">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar stale={stale} onRefresh={() => void onRefresh()} refreshing={refreshing} />
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
