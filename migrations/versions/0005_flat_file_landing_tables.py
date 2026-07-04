"""flat file landing tables

Revision ID: 0005_flat_file_landing_tables
Revises: 0004_flat_file_manifests
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_flat_file_landing_tables"
down_revision = "0004_flat_file_manifests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "raw_polygon_stock_daily_bars",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_manifest_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=True),
        sa.Column("price_date", sa.Date(), nullable=True),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=True),
        sa.Column("adj_close", sa.Float(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default=sa.text("'sample'")),
        sa.Column("raw_row", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_manifest_id"], ["flat_file_manifests.id"]),
        sa.UniqueConstraint("source_manifest_id", "row_number", name="uq_raw_polygon_stock_daily_bars_manifest_row"),
    )
    op.create_table(
        "stock_daily_prices",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_manifest_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("price_date", sa.Date(), nullable=False),
        sa.Column("open", sa.Float(), nullable=True),
        sa.Column("high", sa.Float(), nullable=True),
        sa.Column("low", sa.Float(), nullable=True),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("adj_close", sa.Float(), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("source", sa.String(), nullable=False, server_default=sa.text("'sample'")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_manifest_id"], ["flat_file_manifests.id"]),
        sa.UniqueConstraint(
            "source_manifest_id",
            "ticker",
            "price_date",
            name="uq_stock_daily_prices_manifest_ticker_date",
        ),
    )
    op.create_table(
        "flat_file_quality_events",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("source_manifest_id", sa.Integer(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=True),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("issue_code", sa.String(), nullable=False),
        sa.Column("message", sa.String(), nullable=False),
        sa.Column("raw_row", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["source_manifest_id"], ["flat_file_manifests.id"]),
    )


def downgrade() -> None:
    op.drop_table("flat_file_quality_events")
    op.drop_table("stock_daily_prices")
    op.drop_table("raw_polygon_stock_daily_bars")
