"""Añade snapshots y resultados técnicos auditables.

Revision ID: 0003_technical_audit_results
Revises: 0002_import_metadata
"""

from alembic import op


revision = "0003_technical_audit_results"
down_revision = "0002_import_metadata"
branch_labels = None
depends_on = None


# Crea resultados versionados vinculados a una ejecución, nunca estados permanentes del mercado.
def upgrade() -> None:
    op.execute(
        "CREATE TABLE analysis.source_snapshots ("
        "source_snapshot_id UUID PRIMARY KEY, symbol_id UUID NOT NULL REFERENCES market.symbols(symbol_id), "
        "data_cutoff_utc TIMESTAMPTZ NOT NULL, source_reference TEXT NOT NULL, "
        "bar_counts JSONB NOT NULL, content_hash CHAR(64) NOT NULL, created_at_utc TIMESTAMPTZ NOT NULL, "
        "UNIQUE (symbol_id, data_cutoff_utc, content_hash))"
    )
    op.execute(
        "ALTER TABLE analysis.technical_analysis_runs "
        "ADD CONSTRAINT technical_run_snapshot_fk "
        "FOREIGN KEY (source_snapshot_id) REFERENCES analysis.source_snapshots(source_snapshot_id)"
    )
    op.execute(
        "CREATE TABLE technical.market_structures ("
        "market_structure_id UUID PRIMARY KEY, analysis_run_id UUID NOT NULL "
        "REFERENCES analysis.technical_analysis_runs(analysis_run_id), timeframe TEXT NOT NULL, "
        "direction TEXT NOT NULL, bar_count INTEGER NOT NULL, window_high NUMERIC NOT NULL, "
        "window_low NUMERIC NOT NULL, summary JSONB NOT NULL)"
    )
    op.execute(
        "CREATE TABLE technical.structural_breaks ("
        "structural_break_id UUID PRIMARY KEY, analysis_run_id UUID NOT NULL "
        "REFERENCES analysis.technical_analysis_runs(analysis_run_id), timeframe TEXT NOT NULL, "
        "event_type TEXT NOT NULL, direction TEXT NOT NULL, pivot_price NUMERIC, "
        "confirmed_at_utc TIMESTAMPTZ, details JSONB NOT NULL)"
    )
    op.execute(
        "CREATE TABLE technical.points_of_interest ("
        "point_of_interest_id UUID PRIMARY KEY, analysis_run_id UUID NOT NULL "
        "REFERENCES analysis.technical_analysis_runs(analysis_run_id), timeframe TEXT NOT NULL, "
        "direction TEXT, low NUMERIC NOT NULL, high NUMERIC NOT NULL, state TEXT NOT NULL, details JSONB NOT NULL)"
    )
    op.execute(
        "CREATE TABLE technical.technical_levels ("
        "technical_level_id UUID PRIMARY KEY, analysis_run_id UUID NOT NULL "
        "REFERENCES analysis.technical_analysis_runs(analysis_run_id), period TEXT NOT NULL, "
        "high NUMERIC NOT NULL, low NUMERIC NOT NULL)"
    )
    op.execute(
        "CREATE TABLE technical.structural_targets ("
        "structural_target_id UUID PRIMARY KEY, analysis_run_id UUID NOT NULL "
        "REFERENCES analysis.technical_analysis_runs(analysis_run_id), direction TEXT NOT NULL, "
        "ordinal SMALLINT NOT NULL, price NUMERIC NOT NULL)"
    )
    op.execute(
        "CREATE TABLE analysis.technical_explanations ("
        "technical_explanation_id UUID PRIMARY KEY, analysis_run_id UUID NOT NULL "
        "REFERENCES analysis.technical_analysis_runs(analysis_run_id), explanation_order SMALLINT NOT NULL, "
        "content TEXT NOT NULL)"
    )


# Revierte las interpretaciones antes de snapshots para conservar coherencia referencial.
def downgrade() -> None:
    op.execute("DROP TABLE analysis.technical_explanations")
    op.execute("DROP TABLE technical.structural_targets")
    op.execute("DROP TABLE technical.technical_levels")
    op.execute("DROP TABLE technical.points_of_interest")
    op.execute("DROP TABLE technical.structural_breaks")
    op.execute("DROP TABLE technical.market_structures")
    op.execute("ALTER TABLE analysis.technical_analysis_runs DROP CONSTRAINT technical_run_snapshot_fk")
    op.execute("DROP TABLE analysis.source_snapshots")
