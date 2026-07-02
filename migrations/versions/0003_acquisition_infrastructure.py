"""acquisition infrastructure

Revision ID: 0003_acquisition_infrastructure
Revises: 0002_experiments_schema
Create Date: 2026-07-01 00:00:00.000000
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import op
from sqlmodel import SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.db.models  # noqa: F401

revision = "0003_acquisition_infrastructure"
down_revision = "0002_experiments_schema"
branch_labels = None
depends_on = None


NEW_TABLES = [
    "stock_splits",
    "provider_api_calls",
    "raw_provider_payloads",
    "acquisition_jobs",
    "acquisition_tasks",
]


def upgrade() -> None:
    for table_name in NEW_TABLES:
        table = SQLModel.metadata.tables[table_name]
        op.create_table(
            table_name,
            *[column.copy() for column in table.columns],
        )


def downgrade() -> None:
    for table_name in reversed(NEW_TABLES):
        op.drop_table(table_name)
