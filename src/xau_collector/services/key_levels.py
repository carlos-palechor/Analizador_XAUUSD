from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from xau_collector.domain.models import M1Bar
from xau_collector.ports.market_data import MarketDataGateway
from xau_collector.services.symbol_resolver import SymbolResolver


# Representa el máximo y mínimo de un periodo entregado por el calendario del bróker.
@dataclass(frozen=True, slots=True)
class PeriodRange:
    timeframe: str
    open_time_utc: datetime
    high: float
    low: float


# Reúne niveles diarios, semanales, mensuales y anuales sin sugerir operaciones.
@dataclass(frozen=True, slots=True)
class KeyLevelsReport:
    engine_id: str
    engine_version: str
    symbol: str
    calculated_at_utc: datetime
    market_timestamp_utc: datetime
    day: PeriodRange
    week: PeriodRange
    month: PeriodRange
    year: PeriodRange

    # Convierte los niveles en datos compatibles con un reporte JSON.
    def to_dict(self) -> dict[str, Any]:
        return _serialize_datetimes(asdict(self))


# Lee los niveles mayores directamente de las velas agrupadas por MT5.
class KeyLevelsBrain:
    # Conserva las dependencias necesarias para consultar niveles sin guardar historial.
    def __init__(self, gateway: MarketDataGateway, resolver: SymbolResolver) -> None:
        self._gateway = gateway
        self._resolver = resolver

    # Devuelve los rangos actuales de día, semana, mes y año según el bróker.
    def run(
        self, logical_name: str, aliases: tuple[str, ...], real_name: str | None
    ) -> KeyLevelsReport:
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(), logical_name, aliases, real_name
            )
            self._gateway.select_symbol(symbol.name)
            tick = self._gateway.latest_tick(symbol.name)
            market_time = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
            day = _last_range(
                self._gateway.bars_in_range(
                    symbol.name, "D1", market_time - timedelta(days=7), market_time
                ),
                "D1",
            )
            week = _last_range(
                self._gateway.bars_in_range(
                    symbol.name, "W1", market_time - timedelta(days=70), market_time
                ),
                "W1",
            )
            month_bars = self._gateway.bars_in_range(
                symbol.name, "MN1", market_time - timedelta(days=800), market_time
            )
            month = _last_range(month_bars, "MN1")
            year = _year_range(month_bars, market_time.year)
            return KeyLevelsReport(
                "niveles_clave",
                "0.1.0",
                symbol.name,
                datetime.now(UTC),
                market_time,
                day,
                week,
                month,
                year,
            )
        finally:
            self._gateway.close()


# Obtiene la vela más reciente de una temporalidad y la expresa como rango.
def _last_range(bars: tuple[M1Bar, ...], timeframe: str) -> PeriodRange:
    latest = max(bars, key=lambda bar: bar.open_time_utc)
    return PeriodRange(timeframe, latest.open_time_utc, latest.high, latest.low)


# Agrega las velas mensuales del año actual para formar su máximo y mínimo anual.
def _year_range(bars: tuple[M1Bar, ...], year: int) -> PeriodRange:
    current_year = tuple(bar for bar in bars if bar.open_time_utc.year == year)
    if not current_year:
        raise ValueError("MT5 no devolvió velas mensuales para el año actual")
    return PeriodRange(
        "Y1",
        min(bar.open_time_utc for bar in current_year),
        max(bar.high for bar in current_year),
        min(bar.low for bar in current_year),
    )


# Convierte fechas anidadas a ISO-8601 para conservar reportes legibles.
def _serialize_datetimes(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_datetimes(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_datetimes(item) for item in value]
    return value
