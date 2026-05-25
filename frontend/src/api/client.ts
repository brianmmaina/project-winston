/**
 * Axios HTTP client for the Commodity Trading Advisor API.
 *
 * Centralizes base URL, timeouts, and error normalization for pages and components.
 */

import axios, { type AxiosError } from "axios";
import type {
  AgentAnalysisMeta,
  AgentAnalysisResult,
  BacktestSummaryRow,
  BacktestStatsBlock,
  CommodityRow,
  DailyScan,
  HistoryBar,
  JobStartResponse,
  JobStatus,
  MetaResponse,
  ModelStatRow,
  PerformanceSummary,
  RefreshResponse,
  RetrainResponse,
  SignalPayload,
  StockBacktestSummary,
  StockDetailResponse,
  StockJobResponse,
  StockModelStatRow,
  StockPortfolioResponse,
  StockRankingRow,
  StockUniverseRow,
} from "./types.generated";

export class ApiClientError extends Error {
  readonly status: number | null;
  readonly isNetwork: boolean;

  constructor(message: string, status: number | null, isNetwork: boolean) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.isNetwork = isNetwork;
  }
}

const BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_KEY = (import.meta.env.VITE_API_KEY as string | undefined) ?? "";

const http = axios.create({
  baseURL: BASE,
  timeout: 30000,
  validateStatus: () => true,
});

if (API_KEY) {
  http.defaults.headers.common["Authorization"] = `Bearer ${API_KEY}`;
}

function normalizeError(err: unknown): ApiClientError {
  if (axios.isAxiosError(err)) {
    const ax = err as AxiosError<{ detail?: string | string[] }>;
    if (!ax.response) {
      return new ApiClientError(ax.message || "Network error", null, true);
    }
    const st = ax.response.status;
    if (st >= 500) {
      return new ApiClientError(`Server error (${st})`, st, false);
    }
    const d = ax.response.data?.detail;
    const msg =
      typeof d === "string"
        ? d
        : Array.isArray(d)
          ? d.join(", ")
          : ax.message || `Request failed (${st})`;
    return new ApiClientError(msg, st, false);
  }
  if (err instanceof Error) {
    return new ApiClientError(err.message, null, true);
  }
  return new ApiClientError("Unexpected error", null, true);
}

async function unwrapJson<T>(promise: Promise<{ status: number; data: unknown }>): Promise<T> {
  try {
    const res = await promise;
    if (res.status >= 200 && res.status < 300) {
      return res.data as T;
    }
    if (res.status >= 500) {
      throw new ApiClientError(`Server error (${res.status})`, res.status, false);
    }
    const data = res.data as { detail?: unknown };
    const detail = data?.detail;
    const msg =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map(String).join(", ")
          : `Request failed (${res.status})`;
    throw new ApiClientError(msg, res.status, false);
  } catch (e) {
    if (e instanceof ApiClientError) {
      throw e;
    }
    throw normalizeError(e);
  }
}

function pathTicker(ticker: string): string {
  return encodeURIComponent(ticker);
}

export async function getSignals(): Promise<SignalPayload[]> {
  return unwrapJson(http.get<SignalPayload[]>("/api/signals"));
}

export async function getRawSignals(): Promise<SignalPayload[]> {
  return unwrapJson(http.get<SignalPayload[]>("/api/signals/raw"));
}

export async function getSignalDetail(ticker: string): Promise<SignalPayload> {
  return unwrapJson(http.get<SignalPayload>(`/api/signals/${pathTicker(ticker)}`));
}

export async function getCommodities(): Promise<CommodityRow[]> {
  return unwrapJson(http.get<CommodityRow[]>("/api/commodities"));
}

export async function getCommodityHistory(ticker: string, days = 180): Promise<HistoryBar[]> {
  const q = new URLSearchParams({ days: String(days) });
  return unwrapJson(http.get<HistoryBar[]>(`/api/commodities/${pathTicker(ticker)}/history?${q}`));
}

export async function getBacktestSummary(): Promise<BacktestSummaryRow[]> {
  return unwrapJson(http.get<BacktestSummaryRow[]>("/api/backtest"));
}

export async function getBacktestDetail(ticker: string): Promise<BacktestStatsBlock> {
  return unwrapJson(http.get<BacktestStatsBlock>(`/api/backtest/${pathTicker(ticker)}`));
}

export async function getModelStats(ticker: string): Promise<ModelStatRow[]> {
  return unwrapJson(http.get<ModelStatRow[]>(`/api/model-stats/${pathTicker(ticker)}`));
}

export async function getMeta(): Promise<MetaResponse> {
  return unwrapJson(http.get<MetaResponse>("/api/meta"));
}

export async function triggerRefresh(): Promise<RefreshResponse> {
  return unwrapJson(http.post<RefreshResponse>("/api/refresh"));
}

export async function triggerRefreshAsync(): Promise<JobStartResponse> {
  return unwrapJson(http.post<JobStartResponse>("/api/refresh-async"));
}

export async function triggerRetrain(): Promise<RetrainResponse> {
  return unwrapJson(http.post<RetrainResponse>("/api/retrain"));
}

export async function getJob(jobId: string): Promise<JobStatus> {
  return unwrapJson(http.get<JobStatus>(`/api/jobs/${encodeURIComponent(jobId)}`));
}

export async function getRecentJobs(limit = 50): Promise<JobStatus[]> {
  const q = new URLSearchParams({ limit: String(limit) });
  return unwrapJson(http.get<JobStatus[]>(`/api/jobs?${q}`));
}

// ---------------------------------------------------------------------------
// Stocks (Phase 5+ endpoints)
// ---------------------------------------------------------------------------

export async function getStockUniverse(): Promise<StockUniverseRow[]> {
  return unwrapJson(http.get<StockUniverseRow[]>("/api/stocks/universe"));
}

export async function getStockRankings(
  horizon: string = "5d",
  topOnly: boolean = false,
): Promise<StockRankingRow[]> {
  const q = new URLSearchParams({ horizon, top_only: String(topOnly) });
  return unwrapJson(http.get<StockRankingRow[]>(`/api/stocks/rankings?${q}`));
}

export async function getStockPortfolio(days: number = 365): Promise<StockPortfolioResponse> {
  const q = new URLSearchParams({ days: String(days) });
  return unwrapJson(http.get<StockPortfolioResponse>(`/api/stocks/portfolio?${q}`));
}

export async function getStockBacktest(): Promise<StockBacktestSummary> {
  return unwrapJson(http.get<StockBacktestSummary>("/api/stocks/backtest"));
}

export async function getStockModelStats(): Promise<StockModelStatRow[]> {
  return unwrapJson(http.get<StockModelStatRow[]>("/api/stocks/model-stats"));
}

export async function getStockDetail(ticker: string): Promise<StockDetailResponse> {
  return unwrapJson(http.get<StockDetailResponse>(`/api/stocks/${pathTicker(ticker)}`));
}

export async function getStockHistory(ticker: string, days: number = 180): Promise<HistoryBar[]> {
  const q = new URLSearchParams({ days: String(days) });
  return unwrapJson(http.get<HistoryBar[]>(`/api/stocks/${pathTicker(ticker)}/history?${q}`));
}

export async function triggerStockRefresh(): Promise<StockJobResponse> {
  return unwrapJson(http.post<StockJobResponse>("/api/stocks/refresh"));
}

export async function triggerStockRetrain(): Promise<StockJobResponse> {
  return unwrapJson(http.post<StockJobResponse>("/api/stocks/retrain"));
}

// ---------------------------------------------------------------------------
// Agent analysis
// ---------------------------------------------------------------------------

export async function triggerAgentAnalysis(): Promise<JobStartResponse> {
  return unwrapJson(http.post<JobStartResponse>("/api/agent-analysis"));
}

export async function getAgentAnalysisLatest(): Promise<AgentAnalysisResult> {
  return unwrapJson(http.get<AgentAnalysisResult>("/api/agent-analysis/latest"));
}

export async function getAgentAnalysisMeta(): Promise<AgentAnalysisMeta> {
  return unwrapJson(http.get<AgentAnalysisMeta>("/api/agent-analysis/meta"));
}

export async function getAgentDailyScan(): Promise<DailyScan> {
  return unwrapJson(http.get<DailyScan>("/api/agent-analysis/daily-scan"));
}

export async function triggerDailyScan(): Promise<{ status: string }> {
  return unwrapJson(http.post<{ status: string }>("/api/agent-analysis/daily-scan"));
}

export async function getAgentPerformance(): Promise<PerformanceSummary> {
  return unwrapJson(http.get<PerformanceSummary>("/api/agent-analysis/performance"));
}

export async function triggerOutcomeCheck(): Promise<{ status: string }> {
  return unwrapJson(http.post<{ status: string }>("/api/agent-analysis/check-outcomes"));
}
