/** Top-level SPA shell: stale-data banner, navigation, routed pages. */

import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";

import { ApiClientError, getMeta, triggerRefresh } from "./api/client";
import CommodityDetail from "./pages/CommodityDetail";
import Dashboard from "./pages/Dashboard";
import BacktestReport from "./pages/BacktestReport";
import StockDetail from "./pages/StockDetail";
import StocksDashboard from "./pages/StocksDashboard";
import StocksPortfolio from "./pages/StocksPortfolio";
import AgentAnalysisPage from "./pages/AgentAnalysisPage";
import { isTimestampStale } from "./utils/stale";

const DAY_MS = 24 * 60 * 60 * 1000;

function StaleBanner(): ReactElement {
  const [stale, setStale] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const probe = useCallback(async () => {
    try {
      const meta = await getMeta();
      const iso = meta.last_refresh ?? meta.refreshed_at;
      setStale(isTimestampStale(iso, DAY_MS));
      setMessage(null);
    } catch (err) {
      if (err instanceof ApiClientError && err.status === 404) {
        setStale(true);
      } else {
        setStale(true);
        setMessage("Could not read metadata.");
      }
    }
  }, []);

  useEffect(() => {
    void probe();
  }, [probe]);

  const label = useMemo(() => {
    if (message) {
      return message;
    }
    return "Market snapshot may be stale (older than 24h). Refresh to ingest latest feeds.";
  }, [message]);

  const onRefresh = async () => {
    setBusy(true);
    try {
      await triggerRefresh();
      await probe();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Refresh failed.");
    } finally {
      setBusy(false);
    }
  };

  if (!stale) {
    return <></>;
  }

  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-amber-900/50 bg-amber-950/50 px-4 py-3 text-amber-100">
      <p className="text-sm">{label}</p>
      <button
        type="button"
        disabled={busy}
        onClick={() => void onRefresh()}
        className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-semibold text-amber-50 hover:bg-amber-500 disabled:opacity-50"
      >
        {busy ? "Refreshing…" : "Refresh now"}
      </button>
    </div>
  );
}

function Navigation(): ReactElement {
  const linkCls = ({ isActive }: { isActive: boolean }): string =>
    `rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-emerald-900/50 text-emerald-200" : "text-slate-400 hover:bg-slate-900"}`;

  return (
    <nav className="border-b border-slate-900 bg-slate-950/80">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3">
        <span className="font-semibold tracking-tight text-slate-100">Advisor</span>
        <div className="flex flex-wrap gap-2">
          <NavLink className={linkCls} to="/commodities" end>
            Commodities
          </NavLink>
          <NavLink className={linkCls} to="/stocks" end>
            Stocks
          </NavLink>
          <NavLink className={linkCls} to="/stocks/portfolio">
            Portfolio
          </NavLink>
          <NavLink className={linkCls} to="/backtest">
            Backtest report
          </NavLink>
          <NavLink className={linkCls} to="/agent-analysis">
            Agent Analysis
          </NavLink>
        </div>
      </div>
    </nav>
  );
}

export default function App(): ReactElement {
  return (
    <BrowserRouter>
      <StaleBanner />
      <Navigation />
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/commodities" element={<Dashboard />} />
        <Route path="/commodity/:ticker" element={<CommodityDetail />} />
        <Route path="/stocks" element={<StocksDashboard />} />
        <Route path="/stocks/portfolio" element={<StocksPortfolio />} />
        <Route path="/stocks/:ticker" element={<StockDetail />} />
        <Route path="/backtest" element={<BacktestReport />} />
        <Route path="/agent-analysis" element={<AgentAnalysisPage />} />
      </Routes>
    </BrowserRouter>
  );
}
