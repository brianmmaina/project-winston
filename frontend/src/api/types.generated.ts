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
  expected_return_pct?: number;
  downside_risk_pct?: number;
  suggested_action: string;
  sentiment: SentimentBlock;
  backtest: BacktestStatsBlock;
  shap_features: ShapFeature[];
  generated_at: string;
  correlation_filtered: boolean;
  risk_flags?: string[];
}

export interface PortfolioRiskSummary {
  total_exposure_pct: number;
  commodity_exposure_pct: number;
  equity_exposure_pct: number;
  by_sector: Record<string, number>;
  buy_count: number;
  risk_flagged: string[];
  limits: {
    max_commodity_pct: number;
    max_equity_pct: number;
    max_sector_pct: number;
    max_single_pct: number;
  };
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
  momentum_score?: number | null;
  quality_score?: number | null;
  value_score?: number | null;
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

// ---------------------------------------------------------------------------
// Agent analysis
// ---------------------------------------------------------------------------

export interface AgentSignal {
  ticker: string;
  name?: string;
  ml_signal: string;
  agent_view: "agree" | "cautious" | "disagree" | "neutral";
  conviction: "high" | "medium" | "low";
  key_factors: string[];
  risks: string[];
}

export interface SubAgentParsed {
  agent: string;
  summary: string;
  signals: AgentSignal[];
  top_picks: string[];
  caution_flags: string[];
  news_highlights: string[];
}

export interface SubAgentReport {
  name: string;
  text: string;
  parsed: Partial<SubAgentParsed>;
  error: string | null;
}

export interface VerifiedTrade {
  ticker: string;
  asset_class: string;
  sector: string;
  ml_signal: string;
  final_recommendation: "STRONG_BUY" | "BUY" | "HOLD" | "AVOID";
  conviction: "high" | "medium" | "low";
  horizon?: "short" | "medium";
  position_size_pct?: number;
  agent_consensus: "strong_agree" | "agree" | "mixed" | "disagree";
  catalyst?: string | null;
  catalyst_date?: string | null;
  supporting_themes: string[];
  risk_factors: string[];
  what_breaks_thesis?: string;
  suggested_action: string;
}

export interface WatchlistItem {
  ticker: string;
  reason: string;
  trigger?: string;
}

export interface OverseerParsed {
  market_overview: string;
  portfolio_thesis?: string;
  verified_trades: VerifiedTrade[];
  watchlist: WatchlistItem[];
  top_risks: string[];
  cross_asset_themes: string[];
  generated_at: string;
}

export interface OverseerReport {
  text: string;
  parsed: Partial<OverseerParsed>;
  error: string | null;
}

export interface BullDebateResult {
  ticker: string;
  bull_rebuttal: string;
  supporting_catalysts: string[];
  risk_reward: string;
  options_confirmation?: string;
  verdict: "CONFIRM_BUY" | "REDUCE_CONVICTION" | "HOLD";
  conviction: "high" | "medium" | "low";
  summary: string;
}

export interface BearRebuttalResult {
  ticker: string;
  steelman_bull_case: string;
  bull_catalysts: string[];
  entry_price_that_works?: string;
  verdict: "CONFIRM_AVOID" | "WATCH" | "RECONSIDER";
  summary: string;
}

export interface DebateReport {
  bull_debates: Record<string, Partial<BullDebateResult>>;
  bear_rebuttals: Record<string, Partial<BearRebuttalResult>>;
}

export interface AgentAnalysisResult {
  run_id?: string;
  sub_reports: SubAgentReport[];
  catalyst_report?: {
    text: string;
    parsed: Partial<CatalystParsed>;
    error: string | null;
  };
  bear_report?: {
    text: string;
    parsed: Partial<BearParsed>;
    error: string | null;
  };
  debate_report?: DebateReport;
  overseer: OverseerReport;
  generated_at: string;
  sub_agent_count: number;
  sub_agent_success_count: number;
}

export interface AgentAnalysisMeta {
  generated_at: string;
  sub_agent_count: number;
  sub_agent_success_count: number;
  overseer_ok: boolean;
}

export interface CatalystPlay {
  ticker: string;
  catalyst_type: string;
  catalyst_description: string;
  catalyst_date: string | null;
  directional_bias: "bullish" | "bearish" | "binary";
  options_priced_in: boolean | null;
  atm_iv_pct: number | null;
  iv_hv_ratio: number | null;
  setup_quality: "excellent" | "good" | "fair" | "poor";
  rationale: string;
}

export interface CatalystParsed {
  catalyst_plays: CatalystPlay[];
  macro_events_next_4w: string[];
  summary: string;
}

export interface BearCase {
  strength: "high" | "medium" | "low";
  key_objection: string;
  what_breaks_thesis: string;
  valuation_concern: string;
  crowding_risk: string;
  downgrade_risk: string;
}

export interface BearParsed {
  bear_cases: Record<string, BearCase>;
  highest_risk_picks: string[];
  picks_to_avoid: string[];
  summary: string;
}

export interface DailyScanAlert {
  ticker: string;
  severity: "high" | "medium" | "low";
  alert: string;
  action: "exit" | "reduce" | "hold" | "add";
  rationale: string;
}

export interface DailyScan {
  alerts: DailyScanAlert[];
  portfolio_health: "healthy" | "some_concerns" | "deteriorating";
  market_note: string;
  scanned_at: string;
  active_picks_count: number;
  skipped?: boolean;
  reason?: string;
}

export interface RecommendationRecord {
  id: number;
  run_id: string;
  ticker: string;
  sector: string | null;
  horizon: string | null;
  final_recommendation: string;
  conviction: string | null;
  position_size_pct: number | null;
  thesis: string | null;
  catalyst: string | null;
  catalyst_date: string | null;
  what_breaks_thesis: string | null;
  entry_price: number | null;
  entry_date: string | null;
  return_2w_pct: number | null;
  return_4w_pct: number | null;
  return_8w_pct: number | null;
  spx_return_2w_pct: number | null;
  spx_return_4w_pct: number | null;
  spx_return_8w_pct: number | null;
  check_2w_date: string | null;
  check_4w_date: string | null;
  check_8w_date: string | null;
}

// ---------------------------------------------------------------------------
// COT Positioning
// ---------------------------------------------------------------------------

export interface CotPoint {
  report_date: string;
  comm_net: number | null;
  spec_net: number | null;
  spec_pct_long: number | null;
  open_interest: number | null;
}

export interface CotResponse {
  latest: CotPoint | null;
  history: CotPoint[];
}

// ---------------------------------------------------------------------------
// Alerts
// ---------------------------------------------------------------------------

export interface MarketAlert {
  id: number;
  ticker: string;
  alert_type: "price_spike" | "weekly_move" | "position_adverse" | string;
  severity: "high" | "medium" | "low";
  triggered_at: string;
  message: string;
  price: number | null;
  change_pct: number | null;
  acknowledged: boolean;
}

// ---------------------------------------------------------------------------
// Calendar
// ---------------------------------------------------------------------------

export interface EconomicEvent {
  event_type: string;
  event_date: string;
  description: string;
  impact: string;
  forecast_value: number | null;
  actual_value: number | null;
}

export interface EarningsEvent {
  ticker: string;
  earnings_date: string;
  timing: string | null;
  eps_estimate: number | null;
}

// ---------------------------------------------------------------------------
// Paper trading
// ---------------------------------------------------------------------------

export interface PaperPortfolioSummary {
  initial_capital: number;
  current_cash: number;
  positions_value: number;
  total_value: number;
  total_pnl_pct: number;
  spx_pnl_pct: number | null;
  alpha_pct: number | null;
  open_positions_count: number;
  closed_positions_count: number;
  win_rate: number | null;
  avg_closed_pnl_pct: number | null;
  updated_at: string | null;
}

export interface PaperPosition {
  id: number;
  ticker: string;
  name: string | null;
  sector: string | null;
  asset_class: string | null;
  recommendation: string;
  conviction: string | null;
  thesis: string | null;
  what_breaks_thesis: string | null;
  entry_price: number;
  entry_date: string | null;
  shares: number;
  position_size_pct: number;
  stop_loss_price: number;
  current_price: number;
  unrealized_pnl_pct: number;
  position_value: number;
  is_open: boolean;
  close_reason: string | null;
  realized_pnl_pct: number | null;
}

export interface PaperTrade {
  id: number;
  ticker: string;
  direction: "BUY" | "SELL";
  price: number;
  shares: number;
  value: number;
  pnl_pct: number | null;
  reason: string;
  traded_at: string | null;
}

export interface PaperPortfolioResponse {
  portfolio: PaperPortfolioSummary;
  open_positions: PaperPosition[];
  closed_positions: PaperPosition[];
  trades: PaperTrade[];
}

export interface PriceTriggerEvent {
  ticker: string;
  name: string;
  direction: "above" | "below";
  deviation_pct: number;
  latest_price: number;
  sma_20d: number;
  triggered_at: string;
}

export interface PerformanceSummary {
  total_recommendations: number;
  avg_return_2w_pct: number | null;
  avg_spx_return_2w_pct: number | null;
  avg_alpha_2w_pct: number | null;
  avg_return_4w_pct: number | null;
  avg_spx_return_4w_pct: number | null;
  avg_alpha_4w_pct: number | null;
  records: RecommendationRecord[];
}
