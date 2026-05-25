"""Revision ID: initial_schema

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "commodity_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("high", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("low", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("close", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("adj_close", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "date", name="uq_commodity_price_ticker_date"),
    )
    op.create_index("ix_commodity_prices_ticker_date", "commodity_prices", ["ticker", "date"])

    op.create_table(
        "macro_indicators",
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("fed_funds_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("usd_eur", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("usd_jpy", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("yield_spread_10y2y", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("breakeven_inflation", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("vix", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("cpi_yoy", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("wti_spot", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("gold_fix", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("unrate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.PrimaryKeyConstraint("date"),
    )

    op.create_table(
        "sentiment_scores",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("score_1d", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("score_3d", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("momentum", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "date", name="uq_sentiment_ticker_date"),
    )
    op.create_index("ix_sentiment_ticker_date", "sentiment_scores", ["ticker", "date"])

    op.create_table(
        "signals",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("signal", sa.String(length=16), nullable=False),
        sa.Column("avg_confidence", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("confidence_5d", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("confidence_10d", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("confidence_21d", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("regime", sa.Integer(), nullable=True),
        sa.Column("position_size_pct", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("shap_json", postgresql.JSONB(), nullable=True),
        sa.Column("sentiment_json", postgresql.JSONB(), nullable=True),
        sa.Column("correlation_filtered", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_generated_at", "signals", ["generated_at"])

    op.create_table(
        "model_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("horizon", sa.String(length=8), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("oos_auc", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("oos_precision", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("oos_recall", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("brier_score", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("fold", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_model_runs_ticker_horizon", "model_runs", ["ticker", "horizon"])

    op.create_table(
        "backtest_results",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("horizon", sa.String(length=8), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_return", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("win_rate", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("avg_win_pct", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("avg_loss_pct", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("num_trades", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtest_ticker_horizon", "backtest_results", ["ticker", "horizon"])

    op.create_table(
        "model_hyperparams",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("horizon", sa.String(length=8), nullable=False),
        sa.Column("model_type", sa.String(length=32), nullable=False),
        sa.Column("params_json", postgresql.JSONB(), nullable=False),
        sa.Column("tuned_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "horizon", "model_type", name="uq_model_hyperparams"),
    )
    op.create_index(
        "ix_hyperparams_ticker_horizon",
        "model_hyperparams",
        ["ticker", "horizon", "model_type"],
    )

    op.create_table(
        "oos_predictions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("horizon", sa.String(length=8), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("fold", sa.Integer(), nullable=False),
        sa.Column("y_true", sa.Integer(), nullable=False),
        sa.Column("y_prob", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "horizon", "date", "fold", name="uq_oos_pred"),
    )
    op.create_index(
        "ix_oos_ticker_horizon_date",
        "oos_predictions",
        ["ticker", "horizon", "date"],
    )

    op.create_table(
        "job_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id"),
    )


def downgrade() -> None:
    op.drop_table("job_status")
    op.drop_index("ix_oos_ticker_horizon_date", table_name="oos_predictions")
    op.drop_table("oos_predictions")
    op.drop_index("ix_hyperparams_ticker_horizon", table_name="model_hyperparams")
    op.drop_table("model_hyperparams")
    op.drop_index("ix_backtest_ticker_horizon", table_name="backtest_results")
    op.drop_table("backtest_results")
    op.drop_index("ix_model_runs_ticker_horizon", table_name="model_runs")
    op.drop_table("model_runs")
    op.drop_index("ix_signals_generated_at", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_sentiment_ticker_date", table_name="sentiment_scores")
    op.drop_table("sentiment_scores")
    op.drop_table("macro_indicators")
    op.drop_index("ix_commodity_prices_ticker_date", table_name="commodity_prices")
    op.drop_table("commodity_prices")
