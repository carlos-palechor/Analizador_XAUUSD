from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from xau_collector.domain.market import InstrumentIdentity, MarketDataSnapshot
from xau_collector.domain.models import M1Bar
from xau_collector.errors import ConfigurationError, DependencyUnavailableError
from xau_collector.ports.market_repository import MarketDataRepository


# Lee revisiones exactas de velas que una ejecución histórica dejó en su snapshot.
class PostgresSnapshotRepository(MarketDataRepository):
    # Conserva identidad y snapshot inmutables para reconstruir un análisis original.
    def __init__(
        self, database_url: str, source_snapshot_id: UUID, identity: InstrumentIdentity
    ) -> None:
        if not database_url.strip():
            raise ConfigurationError("Falta XAU_DATABASE_URL para recuperar un snapshot")
        self._database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._source_snapshot_id = source_snapshot_id
        self._identity = identity

    # Devuelve velas desde la copia inmutable, no desde las revisiones vigentes del mercado.
    def closed_bars(
        self,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[M1Bar, ...]:
        if identity != self._identity:
            raise ConfigurationError("La identidad solicitada no corresponde al snapshot")
        query = (
            "SELECT open_time_utc, open, high, low, close, tick_volume, real_volume, spread_points "
            "FROM analysis.snapshot_bars WHERE source_snapshot_id = %s AND timeframe = %s"
        )
        parameters: list[object] = [self._source_snapshot_id, timeframe]
        if cutoff_utc is not None:
            query += " AND close_time_utc <= %s"
            parameters.append(cutoff_utc)
        query += " ORDER BY open_time_utc"
        psycopg = _psycopg()
        with psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            rows = cursor.execute(query, tuple(parameters)).fetchall()
        bars = tuple(
            M1Bar(
                row[0].astimezone(UTC),
                float(row[1]),
                float(row[2]),
                float(row[3]),
                float(row[4]),
                int(row[5]),
                int(row[6]),
                int(row[7]),
            )
            for row in rows
        )
        return bars[-limit:] if limit is not None else bars

    # Describe la fuente inmutable para que un reproceso no confunda snapshot con mercado actual.
    def snapshot(
        self,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime,
        limit: int | None = None,
    ) -> MarketDataSnapshot:
        return MarketDataSnapshot(
            identity=identity,
            timeframe=timeframe,
            bars=self.closed_bars(identity, timeframe, cutoff_utc, limit),
            received_at_utc=datetime.now(UTC),
            data_cutoff_utc=cutoff_utc,
            source_reference=f"postgres-snapshot:{self._source_snapshot_id}",
        )


# Recupera identidad y corte para ofrecer reproducción original o reanálisis actualizado.
def load_analysis_snapshot(
    database_url: str, analysis_run_id: UUID
) -> tuple[PostgresSnapshotRepository, InstrumentIdentity, datetime]:
    connection_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    psycopg = _psycopg()
    query = (
        "SELECT run.source_snapshot_id, run.data_cutoff_utc, source.name, source.broker, "
        "source.server, symbol.broker_symbol FROM analysis.technical_analysis_runs run "
        "JOIN market.symbols symbol ON symbol.symbol_id = run.symbol_id "
        "JOIN market.data_sources source ON source.data_source_id = symbol.data_source_id "
        "WHERE run.analysis_run_id = %s"
    )
    with psycopg.connect(connection_url) as connection, connection.cursor() as cursor:
        row = cursor.execute(query, (analysis_run_id,)).fetchone()
    if row is None:
        raise ConfigurationError("No existe la ejecución técnica solicitada")
    identity = InstrumentIdentity(row[3], row[4], row[5], row[2])
    return PostgresSnapshotRepository(database_url, row[0], identity), identity, row[1]


# Recupera un snapshot recién capturado antes de crear una ejecución técnica.
def load_source_snapshot(
    database_url: str, source_snapshot_id: UUID
) -> tuple[PostgresSnapshotRepository, InstrumentIdentity, datetime]:
    connection_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    psycopg = _psycopg()
    query = (
        "SELECT snapshot.data_cutoff_utc, source.name, source.broker, source.server, "
        "symbol.broker_symbol FROM analysis.source_snapshots snapshot "
        "JOIN market.symbols symbol ON symbol.symbol_id = snapshot.symbol_id "
        "JOIN market.data_sources source ON source.data_source_id = symbol.data_source_id "
        "WHERE snapshot.source_snapshot_id = %s"
    )
    with psycopg.connect(connection_url) as connection, connection.cursor() as cursor:
        row = cursor.execute(query, (source_snapshot_id,)).fetchone()
    if row is None:
        raise ConfigurationError("No existe el snapshot técnico solicitado")
    identity = InstrumentIdentity(row[2], row[3], row[4], row[1])
    return PostgresSnapshotRepository(database_url, source_snapshot_id, identity), identity, row[0]


# Carga psycopg de forma diferida para permitir pruebas CSV sin PostgreSQL instalado.
def _psycopg() -> object:
    try:
        import psycopg
    except ImportError as exc:
        raise DependencyUnavailableError("Instale la dependencia opcional postgres") from exc
    return psycopg
