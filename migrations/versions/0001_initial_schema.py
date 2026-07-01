"""baseline schema for current development database

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-30 00:00:00.000000
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import op
from sqlmodel import SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.db.models  # noqa: F401

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in SQLModel.metadata.sorted_tables:
        op.create_table(
            table.name,
            *[column.copy() for column in table.columns],
        )


def downgrade() -> None:
    for table in reversed(SQLModel.metadata.sorted_tables):
        op.drop_table(table.name)
