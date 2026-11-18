"""Añade consolidaciones auditables.

Revision ID: 0005_auditable_consolidations
Revises: 0004_exact_source_snapshots
"""

from alembic import op


revision = "0005_auditable_consolidations"
down_revision = "0004_exact_source_snapshots"
branch_labels = None
depends_on = None


# Conserva rango, duración, ruptura y evidencia de cada consolidación detectada.
def upgrade() -> None:
    op.execute(
        "CREATE TABLE technical.consolidations ("
        "consolidation_id UUID PRIMARY KEY, analysis_run_id UUID NOT NULL "
        "REFERENCES analysis.technical_analysis_runs(analysis_run_id), timeframe TEXT NOT NULL, "
        "starts_at_utc TIMESTAMPTZ NOT NULL, ends_at_utc TIMESTAMPTZ NOT NULL, "
        "low NUMERIC NOT NULL, high NUMERIC NOT NULL, breakout_direction TEXT NOT NULL, "
        "breakout_at_utc TIMESTAMPTZ NOT NULL, state TEXT NOT NULL, evidence JSONB NOT NULL, "
        "CHECK (high >= low), CHECK (ends_at_utc >= starts_at_utc))"
    )


# Elimina únicamente la tabla derivada; los análisis y snapshots permanecen intactos.
def downgrade() -> None:
    op.execute("DROP TABLE technical.consolidations")
