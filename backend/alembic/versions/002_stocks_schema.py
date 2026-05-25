"""Add stock universe support: asset_class column, stock_prices, instrument_metadata,
portfolio_rankings, portfolio_holdings.

Revision ID: 002_stocks
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "002_stocks"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ASSET_CLASS_TABLES = (
    "signals",
    "model_runs",
    "backtest_results",
    "model_hyperparams",
    "oos_predictions",
)


def upgrade() -> None:
    for tbl in _ASSET_CLASS_TABLES:
        op.add_column(
            tbl,
            sa.Column(
                "asset_class",
                sa.String(length=16),
                nullable=False,
                server_default=sa.text("'commodity'"),
            ),
        )
        op.create_index(f"ix_{tbl}_asset_class", tbl, ["asset_class"])

    op.create_table(
        "stock_prices",
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
        sa.UniqueConstraint("ticker", "date", name="uq_stock_price_ticker_date"),
    )
    op.create_index("ix_stock_prices_ticker_date", "stock_prices", ["ticker", "date"])
    op.create_index("ix_stock_prices_date", "stock_prices", ["date"])

    op.create_table(
        "instrument_metadata",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("asset_class", sa.String(length=16), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("industry", sa.String(length=128), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "asset_class", name="uq_instrument_ticker_class"),
    )
    op.create_index(
        "ix_instrument_metadata_class_active",
        "instrument_metadata",
        ["asset_class", "is_active"],
    )
    op.create_index("ix_instrument_metadata_sector", "instrument_metadata", ["sector"])

    op.create_table(
        "portfolio_rankings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("score", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.Column("in_topk", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("horizon", sa.String(length=8), nullable=False, server_default=sa.text("'5d'")),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "ticker", "horizon", name="uq_ranking_date_ticker_horizon"),
    )
    op.create_index("ix_portfolio_rankings_date", "portfolio_rankings", ["date"])
    op.create_index(
        "ix_portfolio_rankings_date_rank",
        "portfolio_rankings",
        ["date", "rank"],
    )

    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("weight", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("last_price", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("sector", sa.String(length=64), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", "ticker", name="uq_holding_date_ticker"),
    )
    op.create_index("ix_portfolio_holdings_date", "portfolio_holdings", ["date"])

    op.create_table(
        "portfolio_equity",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("equity", sa.Numeric(precision=24, scale=8), nullable=False),
        sa.Column("benchmark_equity", sa.Numeric(precision=24, scale=8), nullable=True),
        sa.Column("daily_return", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("turnover", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uq_portfolio_equity_date"),
    )
    op.create_index("ix_portfolio_equity_date", "portfolio_equity", ["date"])


def downgrade() -> None:
    op.drop_index("ix_portfolio_equity_date", table_name="portfolio_equity")
    op.drop_table("portfolio_equity")

    op.drop_index("ix_portfolio_holdings_date", table_name="portfolio_holdings")
    op.drop_table("portfolio_holdings")

    op.drop_index("ix_portfolio_rankings_date_rank", table_name="portfolio_rankings")
    op.drop_index("ix_portfolio_rankings_date", table_name="portfolio_rankings")
    op.drop_table("portfolio_rankings")

    op.drop_index("ix_instrument_metadata_sector", table_name="instrument_metadata")
    op.drop_index("ix_instrument_metadata_class_active", table_name="instrument_metadata")
    op.drop_table("instrument_metadata")

    op.drop_index("ix_stock_prices_date", table_name="stock_prices")
    op.drop_index("ix_stock_prices_ticker_date", table_name="stock_prices")
    op.drop_table("stock_prices")

    for tbl in reversed(_ASSET_CLASS_TABLES):
        op.drop_index(f"ix_{tbl}_asset_class", table_name=tbl)
        op.drop_column(tbl, "asset_class")
