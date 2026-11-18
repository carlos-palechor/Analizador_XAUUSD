"""Crea los esquemas mínimos de mercado y auditoría.

Revision ID: 0001_market_and_audit
Revises:
"""

from alembic import op


revision = "0001_market_and_audit"
down_revision = None
branch_labels = None
depends_on = None


# Crea entidades mínimas sin persistir todavía interpretaciones técnicas.
def upgrade() -> None:
    op.execute("CREATE SCHEMA market")
    op.execute("CREATE SCHEMA technical")
    op.execute("CREATE SCHEMA analysis")
    op.execute("CREATE SCHEMA system")
    op.execute("""
        CREATE TABLE market.data_sources (
            data_source_id UUID PRIMARY KEY,
            name TEXT NOT NULL,
            broker TEXT NOT NULL,
            server TEXT NOT NULL,
            created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (name, broker, server)
        )
    """)
    op.execute("""
        CREATE TABLE market.symbols (
            symbol_id UUID PRIMARY KEY,
            data_source_id UUID NOT NULL REFERENCES market.data_sources(data_source_id),
            broker_symbol TEXT NOT NULL,
            canonical_symbol TEXT NOT NULL,
            digits INTEGER NOT NULL,
            point NUMERIC NOT NULL,
            created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (data_source_id, broker_symbol)
        )
    """)
    op.execute("""
        CREATE TABLE system.import_batches (
            import_batch_id UUID PRIMARY KEY,
            source_filename TEXT NOT NULL,
            source_sha256 CHAR(64) NOT NULL,
            importer_version TEXT NOT NULL,
            imported_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(),
            original_rows INTEGER NOT NULL,
            accepted_rows INTEGER NOT NULL,
            duplicate_rows INTEGER NOT NULL,
            rejected_rows INTEGER NOT NULL,
            quality_status TEXT NOT NULL,
            UNIQUE (source_sha256, importer_version)
        )
    """)
    op.execute("""
        CREATE TABLE market.market_bars (
            market_bar_id UUID PRIMARY KEY,
            symbol_id UUID NOT NULL REFERENCES market.symbols(symbol_id),
            import_batch_id UUID REFERENCES system.import_batches(import_batch_id),
            timeframe TEXT NOT NULL,
            open_time_utc TIMESTAMPTZ NOT NULL,
            close_time_utc TIMESTAMPTZ NOT NULL,
            received_at_utc TIMESTAMPTZ NOT NULL,
            open NUMERIC NOT NULL, high NUMERIC NOT NULL, low NUMERIC NOT NULL, close NUMERIC NOT NULL,
            tick_volume BIGINT NOT NULL, real_volume BIGINT NOT NULL, spread_points INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,
            is_current BOOLEAN NOT NULL DEFAULT TRUE,
            correction_reason TEXT,
            CHECK (high >= low), CHECK (open BETWEEN low AND high), CHECK (close BETWEEN low AND high),
            UNIQUE (symbol_id, timeframe, open_time_utc, revision)
        )
    """)
    op.execute("CREATE UNIQUE INDEX market_current_bar_identity ON market.market_bars(symbol_id, timeframe, open_time_utc) WHERE is_current")
    op.execute("""
        CREATE TABLE market.trading_sessions (
            trading_session_id UUID PRIMARY KEY,
            symbol_id UUID NOT NULL REFERENCES market.symbols(symbol_id),
            weekday SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
            start_seconds_server INTEGER NOT NULL, end_seconds_server INTEGER NOT NULL,
            session_kind TEXT NOT NULL, source_reference TEXT NOT NULL,
            effective_from_utc TIMESTAMPTZ NOT NULL, effective_to_utc TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE TABLE market.market_closures (
            market_closure_id UUID PRIMARY KEY,
            symbol_id UUID NOT NULL REFERENCES market.symbols(symbol_id),
            starts_at_utc TIMESTAMPTZ NOT NULL, ends_at_utc TIMESTAMPTZ NOT NULL,
            closure_type TEXT NOT NULL, source_reference TEXT NOT NULL,
            CHECK (ends_at_utc > starts_at_utc)
        )
    """)
    op.execute("""
        CREATE TABLE system.algorithm_versions (
            algorithm_version_id UUID PRIMARY KEY,
            algorithm_name TEXT NOT NULL, version TEXT NOT NULL, source_revision TEXT NOT NULL,
            created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (algorithm_name, version)
        )
    """)
    op.execute("""
        CREATE TABLE system.analysis_parameters (
            parameters_hash CHAR(64) PRIMARY KEY, parameters_json JSONB NOT NULL,
            created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE analysis.technical_analysis_runs (
            analysis_run_id UUID PRIMARY KEY,
            symbol_id UUID NOT NULL REFERENCES market.symbols(symbol_id),
            data_cutoff_utc TIMESTAMPTZ NOT NULL, analyzed_at_utc TIMESTAMPTZ NOT NULL,
            algorithm_version_id UUID NOT NULL REFERENCES system.algorithm_versions(algorithm_version_id),
            parameters_hash CHAR(64) NOT NULL REFERENCES system.analysis_parameters(parameters_hash),
            source_snapshot_id UUID NOT NULL, state TEXT NOT NULL,
            UNIQUE (analysis_run_id, data_cutoff_utc)
        )
    """)
    op.execute("""
        CREATE TABLE analysis.analysis_evidence (
            analysis_evidence_id UUID PRIMARY KEY,
            analysis_run_id UUID NOT NULL REFERENCES analysis.technical_analysis_runs(analysis_run_id),
            evidence_kind TEXT NOT NULL, payload JSONB NOT NULL
        )
    """)


# Elimina los esquemas en orden inverso, exclusivamente para entornos de desarrollo.
def downgrade() -> None:
    op.execute("DROP SCHEMA system CASCADE")
    op.execute("DROP SCHEMA analysis CASCADE")
    op.execute("DROP SCHEMA technical CASCADE")
    op.execute("DROP SCHEMA market CASCADE")
