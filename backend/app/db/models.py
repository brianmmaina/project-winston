from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CommodityPrice(Base):
    __tablename__ = "commodity_prices"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_commodity_price_ticker_date"),
        Index("ix_commodity_prices_ticker_date", "ticker", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    high: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    low: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    close: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))


class MacroIndicator(Base):
    __tablename__ = "macro_indicators"
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    fed_funds_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    usd_eur: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    usd_jpy: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    yield_spread_10y2y: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    breakeven_inflation: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    vix: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    cpi_yoy: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    # optional raw refs for reproducibility / debugging (not strictly in spec schema)
    wti_spot: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    gold_fix: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    unrate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))


class SentimentScore(Base):
    __tablename__ = "sentiment_scores"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_sentiment_ticker_date"),
        Index("ix_sentiment_ticker_date", "ticker", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    score_1d: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    score_3d: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    volume: Mapped[int | None] = mapped_column(Integer)
    momentum: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        Index("ix_signals_generated_at", "generated_at"),
        Index("ix_signals_asset_class", "asset_class"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    signal: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False, server_default="commodity")
    avg_confidence: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    confidence_5d: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    confidence_10d: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    confidence_21d: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    regime: Mapped[int | None] = mapped_column(Integer)
    position_size_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    shap_json: Mapped[dict | None] = mapped_column(JSONB)
    sentiment_json: Mapped[dict | None] = mapped_column(JSONB)
    correlation_filtered: Mapped[bool | None] = mapped_column(Boolean, default=False)


class ModelRun(Base):
    __tablename__ = "model_runs"
    __table_args__ = (
        Index("ix_model_runs_ticker_horizon", "ticker", "horizon"),
        Index("ix_model_runs_asset_class", "asset_class"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False, server_default="commodity")
    trained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    oos_auc: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    oos_precision: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    oos_recall: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    brier_score: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    fold: Mapped[int | None] = mapped_column(Integer)


class BacktestResult(Base):
    __tablename__ = "backtest_results"
    __table_args__ = (
        Index("ix_backtest_ticker_horizon", "ticker", "horizon"),
        Index("ix_backtest_results_asset_class", "asset_class"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False, server_default="commodity")
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    avg_win_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    avg_loss_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    num_trades: Mapped[int | None] = mapped_column(Integer)


class ModelHyperparam(Base):
    __tablename__ = "model_hyperparams"
    __table_args__ = (
        UniqueConstraint("ticker", "horizon", "model_type", name="uq_model_hyperparams"),
        Index("ix_hyperparams_ticker_horizon", "ticker", "horizon", "model_type"),
        Index("ix_model_hyperparams_asset_class", "asset_class"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False, server_default="commodity")
    model_type: Mapped[str] = mapped_column(String(32), nullable=False)
    params_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    tuned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OosPrediction(Base):
    __tablename__ = "oos_predictions"
    __table_args__ = (
        UniqueConstraint("ticker", "horizon", "date", "fold", name="uq_oos_pred"),
        Index("ix_oos_ticker_horizon_date", "ticker", "horizon", "date"),
        Index("ix_oos_predictions_asset_class", "asset_class"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    horizon: Mapped[str] = mapped_column(String(8), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False, server_default="commodity")
    date: Mapped[date] = mapped_column(Date, nullable=False)
    fold: Mapped[int] = mapped_column(Integer, nullable=False)
    y_true: Mapped[int] = mapped_column(Integer, nullable=False)
    y_prob: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)


class JobStatus(Base):
    __tablename__ = "job_status"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())


class StockPrice(Base):
    __tablename__ = "stock_prices"
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_stock_price_ticker_date"),
        Index("ix_stock_prices_ticker_date", "ticker", "date"),
        Index("ix_stock_prices_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    high: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    low: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    close: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    volume: Mapped[int | None] = mapped_column(BigInteger)
    adj_close: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))


class InstrumentMetadata(Base):
    __tablename__ = "instrument_metadata"
    __table_args__ = (
        UniqueConstraint("ticker", "asset_class", name="uq_instrument_ticker_class"),
        Index("ix_instrument_metadata_class_active", "asset_class", "is_active"),
        Index("ix_instrument_metadata_sector", "sector"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64))
    industry: Mapped[str | None] = mapped_column(String(128))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PortfolioRanking(Base):
    __tablename__ = "portfolio_rankings"
    __table_args__ = (
        UniqueConstraint("date", "ticker", "horizon", name="uq_ranking_date_ticker_horizon"),
        Index("ix_portfolio_rankings_date", "date"),
        Index("ix_portfolio_rankings_date_rank", "date", "rank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    sector: Mapped[str | None] = mapped_column(String(64))
    in_topk: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    horizon: Mapped[str] = mapped_column(String(8), nullable=False, server_default="5d")
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class PortfolioHolding(Base):
    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        UniqueConstraint("date", "ticker", name="uq_holding_date_ticker"),
        Index("ix_portfolio_holdings_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    last_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    sector: Mapped[str | None] = mapped_column(String(64))


class PortfolioEquity(Base):
    __tablename__ = "portfolio_equity"
    __table_args__ = (
        UniqueConstraint("date", name="uq_portfolio_equity_date"),
        Index("ix_portfolio_equity_date", "date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    equity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    benchmark_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(18, 8))


class CotReport(Base):
    """CFTC Commitment of Traders — disaggregated weekly positioning."""

    __tablename__ = "cot_reports"
    __table_args__ = (
        UniqueConstraint("ticker", "report_date", name="uq_cot_ticker_date"),
        Index("ix_cot_ticker_date", "ticker", "report_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    open_interest: Mapped[int | None] = mapped_column(BigInteger)
    comm_long: Mapped[int | None] = mapped_column(BigInteger)
    comm_short: Mapped[int | None] = mapped_column(BigInteger)
    spec_long: Mapped[int | None] = mapped_column(BigInteger)
    spec_short: Mapped[int | None] = mapped_column(BigInteger)
    comm_net: Mapped[int | None] = mapped_column(BigInteger)
    spec_net: Mapped[int | None] = mapped_column(BigInteger)
    spec_pct_long: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))


class EiaInventory(Base):
    """EIA weekly petroleum and natural gas storage."""

    __tablename__ = "eia_inventories"
    __table_args__ = (
        UniqueConstraint("series_id", "report_date", name="uq_eia_series_date"),
        Index("ix_eia_series_date", "series_id", "report_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    series_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    units: Mapped[str | None] = mapped_column(String(32))
    wow_change: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))


class EarningsEvent(Base):
    """Upcoming and historical earnings release dates."""

    __tablename__ = "earnings_events"
    __table_args__ = (
        UniqueConstraint("ticker", "earnings_date", name="uq_earnings_ticker_date"),
        Index("ix_earnings_ticker_date", "ticker", "earnings_date"),
        Index("ix_earnings_date", "earnings_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    earnings_date: Mapped[date] = mapped_column(Date, nullable=False)
    timing: Mapped[str | None] = mapped_column(String(8))   # BMO / AMC
    eps_estimate: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    eps_actual: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    revenue_estimate: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    revenue_actual: Mapped[Decimal | None] = mapped_column(Numeric(24, 4))
    surprise_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EconomicEvent(Base):
    """Key macro release calendar — FOMC, CPI, NFP, PCE."""

    __tablename__ = "economic_events"
    __table_args__ = (
        UniqueConstraint("event_type", "event_date", name="uq_econ_type_date"),
        Index("ix_econ_date", "event_date"),
        Index("ix_econ_type", "event_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)   # FOMC | CPI | NFP | PCE | GDP
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str | None] = mapped_column(String(256))
    actual_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    forecast_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    prior_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    impact: Mapped[str | None] = mapped_column(String(16))   # high | medium | low


class MarketAlert(Base):
    """Price threshold and event-driven alerts."""

    __tablename__ = "market_alerts"
    __table_args__ = (
        Index("ix_alerts_ticker_triggered", "ticker", "triggered_at"),
        Index("ix_alerts_acknowledged", "acknowledged"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    alert_type: Mapped[str] = mapped_column(String(32), nullable=False)   # price_spike | inventory_draw | cot_extreme | earnings
    severity: Mapped[str] = mapped_column(String(16), nullable=False, server_default="medium")  # high | medium | low
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    message: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    change_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    acknowledged: Mapped[bool] = mapped_column(Boolean, server_default="false")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentMemory(Base):
    """Persistent agent analysis memory for cross-run context retrieval."""

    __tablename__ = "agent_memory"
    __table_args__ = (
        Index("ix_agent_memory_run_id", "run_id"),
        Index("ix_agent_memory_agent_name", "agent_name"),
        Index("ix_agent_memory_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    tickers_covered: Mapped[list | None] = mapped_column(JSONB)
    summary: Mapped[str | None] = mapped_column(Text)
    key_findings: Mapped[dict | None] = mapped_column(JSONB)
    top_picks: Mapped[list | None] = mapped_column(JSONB)
    risks: Mapped[list | None] = mapped_column(JSONB)
    full_text: Mapped[str | None] = mapped_column(Text)
    embedding_json: Mapped[list | None] = mapped_column(JSONB)


class AgentRecommendation(Base):
    __tablename__ = "agent_recommendations"
    __table_args__ = (
        Index("ix_agent_rec_run_id", "run_id"),
        Index("ix_agent_rec_ticker", "ticker"),
        Index("ix_agent_rec_entry_date", "entry_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_class: Mapped[str | None] = mapped_column(String(16))
    sector: Mapped[str | None] = mapped_column(String(64))
    horizon: Mapped[str | None] = mapped_column(String(16))          # short | medium
    final_recommendation: Mapped[str] = mapped_column(String(16), nullable=False)
    conviction: Mapped[str | None] = mapped_column(String(16))
    position_size_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    thesis: Mapped[str | None] = mapped_column(Text)
    catalyst: Mapped[str | None] = mapped_column(Text)
    catalyst_date: Mapped[date | None] = mapped_column(Date)
    what_breaks_thesis: Mapped[str | None] = mapped_column(Text)
    entry_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    spx_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    check_2w_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    check_2w_spx: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    check_2w_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_4w_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    check_4w_spx: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    check_4w_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    check_8w_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    check_8w_spx: Mapped[Decimal | None] = mapped_column(Numeric(24, 8))
    check_8w_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ---------------------------------------------------------------------------
# Paper trading
# ---------------------------------------------------------------------------

class PaperPortfolio(Base):
    """Single-row table representing the paper trading account."""

    __tablename__ = "paper_portfolio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False, default=100000)
    current_cash: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    spx_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PaperPosition(Base):
    """An open or closed simulated position."""

    __tablename__ = "paper_positions"
    __table_args__ = (
        Index("ix_paper_pos_ticker", "ticker"),
        Index("ix_paper_pos_is_open", "is_open"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    name: Mapped[str | None] = mapped_column(String(128))
    sector: Mapped[str | None] = mapped_column(String(64))
    asset_class: Mapped[str | None] = mapped_column(String(16))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    entry_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    position_size_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    stop_loss_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    recommendation: Mapped[str] = mapped_column(String(16), nullable=False)  # STRONG_BUY | BUY
    conviction: Mapped[str | None] = mapped_column(String(16))
    thesis: Mapped[str | None] = mapped_column(Text)
    what_breaks_thesis: Mapped[str | None] = mapped_column(Text)
    source_run_id: Mapped[str | None] = mapped_column(String(64))
    is_open: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 4))
    close_reason: Mapped[str | None] = mapped_column(String(64))
    realized_pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))


class PaperTrade(Base):
    """Immutable record of every simulated buy/sell execution."""

    __tablename__ = "paper_trades"
    __table_args__ = (Index("ix_paper_trade_ticker", "ticker"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # BUY | SELL
    price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    pnl_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    traded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
