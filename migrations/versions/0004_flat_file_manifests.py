"""flat file manifests

Revision ID: 0004_flat_file_manifests
Revises: 0003_acquisition_infrastructure
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import op
from sqlmodel import SQLModel

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import app.db.models  # noqa: F401

revision = "0004_flat_file_manifests"
down_revision = "0003_acquisition_infrastructure"
branch_labels = None
depends_on = None


def upgrade() -> None:
    table = SQLModel.metadata.tables["flat_file_manifests"]
    op.create_table(
        table.name,
        *[column.copy() for column in table.columns],
    )


def downgrade() -> None:
    op.drop_table("flat_file_manifests")
