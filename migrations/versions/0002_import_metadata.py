"""Añade trazabilidad completa para importaciones históricas.

Revision ID: 0002_import_metadata
Revises: 0001_market_and_audit
"""

from alembic import op


revision = "0002_import_metadata"
down_revision = "0001_market_and_audit"
branch_labels = None
depends_on = None


# Añade fuente, símbolo, período y reporte de calidad a cada importación reproducible.
def upgrade() -> None:
    op.execute(
        "ALTER TABLE system.import_batches "
        "ADD COLUMN data_source_id UUID REFERENCES market.data_sources(data_source_id), "
        "ADD COLUMN symbol_id UUID REFERENCES market.symbols(symbol_id), "
        "ADD COLUMN timeframe TEXT, "
        "ADD COLUMN period_start_utc TIMESTAMPTZ, "
        "ADD COLUMN period_end_utc TIMESTAMPTZ"
    )
    op.execute(
        "CREATE TABLE system.data_quality_reports ("
        "data_quality_report_id UUID PRIMARY KEY, "
        "import_batch_id UUID NOT NULL REFERENCES system.import_batches(import_batch_id), "
        "checked_at_utc TIMESTAMPTZ NOT NULL, status TEXT NOT NULL, details JSONB NOT NULL)"
    )


# Revierte solamente los metadatos agregados por esta migración.
def downgrade() -> None:
    op.execute("DROP TABLE system.data_quality_reports")
    op.execute(
        "ALTER TABLE system.import_batches "
        "DROP COLUMN period_end_utc, DROP COLUMN period_start_utc, DROP COLUMN timeframe, "
        "DROP COLUMN symbol_id, DROP COLUMN data_source_id"
    )
