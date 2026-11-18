"""Registra las velas exactas usadas por cada snapshot.

Revision ID: 0004_exact_source_snapshots
Revises: 0003_technical_audit_results
"""

from alembic import op


revision = "0004_exact_source_snapshots"
down_revision = "0003_technical_audit_results"
branch_labels = None
depends_on = None


# Conserva el contenido exacto de cada vela usada, incluida su revisión vigente.
def upgrade() -> None:
    op.execute("ALTER TABLE analysis.source_snapshots ADD COLUMN fingerprint_version SMALLINT NOT NULL DEFAULT 2")
    op.execute(
        "CREATE TABLE analysis.snapshot_bars ("
        "source_snapshot_id UUID NOT NULL REFERENCES analysis.source_snapshots(source_snapshot_id), "
        "timeframe TEXT NOT NULL, ordinal INTEGER NOT NULL, market_bar_id UUID NOT NULL "
        "REFERENCES market.market_bars(market_bar_id), open_time_utc TIMESTAMPTZ NOT NULL, "
        "close_time_utc TIMESTAMPTZ NOT NULL, open NUMERIC NOT NULL, high NUMERIC NOT NULL, "
        "low NUMERIC NOT NULL, close NUMERIC NOT NULL, tick_volume BIGINT NOT NULL, "
        "real_volume BIGINT NOT NULL, spread_points INTEGER NOT NULL, revision INTEGER NOT NULL, "
        "PRIMARY KEY (source_snapshot_id, timeframe, ordinal))"
    )


# Revierte el detalle de velas sin borrar snapshots históricos existentes.
def downgrade() -> None:
    op.execute("DROP TABLE analysis.snapshot_bars")
    op.execute("ALTER TABLE analysis.source_snapshots DROP COLUMN fingerprint_version")
