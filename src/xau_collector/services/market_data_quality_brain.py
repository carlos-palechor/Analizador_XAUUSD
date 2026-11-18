from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from xau_collector.config import AppSettings
from xau_collector.domain.models import M1Bar
from xau_collector.ports.market_data import MarketDataGateway
from xau_collector.services.m1_quality import M1QualityValidator, QualitySummary
from xau_collector.services.symbol_resolver import SymbolResolver


# Enumera los estados que puede entregar el Cerebro de Datos y Calidad.
class BrainStatus(StrEnum):
    VALID = "VALIDO"
    DEGRADED = "DEGRADADO"
    UNAVAILABLE = "NO_DISPONIBLE"


# Enumera si el símbolo puede aportar cotizaciones en el instante evaluado.
class MarketState(StrEnum):
    OPEN = "ABIERTO"
    OUT_OF_QUOTE_SESSION = "FUERA_DE_SESION_DE_COTIZACION"


# Define el mínimo que necesita el cerebro para interpretar sesiones de mercado.
class QuoteSessionCalendar(Protocol):
    # Indica si un instante UTC está fuera de una sesión de cotización confirmada.
    def is_expected_market_closed(self, instant_utc: datetime) -> bool: ...


# Reúne la respuesta verificable y sin decisiones de trading del primer cerebro.
@dataclass(frozen=True, slots=True)
class DataQualityBrainReport:
    engine_id: str
    engine_version: str
    status: BrainStatus
    market_state: MarketState
    symbol: str
    market_timestamp_utc: datetime
    calculated_at_utc: datetime
    source: str
    recent_bar_count: int
    quality: QualitySummary
    evidence: tuple[str, ...]
    missing_data: tuple[str, ...]
    blocking_reasons: tuple[str, ...]

    # Convierte la respuesta del cerebro en datos serializables para un reporte JSON.
    def to_dict(self) -> dict[str, Any]:
        return _serialize_datetimes(asdict(self))


# Coordina datos MT5, sesiones y validación para producir el estado único del Cerebro 1.
class MarketDataQualityBrain:
    # Conserva dependencias especializadas sin mezclar conexión, calendario y validación.
    def __init__(
        self,
        gateway: MarketDataGateway,
        resolver: SymbolResolver,
        calendar: QuoteSessionCalendar,
        validator: M1QualityValidator,
    ) -> None:
        self._gateway = gateway
        self._resolver = resolver
        self._calendar = calendar
        self._validator = validator

    # Evalúa una ventana reciente y devuelve estado, evidencia y bloqueos sin emitir señales.
    def run(self, settings: AppSettings, now_utc: datetime | None = None) -> DataQualityBrainReport:
        calculated_at = (now_utc or datetime.now(UTC)).astimezone(UTC)
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(),
                settings.symbol.logical_name,
                settings.symbol.aliases,
                settings.symbol.real_name,
            )
            self._gateway.select_symbol(symbol.name)
            tick = self._gateway.latest_tick(symbol.name)
            market_time = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
            market_state = (
                MarketState.OUT_OF_QUOTE_SESSION
                if self._calendar.is_expected_market_closed(market_time)
                else MarketState.OPEN
            )
            bars = tuple(
                self._gateway.bars_in_range(
                    symbol.name,
                    "M1",
                    market_time - timedelta(minutes=10),
                    market_time,
                )
            )
            quality = self._validator.validate(bars)
            return _report(
                symbol.name,
                market_time,
                calculated_at,
                self._gateway.broker_server(),
                bars,
                quality,
                market_state,
            )
        finally:
            self._gateway.close()


# Construye una respuesta consistente a partir de la calidad observada y el estado de sesión.
def _report(
    symbol: str,
    market_time: datetime,
    calculated_at: datetime,
    source: str,
    bars: tuple[M1Bar, ...],
    quality: QualitySummary,
    market_state: MarketState,
) -> DataQualityBrainReport:
    missing = _missing_data(bars, quality)
    blockers = _blocking_reasons(quality, market_state)
    status = BrainStatus.VALID if not missing and not blockers else BrainStatus.DEGRADED
    return DataQualityBrainReport(
        "datos_calidad",
        "1.0.0",
        status,
        market_state,
        symbol,
        market_time,
        calculated_at,
        source,
        len(bars),
        quality,
        ("MT5", "sesiones_exportadas_MT5"),
        missing,
        blockers,
    )


# Describe datos ausentes sin ocultar huecos detectados por la validación.
def _missing_data(bars: tuple[M1Bar, ...], quality: QualitySummary) -> tuple[str, ...]:
    missing: list[str] = []
    if not bars:
        missing.append("SIN_VELAS_RECIENTES")
    if quality.unexpected_gap_count:
        missing.append("HUECOS_NO_CONFIRMADOS")
    return tuple(missing)


# Explica por qué el cerebro recomienda bloquear análisis posterior.
def _blocking_reasons(quality: QualitySummary, market_state: MarketState) -> tuple[str, ...]:
    reasons: list[str] = []
    if market_state is MarketState.OUT_OF_QUOTE_SESSION:
        reasons.append("MERCADO_FUERA_DE_SESION_DE_COTIZACION")
    if quality.invalid_bar_count:
        reasons.append("VELAS_INVALIDAS")
    if quality.duplicate_count:
        reasons.append("VELAS_DUPLICADAS")
    if quality.out_of_order_count:
        reasons.append("VELAS_FUERA_DE_ORDEN")
    if quality.unexpected_gap_count:
        reasons.append("HUECOS_NO_CONFIRMADOS")
    return tuple(reasons)


# Convierte fechas anidadas en texto ISO-8601 para mantener el reporte auditable.
def _serialize_datetimes(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_datetimes(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_datetimes(item) for item in value]
    return value
