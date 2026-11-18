from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.domain.models import M1Bar
from xau_collector.errors import ConfigurationError, DependencyUnavailableError
from xau_collector.infrastructure.csv_store import CsvBarStore
from xau_collector.services.historical_import_validation import HistoricalCsvValidator
from xau_collector.services.historical_technical_runner import timeframe_duration


# Resume una importación para guardar evidencia y mostrar resultados verificables.
@dataclass(frozen=True, slots=True)
class HistoricalImportReport:
    source: Path
    source_sha256: str
    timeframe: str
    original_rows: int
    accepted_rows: int
    inserted_rows: int
    duplicate_rows: int
    already_persisted_rows: int
    rejected_rows: int
    status: str
    import_batch_id: UUID

    # Convierte el reporte en una estructura sencilla para la consola y JSON.
    def to_dict(self) -> dict[str, object]:
        return {
            "source": str(self.source),
            "source_sha256": self.source_sha256,
            "timeframe": self.timeframe,
            "original_rows": self.original_rows,
            "accepted_rows": self.accepted_rows,
            "inserted_rows": self.inserted_rows,
            "duplicate_rows": self.duplicate_rows,
            "already_persisted_rows": self.already_persisted_rows,
            "rejected_rows": self.rejected_rows,
            "status": self.status,
            "import_batch_id": str(self.import_batch_id),
        }


# Importa CSV validados a PostgreSQL sin modificar ni borrar la fuente original.
class PostgresHistoricalImporter:
    _importer_version = "1.0.0"

    # Guarda la URL de conexión solo en memoria durante la ejecución actual.
    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ConfigurationError("Falta XAU_DATABASE_URL para importar históricos")
        self._database_url = database_url
        self._validator = HistoricalCsvValidator()

    # Importa un CSV y registra el lote incluso cuando contiene filas rechazadas.
    def import_csv(
        self,
        source: Path,
        identity: InstrumentIdentity,
        canonical_symbol: str,
        digits: int,
        point: float,
        timeframe: str,
    ) -> HistoricalImportReport:
        validation = self._validator.validate(source)
        source_hash = CsvBarStore.sha256(source)
        psycopg = _psycopg()
        imported_at = datetime.now(UTC)
        connection_url = _psycopg_connection_url(self._database_url)
        with psycopg.connect(connection_url) as connection, connection.cursor() as cursor:
            existing = cursor.execute(
                "SELECT import_batch_id FROM system.import_batches "
                "WHERE source_sha256 = %s AND importer_version = %s",
                (source_hash, self._importer_version),
            ).fetchone()
            if existing is not None:
                return HistoricalImportReport(
                    source,
                    source_hash,
                    timeframe,
                    validation.original_rows,
                    len(validation.accepted_bars),
                    0,
                    validation.duplicate_rows,
                    len(validation.accepted_bars),
                    validation.rejected_rows,
                    "ALREADY_IMPORTED",
                    existing[0],
                )
            source_id = _ensure_data_source(cursor, identity)
            symbol_id = _ensure_symbol(
                cursor, source_id, identity.symbol, canonical_symbol, digits, point
            )
            batch_id = uuid4()
            quality = "VALID" if validation.rejected_rows == 0 else "DEGRADED"
            cursor.execute(
                "INSERT INTO system.import_batches "
                "(import_batch_id, source_filename, source_sha256, importer_version, "
                "original_rows, accepted_rows, duplicate_rows, rejected_rows, quality_status, "
                "data_source_id, symbol_id, timeframe, period_start_utc, period_end_utc) "
                "VALUES (%s, %s, %s, %s, %s, 0, 0, %s, %s, %s, %s, %s, %s, %s)",
                (
                    batch_id,
                    str(source),
                    source_hash,
                    self._importer_version,
                    validation.original_rows,
                    validation.rejected_rows,
                    quality,
                    source_id,
                    symbol_id,
                    timeframe,
                    validation.period_start_utc,
                    validation.period_end_utc,
                ),
            )
            inserted = _insert_bars(
                cursor, symbol_id, batch_id, validation.accepted_bars, timeframe, imported_at
            )
            duplicates = validation.duplicate_rows + len(validation.accepted_bars) - inserted
            cursor.execute(
                "UPDATE system.import_batches SET accepted_rows = %s, duplicate_rows = %s "
                "WHERE import_batch_id = %s",
                (inserted, duplicates, batch_id),
            )
            cursor.execute(
                "INSERT INTO system.data_quality_reports "
                "(data_quality_report_id, import_batch_id, checked_at_utc, status, details) "
                "VALUES (%s, %s, %s, %s, jsonb_build_object("
                "'original_rows', %s, 'inserted_rows', %s, "
                "'duplicate_rows', %s, 'rejected_rows', %s))",
                (
                    uuid4(),
                    batch_id,
                    imported_at,
                    quality,
                    validation.original_rows,
                    inserted,
                    duplicates,
                    validation.rejected_rows,
                ),
            )
        return HistoricalImportReport(
            source,
            source_hash,
            timeframe,
            validation.original_rows,
            len(validation.accepted_bars),
            inserted,
            duplicates,
            0,
            validation.rejected_rows,
            quality,
            batch_id,
        )

    # Consulta conteos persistidos para comprobar una importación sin modificar datos.
    def verification_report(self) -> dict[str, object]:
        psycopg = _psycopg()
        connection_url = _psycopg_connection_url(self._database_url)
        with psycopg.connect(connection_url) as connection, connection.cursor() as cursor:
            bar_counts = cursor.execute(
                "SELECT timeframe, COUNT(*) FROM market.market_bars "
                "WHERE is_current GROUP BY timeframe ORDER BY timeframe"
            ).fetchall()
            batches = cursor.execute(
                "SELECT quality_status, COUNT(*) FROM system.import_batches "
                "GROUP BY quality_status ORDER BY quality_status"
            ).fetchall()
        return {
            "current_bar_counts": {timeframe: count for timeframe, count in bar_counts},
            "import_batches_by_quality": {status: count for status, count in batches},
        }


# Encuentra CSV históricos por carpeta de temporalidad sin incluir manifiestos ni reportes.
def discover_historical_csvs(root: Path) -> tuple[tuple[str, Path], ...]:
    sources: list[tuple[str, Path]] = []
    for timeframe in ("H4", "H1", "M15", "M5"):
        sources.extend(
            (timeframe, source) for source in sorted((root / timeframe.lower()).glob("*.csv"))
        )
    sources.extend(("M1", source) for source in sorted((root / "m1").rglob("*.csv")))
    if not sources:
        raise ConfigurationError(f"No se encontraron CSV históricos en: {root}")
    return tuple(sources)


# Carga psycopg solo cuando se necesita PostgreSQL para mantener pruebas locales simples.
def _psycopg() -> object:
    try:
        import psycopg
    except ImportError as exc:
        raise DependencyUnavailableError("Instale la dependencia opcional postgres") from exc
    return psycopg


# Adapta la URL SQLAlchemy usada por Alembic al formato de conexión directa de psycopg.
def _psycopg_connection_url(database_url: str) -> str:
    return database_url.replace("postgresql+psycopg://", "postgresql://", 1)


# Inserta o recupera la fuente de datos que identifica el bróker y servidor reales.
def _ensure_data_source(cursor: object, identity: InstrumentIdentity) -> UUID:
    row = cursor.execute(
        "SELECT data_source_id FROM market.data_sources "
        "WHERE name = %s AND broker = %s AND server = %s",
        (identity.source_name, identity.broker, identity.server),
    ).fetchone()
    if row is not None:
        return row[0]
    identifier = uuid4()
    cursor.execute(
        "INSERT INTO market.data_sources (data_source_id, name, broker, server) "
        "VALUES (%s, %s, %s, %s)",
        (identifier, identity.source_name, identity.broker, identity.server),
    )
    return identifier


# Inserta o recupera el símbolo exacto del bróker para impedir mezclar proveedores.
def _ensure_symbol(
    cursor: object,
    source_id: UUID,
    broker_symbol: str,
    canonical_symbol: str,
    digits: int,
    point: float,
) -> UUID:
    row = cursor.execute(
        "SELECT symbol_id FROM market.symbols WHERE data_source_id = %s AND broker_symbol = %s",
        (source_id, broker_symbol),
    ).fetchone()
    if row is not None:
        return row[0]
    identifier = uuid4()
    cursor.execute(
        "INSERT INTO market.symbols "
        "(symbol_id, data_source_id, broker_symbol, canonical_symbol, digits, point) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (identifier, source_id, broker_symbol, canonical_symbol, digits, point),
    )
    return identifier


# Inserta velas nuevas y conserva una revisión adicional si el proveedor corrigió su contenido.
def _insert_bars(
    cursor: object,
    symbol_id: UUID,
    batch_id: UUID,
    bars: tuple[object, ...],
    timeframe: str,
    received_at_utc: datetime,
) -> int:
    duration = timeframe_duration(timeframe)
    inserted = 0
    insert_statement = (
        "INSERT INTO market.market_bars "
        "(market_bar_id, symbol_id, import_batch_id, timeframe, open_time_utc, close_time_utc, "
        "received_at_utc, open, high, low, close, tick_volume, real_volume, spread_points, "
        "revision, correction_reason) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
    )
    for bar in bars:
        current = cursor.execute(
            "SELECT market_bar_id, revision, open, high, low, close, tick_volume, real_volume, "
            "spread_points FROM market.market_bars "
            "WHERE symbol_id = %s AND timeframe = %s AND open_time_utc = %s AND is_current",
            (symbol_id, timeframe, bar.open_time_utc),
        ).fetchone()
        if current is not None and _bar_matches_current(current, bar):
            continue
        revision = 1 if current is None else current[1] + 1
        if current is not None:
            cursor.execute(
                "UPDATE market.market_bars SET is_current = FALSE "
                "WHERE market_bar_id = %s",
                (current[0],),
            )
        cursor.execute(
            insert_statement,
            (
                uuid4(),
                symbol_id,
                batch_id,
                timeframe,
                bar.open_time_utc,
                bar.open_time_utc + duration,
                received_at_utc,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                bar.tick_volume,
                bar.real_volume,
                bar.spread_points,
                revision,
                None if current is None else "SOURCE_CONTENT_CHANGED",
            ),
        )
        inserted += 1
    return inserted


# Comprueba si una vela entrante es idéntica a la revisión actual antes de crear historia adicional.
def _bar_matches_current(current: tuple[object, ...], bar: M1Bar) -> bool:
    return (
        current[2] == Decimal(str(bar.open))
        and current[3] == Decimal(str(bar.high))
        and current[4] == Decimal(str(bar.low))
        and current[5] == Decimal(str(bar.close))
        and current[6] == bar.tick_volume
        and current[7] == bar.real_volume
        and current[8] == bar.spread_points
    )
