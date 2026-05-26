"""Add COT, EIA, earnings, economic calendar, market alerts, and agent memory tables.

Revision ID: 004_phase2_5
Revises: 003_recommendations
Create Date: 2026-05-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "004_phase2_5"
down_revision = "003_recommendations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cot_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("open_interest", sa.BigInteger()),
        sa.Column("comm_long", sa.BigInteger()),
        sa.Column("comm_short", sa.BigInteger()),
        sa.Column("spec_long", sa.BigInteger()),
        sa.Column("spec_short", sa.BigInteger()),
        sa.Column("comm_net", sa.BigInteger()),
        sa.Column("spec_net", sa.BigInteger()),
        sa.Column("spec_pct_long", sa.Numeric(8, 4)),
        sa.UniqueConstraint("ticker", "report_date", name="uq_cot_ticker_date"),
    )
    op.create_index("ix_cot_ticker_date", "cot_reports", ["ticker", "report_date"])

    op.create_table(
        "eia_inventories",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("series_id", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Numeric(18, 4)),
        sa.Column("units", sa.String(32)),
        sa.Column("wow_change", sa.Numeric(18, 4)),
        sa.UniqueConstraint("series_id", "report_date", name="uq_eia_series_date"),
    )
    op.create_index("ix_eia_series_date", "eia_inventories", ["series_id", "report_date"])

    op.create_table(
        "earnings_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("earnings_date", sa.Date(), nullable=False),
        sa.Column("timing", sa.String(8)),
        sa.Column("eps_estimate", sa.Numeric(10, 4)),
        sa.Column("eps_actual", sa.Numeric(10, 4)),
        sa.Column("revenue_estimate", sa.Numeric(24, 4)),
        sa.Column("revenue_actual", sa.Numeric(24, 4)),
        sa.Column("surprise_pct", sa.Numeric(8, 4)),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("ticker", "earnings_date", name="uq_earnings_ticker_date"),
    )
    op.create_index("ix_earnings_ticker_date", "earnings_events", ["ticker", "earnings_date"])
    op.create_index("ix_earnings_date", "earnings_events", ["earnings_date"])

    op.create_table(
        "economic_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("description", sa.String(256)),
        sa.Column("actual_value", sa.Numeric(12, 4)),
        sa.Column("forecast_value", sa.Numeric(12, 4)),
        sa.Column("prior_value", sa.Numeric(12, 4)),
        sa.Column("impact", sa.String(16)),
        sa.UniqueConstraint("event_type", "event_date", name="uq_econ_type_date"),
    )
    op.create_index("ix_econ_date", "economic_events", ["event_date"])
    op.create_index("ix_econ_type", "economic_events", ["event_type"])

    op.create_table(
        "market_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("alert_type", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("price", sa.Numeric(24, 8)),
        sa.Column("change_pct", sa.Numeric(8, 4)),
        sa.Column("acknowledged", sa.Boolean(), server_default="false"),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_alerts_ticker_triggered", "market_alerts", ["ticker", "triggered_at"])
    op.create_index("ix_alerts_acknowledged", "market_alerts", ["acknowledged"])

    op.create_table(
        "agent_memory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("agent_name", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("tickers_covered", JSONB),
        sa.Column("summary", sa.Text()),
        sa.Column("key_findings", JSONB),
        sa.Column("top_picks", JSONB),
        sa.Column("risks", JSONB),
        sa.Column("full_text", sa.Text()),
    )
    op.create_index("ix_agent_memory_run_id", "agent_memory", ["run_id"])
    op.create_index("ix_agent_memory_agent_name", "agent_memory", ["agent_name"])
    op.create_index("ix_agent_memory_created_at", "agent_memory", ["created_at"])


def downgrade() -> None:
    op.drop_table("agent_memory")
    op.drop_table("market_alerts")
    op.drop_table("economic_events")
    op.drop_table("earnings_events")
    op.drop_table("eia_inventories")
    op.drop_table("cot_reports")
