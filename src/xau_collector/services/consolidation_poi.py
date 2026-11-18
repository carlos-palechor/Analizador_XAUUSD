from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from xau_collector.domain.models import M1Bar
from xau_collector.ports.market_data import MarketDataGateway
from xau_collector.services.symbol_resolver import SymbolResolver


# Representa una zona A-B negociada antes de una ruptura confirmada por cierre.
@dataclass(frozen=True, slots=True)
class ConsolidationPoi:
    low: float
    high: float
    first_open_utc: datetime
    last_open_utc: datetime
    breakout_direction: str
    breakout_open_utc: datetime


# Define los filtros ajustables de consolidación para una temporalidad concreta.
@dataclass(frozen=True, slots=True)
class ConsolidationRules:
    minimum_bars: int
    boundary_tolerance_ratio: float = 0.15
    minimum_boundary_touches: int = 2
    max_zone_to_average_range: float = 2.0


# Devuelve filtros iniciales por temporalidad para evitar tratar todas las escalas igual.
def rules_for_timeframe(timeframe: str) -> ConsolidationRules:
    rules = {
        "H4": ConsolidationRules(6, 0.10, 3, 1.5),
        "H1": ConsolidationRules(6, 0.12, 3, 1.5),
        "M15": ConsolidationRules(5, 0.15, 3, 1.6),
        "M5": ConsolidationRules(5, 0.16, 3, 1.6),
    }
    return rules[timeframe]


# Reúne POI de consolidación H1 sin producir recomendaciones de entrada.
@dataclass(frozen=True, slots=True)
class ConsolidationPoiReport:
    engine_id: str
    symbol: str
    calculated_at_utc: datetime
    h4_pois: tuple[ConsolidationPoi, ...]
    h1_pois: tuple[ConsolidationPoi, ...]
    m15_pois: tuple[ConsolidationPoi, ...]
    m5_pois: tuple[ConsolidationPoi, ...]

    # Convierte el reporte en datos compatibles con JSON.
    def to_dict(self) -> dict[str, Any]:
        return _serialize_datetimes(asdict(self))


# Detecta zonas H1 de negociación que terminaron con una ruptura de cuerpo.
class ConsolidationPoiBrain:
    # Conserva las dependencias de lectura sin escribir velas ni enviar órdenes.
    def __init__(self, gateway: MarketDataGateway, resolver: SymbolResolver) -> None:
        self._gateway = gateway
        self._resolver = resolver

    # Analiza las últimas velas H1 cerradas y devuelve consolidaciones con ruptura válida.
    def run(
        self, logical_name: str, aliases: tuple[str, ...], real_name: str | None
    ) -> ConsolidationPoiReport:
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(), logical_name, aliases, real_name
            )
            self._gateway.select_symbol(symbol.name)
            tick = self._gateway.latest_tick(symbol.name)
            now = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
            h4_bars = self._gateway.bars_in_range(symbol.name, "H4", now - timedelta(days=90), now)
            h1_bars = self._gateway.bars_in_range(symbol.name, "H1", now - timedelta(days=20), now)
            m15_bars = self._gateway.bars_in_range(symbol.name, "M15", now - timedelta(days=5), now)
            m5_bars = self._gateway.bars_in_range(symbol.name, "M5", now - timedelta(days=2), now)
            h4_closed = tuple(
                bar for bar in h4_bars if bar.open_time_utc + timedelta(hours=4) <= now
            )
            h1_closed = tuple(
                bar for bar in h1_bars if bar.open_time_utc + timedelta(hours=1) <= now
            )
            m15_closed = tuple(
                bar for bar in m15_bars if bar.open_time_utc + timedelta(minutes=15) <= now
            )
            m5_closed = tuple(
                bar for bar in m5_bars if bar.open_time_utc + timedelta(minutes=5) <= now
            )
            return ConsolidationPoiReport(
                "poi_consolidacion",
                symbol.name,
                datetime.now(UTC),
                tuple(_find_pois(h4_closed, rules_for_timeframe("H4"))),
                tuple(_find_pois(h1_closed, rules_for_timeframe("H1"))),
                tuple(_find_pois(m15_closed, rules_for_timeframe("M15"))),
                tuple(_find_pois(m5_closed, rules_for_timeframe("M5"))),
            )
        finally:
            self._gateway.close()


# Busca cuatro velas consecutivas y exige un cierre posterior fuera de su rango A-B.
def _find_pois(
    bars: Sequence[M1Bar], rules: ConsolidationRules | None = None
) -> list[ConsolidationPoi]:
    rules = rules or ConsolidationRules(4)
    candidates: list[ConsolidationPoi] = []
    for index in range(len(bars) - rules.minimum_bars):
        window = bars[index : index + rules.minimum_bars]
        high = max(bar.high for bar in window)
        low = min(bar.low for bar in window)
        average_range = sum(bar.high - bar.low for bar in window) / len(window)
        if high - low > average_range * rules.max_zone_to_average_range:
            continue
        tolerance = (high - low) * rules.boundary_tolerance_ratio
        touches_high = sum(bar.high >= high - tolerance for bar in window)
        touches_low = sum(bar.low <= low + tolerance for bar in window)
        if (
            touches_high < rules.minimum_boundary_touches
            or touches_low < rules.minimum_boundary_touches
        ):
            continue
        breakout = bars[index + rules.minimum_bars]
        if breakout.close > high:
            candidates.append(
                ConsolidationPoi(
                    low,
                    high,
                    window[0].open_time_utc,
                    window[-1].open_time_utc,
                    "ALCISTA",
                    breakout.open_time_utc,
                )
            )
        elif breakout.close < low:
            candidates.append(
                ConsolidationPoi(
                    low,
                    high,
                    window[0].open_time_utc,
                    window[-1].open_time_utc,
                    "BAJISTA",
                    breakout.open_time_utc,
                )
            )
    return _remove_overlaps(candidates)


# Conserva una sola zona cuando ventanas consecutivas describen la misma consolidación.
def _remove_overlaps(candidates: Sequence[ConsolidationPoi]) -> list[ConsolidationPoi]:
    selected: list[ConsolidationPoi] = []
    for candidate in candidates:
        overlaps = any(
            candidate.first_open_utc <= poi.last_open_utc
            and candidate.last_open_utc >= poi.first_open_utc
            for poi in selected
        )
        if not overlaps:
            selected.append(candidate)
    return selected


# Convierte fechas anidadas a texto ISO-8601.
def _serialize_datetimes(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_datetimes(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_datetimes(item) for item in value]
    return value
