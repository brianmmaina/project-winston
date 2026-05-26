"""Add agent_recommendations outcome tracking table.

Revision ID: 003_recommendations
Revises: 002_stocks
Create Date: 2026-05-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "003_recommendations"
down_revision = "002_stocks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_recommendations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("ticker", sa.String(16), nullable=False),
        sa.Column("asset_class", sa.String(16), nullable=True),
        sa.Column("sector", sa.String(64), nullable=True),
        sa.Column("horizon", sa.String(16), nullable=True),
        sa.Column("final_recommendation", sa.String(16), nullable=False),
        sa.Column("conviction", sa.String(16), nullable=True),
        sa.Column("position_size_pct", sa.Numeric(8, 2), nullable=True),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("catalyst", sa.Text(), nullable=True),
        sa.Column("catalyst_date", sa.Date(), nullable=True),
        sa.Column("what_breaks_thesis", sa.Text(), nullable=True),
        sa.Column("entry_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("spx_entry_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("entry_date", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("check_2w_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("check_2w_spx", sa.Numeric(24, 8), nullable=True),
        sa.Column("check_2w_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_4w_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("check_4w_spx", sa.Numeric(24, 8), nullable=True),
        sa.Column("check_4w_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_8w_price", sa.Numeric(24, 8), nullable=True),
        sa.Column("check_8w_spx", sa.Numeric(24, 8), nullable=True),
        sa.Column("check_8w_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_rec_run_id", "agent_recommendations", ["run_id"])
    op.create_index("ix_agent_rec_ticker", "agent_recommendations", ["ticker"])
    op.create_index("ix_agent_rec_entry_date", "agent_recommendations", ["entry_date"])


def downgrade() -> None:
    op.drop_index("ix_agent_rec_entry_date", table_name="agent_recommendations")
    op.drop_index("ix_agent_rec_ticker", table_name="agent_recommendations")
    op.drop_index("ix_agent_rec_run_id", table_name="agent_recommendations")
    op.drop_table("agent_recommendations")
