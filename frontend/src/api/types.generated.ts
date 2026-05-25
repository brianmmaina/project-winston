/**
 * JSON contracts returned by the FastAPI backend.
 *
 * Regenerate from OpenAPI via: `npm run generate-types` (requires backend at :8000).
 * This hand-maintained file mirrors the live API until codegen is run.
 */

export interface SentimentBlock {
  score_1d: number;
  score_3d: number;
  momentum: number;
  volume: number;
  label: string;
}

export interface BacktestStatsBlock {
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown: number;
  num_trades: number;
  avg_win_pct?: number;
  avg_loss_pct?: number;
  total_return?: number;
}

export interface ShapFeature {
  feature: string;
  importance: number;
}

export interface SignalPayload {
  ticker: string;
  name: string;
  signal: "BUY" | "HOLD";
  avg_confidence: number;
  confidence_5d: number;
  confidence_10d: number;
  confidence_21d: number;
  current_price: number;
  regime: number;
  regime_label: string;
  regime_confidence: number;
  consensus: boolean;
  position_size_pct: number;
  suggested_action: string;
  sentiment: SentimentBlock;
  backtest: BacktestStatsBlock;
  shap_features: ShapFeature[];
  generated_at: string;
  correlation_filtered: boolean;
}

export interface CommodityRow {
  ticker: string;
  name: string;
  last_close?: number;
}

export interface HistoryBar {
  date: string;
  close: number;
}

export interface MetaResponse {
  refreshed_at?: string;
  last_refresh?: string;
  filtered_count?: number;
  ingestion?: Record<string, unknown>;
  source?: string;
}

export interface BacktestSummaryRow {
  ticker: string;
  horizon: string;
  name: string;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  num_trades: number;
  run_at: string | null;
}

export interface ModelStatRow {
  id: number;
  ticker: string;
  horizon: string;
  trained_at: string | null;
  oos_auc: number | null;
  oos_precision: number | null;
  oos_recall: number | null;
  brier_score: number | null;
  fold: number | null;
}

export interface RefreshResponse {
  ingestion: Record<string, unknown>;
  filtered_count: number;
  refreshed_at: string;
}

export interface RetrainResponse {
  job_id: string;
  status: string;
  name?: string;
}

export interface JobStartResponse {
  job_id: string;
  status: string;
  name: string;
}

export interface JobStatus {
  job_id: string;
  name: string;
  state: "pending" | "running" | "completed" | "failed" | "cancelled";
  message: string | null;
  created_at: string | null;
  updated_at: string | null;
  is_terminal: boolean;
}

// ---------------------------------------------------------------------------
// Stocks (Phase 5+ endpoints)
// ---------------------------------------------------------------------------

export interface StockUniverseRow {
  ticker: string;
  name: string;
  sector: string | null;
  industry: string | null;
  last_close: number | null;
}

export interface StockRankingRow {
  date: string;
  ticker: string;
  name: string | null;
  sector: string | null;
  score: number;
  rank: number;
  in_topk: boolean;
  horizon: string;
  last_close: number | null;
}

export interface StockHoldingRow {
  date: string;
  ticker: string;
  name: string | null;
  sector: string | null;
  weight: number;
  last_price: number | null;
}

export interface PortfolioEquityPoint {
  date: string;
  equity: number;
  benchmark_equity: number | null;
  daily_return: number | null;
  turnover: number | null;
}

export interface StockPortfolioResponse {
  as_of: string | null;
  holdings: StockHoldingRow[];
  equity_curve: PortfolioEquityPoint[];
}

export interface StockBacktestSummary {
  horizon: string;
  run_at: string | null;
  total_return: number;
  sharpe_ratio: number;
  max_drawdown: number;
  win_rate: number;
  benchmark_total_return: number;
  info_ratio_vs_benchmark: number;
  num_rebalances: number;
}

export interface StockModelStatRow {
  fold: number | null;
  horizon: string;
  trained_at: string | null;
  ic: number;
  rank_ic: number;
  top_minus_bottom: number;
  mae: number;
}

export interface StockDetailResponse {
  ticker: string;
  name: string;
  sector: string | null;
  industry: string | null;
  last_close: number | null;
  ranking: {
    date: string;
    score: number;
    rank: number;
    in_topk: boolean;
    horizon: string;
  } | null;
}

export interface StockJobResponse {
  job_id: string;
  status: string;
  name: string;
}
