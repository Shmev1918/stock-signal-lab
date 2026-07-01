"""experiments schema

Revision ID: 0002_experiments_schema
Revises: 0001_initial_schema
Create Date: 2026-07-01 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_experiments_schema"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("experiment_type", sa.String(), nullable=False),
        sa.Column("strategy_name", sa.String(), nullable=True),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("benchmark_ticker", sa.String(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("filters_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_experiments_name"), "experiments", ["name"], unique=False)
    op.create_index(op.f("ix_experiments_experiment_type"), "experiments", ["experiment_type"], unique=False)
    op.create_index(op.f("ix_experiments_strategy_name"), "experiments", ["strategy_name"], unique=False)
    op.create_index(op.f("ix_experiments_benchmark_ticker"), "experiments", ["benchmark_ticker"], unique=False)
    op.create_index(op.f("ix_experiments_start_date"), "experiments", ["start_date"], unique=False)
    op.create_index(op.f("ix_experiments_end_date"), "experiments", ["end_date"], unique=False)
    op.create_index(op.f("ix_experiments_created_at"), "experiments", ["created_at"], unique=False)

    op.create_table(
        "experiment_results",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("experiment_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("strategy_name", sa.String(), nullable=False),
        sa.Column("recommendation", sa.String(), nullable=False),
        sa.Column("risk_category", sa.String(), nullable=False),
        sa.Column("opportunity_score", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("valuation_score", sa.Float(), nullable=False),
        sa.Column("momentum_score", sa.Float(), nullable=False),
        sa.Column("future_price_date", sa.Date(), nullable=True),
        sa.Column("future_return", sa.Float(), nullable=True),
        sa.Column("benchmark_return", sa.Float(), nullable=True),
        sa.Column("excess_return", sa.Float(), nullable=True),
        sa.Column("outcome_label", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("skip_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["experiment_id"], ["experiments.id"]),
    )
    op.create_index(op.f("ix_experiment_results_experiment_id"), "experiment_results", ["experiment_id"], unique=False)
    op.create_index(op.f("ix_experiment_results_ticker"), "experiment_results", ["ticker"], unique=False)
    op.create_index(op.f("ix_experiment_results_as_of_date"), "experiment_results", ["as_of_date"], unique=False)
    op.create_index(op.f("ix_experiment_results_strategy_name"), "experiment_results", ["strategy_name"], unique=False)
    op.create_index(op.f("ix_experiment_results_recommendation"), "experiment_results", ["recommendation"], unique=False)
    op.create_index(op.f("ix_experiment_results_risk_category"), "experiment_results", ["risk_category"], unique=False)
    op.create_index(op.f("ix_experiment_results_outcome_label"), "experiment_results", ["outcome_label"], unique=False)
    op.create_index(op.f("ix_experiment_results_status"), "experiment_results", ["status"], unique=False)
    op.create_index(op.f("ix_experiment_results_future_price_date"), "experiment_results", ["future_price_date"], unique=False)
    op.create_index(op.f("ix_experiment_results_created_at"), "experiment_results", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_experiment_results_created_at"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_future_price_date"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_status"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_outcome_label"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_risk_category"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_recommendation"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_strategy_name"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_as_of_date"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_ticker"), table_name="experiment_results")
    op.drop_index(op.f("ix_experiment_results_experiment_id"), table_name="experiment_results")
    op.drop_table("experiment_results")

    op.drop_index(op.f("ix_experiments_created_at"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_end_date"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_start_date"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_benchmark_ticker"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_strategy_name"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_experiment_type"), table_name="experiments")
    op.drop_index(op.f("ix_experiments_name"), table_name="experiments")
    op.drop_table("experiments")
