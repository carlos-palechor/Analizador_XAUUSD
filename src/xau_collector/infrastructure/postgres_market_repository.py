from __future__ import annotations

from datetime import UTC, datetime

from xau_collector.domain.market import InstrumentIdentity, MarketDataSnapshot
from xau_collector.domain.models import M1Bar
from xau_collector.errors import ConfigurationError, DependencyUnavailableError
from xau_collector.ports.market_repository import MarketDataRepository


# Lee velas vigentes de PostgreSQL mediante el contrato común del cerebro técnico.
class PostgresMarketDataRepository(MarketDataRepository):
    # Conserva la conexión solo en memoria y requiere una URL explícita de entorno.
    def __init__(self, database_url: str) -> None:
        if not database_url.strip():
            raise ConfigurationError("Falta XAU_DATABASE_URL para leer PostgreSQL")
        self._database_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)

    # Devuelve velas cerradas y vigentes del símbolo y fuente exactos.
    def closed_bars(
        self,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[M1Bar, ...]:
        psycopg = _psycopg()
        query, parameters = _bars_query(identity, timeframe, cutoff_utc, limit)
        with psycopg.connect(self._database_url) as connection, connection.cursor() as cursor:
            rows = cursor.execute(query, parameters).fetchall()
        return tuple(
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

    # Describe el corte y la fuente persistida usados por un cálculo reproducible.
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
            source_reference=f"postgres:{identity.source_name}:{identity.server}:{identity.symbol}",
        )


# Construye la consulta con identidad completa y límite aplicado antes del orden final.
def _bars_query(
    identity: InstrumentIdentity,
    timeframe: str,
    cutoff_utc: datetime | None,
    limit: int | None,
) -> tuple[str, tuple[object, ...]]:
    filters = (
        "source.name = %s AND source.broker = %s AND source.server = %s "
        "AND symbol.broker_symbol = %s AND bar.timeframe = %s AND bar.is_current"
    )
    parameters: list[object] = [
        identity.source_name,
        identity.broker,
        identity.server,
        identity.symbol,
        timeframe,
    ]
    if cutoff_utc is not None:
        filters += " AND bar.close_time_utc <= %s"
        parameters.append(cutoff_utc)
    select = (
        "SELECT bar.open_time_utc, bar.open, bar.high, bar.low, bar.close, "
        "bar.tick_volume, bar.real_volume, bar.spread_points "
        "FROM market.market_bars bar "
        "JOIN market.symbols symbol ON symbol.symbol_id = bar.symbol_id "
        "JOIN market.data_sources source ON source.data_source_id = symbol.data_source_id "
        f"WHERE {filters}"
    )
    if limit is None:
        return select + " ORDER BY bar.open_time_utc", tuple(parameters)
    query = (
        "SELECT * FROM ("
        + select
        + " ORDER BY bar.open_time_utc DESC LIMIT %s) recent ORDER BY open_time_utc"
    )
    parameters.append(limit)
    return query, tuple(parameters)


# Carga psycopg solo al leer PostgreSQL para conservar el uso CSV sin dependencia obligatoria.
def _psycopg() -> object:
    try:
        import psycopg
    except ImportError as exc:
        raise DependencyUnavailableError("Instale la dependencia opcional postgres") from exc
    return psycopg
