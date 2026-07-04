"""campaign runs

Revision ID: 0007_campaign_runs
Revises: 0006_security_master
Create Date: 2026-07-03 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0007_campaign_runs"
down_revision = "0006_security_master"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campaign_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("campaign_name", sa.String(), nullable=False),
        sa.Column("config_path", sa.String(), nullable=True),
        sa.Column("config_hash", sa.String(), nullable=False),
        sa.Column("provider", sa.String(), nullable=False),
        sa.Column("universe_name", sa.String(), nullable=True),
        sa.Column("market", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'PLANNED'")),
        sa.Column("live", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("current_phase", sa.Integer(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("audit_json", sa.JSON(), nullable=False),
        sa.Column("warning_json", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_campaign_runs_campaign_name", "campaign_runs", ["campaign_name"])
    op.create_index("ix_campaign_runs_config_hash", "campaign_runs", ["config_hash"])
    op.create_index("ix_campaign_runs_status", "campaign_runs", ["status"])

    op.create_table(
        "campaign_phase_runs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("phase_number", sa.Integer(), nullable=False),
        sa.Column("phase_name", sa.String(), nullable=False),
        sa.Column("phase_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'PLANNED'")),
        sa.Column("mode", sa.String(), nullable=False, server_default=sa.text("'diagnostic'")),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("estimate_json", sa.JSON(), nullable=False),
        sa.Column("audit_json", sa.JSON(), nullable=False),
        sa.Column("blocker", sa.String(), nullable=True),
        sa.Column("acquisition_job_id", sa.Integer(), nullable=True),
        sa.Column("rows_imported", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_downloaded", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_ingested", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_normalized", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("files_failed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["campaign_runs.id"]),
        sa.UniqueConstraint("campaign_id", "phase_number", name="uq_campaign_phase_runs_campaign_phase"),
    )
    op.create_index("ix_campaign_phase_runs_campaign_id", "campaign_phase_runs", ["campaign_id"])
    op.create_index("ix_campaign_phase_runs_phase_number", "campaign_phase_runs", ["phase_number"])
    op.create_index("ix_campaign_phase_runs_status", "campaign_phase_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_campaign_phase_runs_status", table_name="campaign_phase_runs")
    op.drop_index("ix_campaign_phase_runs_phase_number", table_name="campaign_phase_runs")
    op.drop_index("ix_campaign_phase_runs_campaign_id", table_name="campaign_phase_runs")
    op.drop_table("campaign_phase_runs")
    op.drop_index("ix_campaign_runs_status", table_name="campaign_runs")
    op.drop_index("ix_campaign_runs_config_hash", table_name="campaign_runs")
    op.drop_index("ix_campaign_runs_campaign_name", table_name="campaign_runs")
    op.drop_table("campaign_runs")
