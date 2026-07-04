"""security master support

Revision ID: 0006_security_master
Revises: 0005_flat_file_landing_tables
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_security_master"
down_revision = "0005_flat_file_landing_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "securities",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False, server_default=sa.text("'sample'")),
        sa.Column("asset_type", sa.String(), nullable=True),
        sa.Column("exchange", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("first_seen_date", sa.Date(), nullable=True),
        sa.Column("last_seen_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("provider", "symbol", name="uq_securities_provider_symbol"),
    )
    op.add_column("stock_daily_prices", sa.Column("security_id", sa.Integer(), nullable=True))

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO securities (
                symbol,
                provider,
                asset_type,
                exchange,
                name,
                active,
                first_seen_date,
                last_seen_date,
                created_at,
                updated_at
            )
            SELECT
                stock_daily_prices.ticker,
                'sample',
                'equity',
                NULL,
                NULL,
                1,
                MIN(stock_daily_prices.price_date),
                MAX(stock_daily_prices.price_date),
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM stock_daily_prices
            WHERE stock_daily_prices.ticker IS NOT NULL
            GROUP BY stock_daily_prices.ticker
            ON CONFLICT(provider, symbol) DO UPDATE SET
                first_seen_date = LEAST(excluded.first_seen_date, securities.first_seen_date),
                last_seen_date = GREATEST(excluded.last_seen_date, securities.last_seen_date),
                updated_at = CURRENT_TIMESTAMP
            """
        )
    )
    bind.execute(
        sa.text(
            """
            UPDATE stock_daily_prices
            SET security_id = (
                SELECT securities.id
                FROM securities
                WHERE securities.provider = 'sample'
                  AND securities.symbol = stock_daily_prices.ticker
            )
            WHERE stock_daily_prices.security_id IS NULL
            """
        )
    )
    op.create_foreign_key(
        "fk_stock_daily_prices_security_id_securities",
        "stock_daily_prices",
        "securities",
        ["security_id"],
        ["id"],
    )
    op.drop_constraint("uq_stock_daily_prices_manifest_ticker_date", "stock_daily_prices", type_="unique")
    op.create_unique_constraint(
        "uq_stock_daily_prices_manifest_security_date",
        "stock_daily_prices",
        ["source_manifest_id", "security_id", "price_date"],
    )
    op.create_index("ix_stock_daily_prices_security_id", "stock_daily_prices", ["security_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_daily_prices_security_id", table_name="stock_daily_prices")
    op.drop_constraint("uq_stock_daily_prices_manifest_security_date", "stock_daily_prices", type_="unique")
    op.create_unique_constraint(
        "uq_stock_daily_prices_manifest_ticker_date",
        "stock_daily_prices",
        ["source_manifest_id", "ticker", "price_date"],
    )
    op.drop_constraint("fk_stock_daily_prices_security_id_securities", "stock_daily_prices", type_="foreignkey")
    op.drop_column("stock_daily_prices", "security_id")
    op.drop_table("securities")
