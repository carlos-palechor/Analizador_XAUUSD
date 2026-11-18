from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


# Enumera los posibles resultados de una comprobación técnica del entorno.
class CheckStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
# Representa una comprobación individual y su resultado dentro de un diagnóstico.
class DiagnosticCheck:
    name: str
    status: CheckStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
# Reúne el estado general del diagnóstico previo a usar el recolector.
class DoctorReport:
    generated_at_utc: datetime
    collector_version: str
    checks: tuple[DiagnosticCheck, ...]

    @property
    # Indica si ninguna comprobación del diagnóstico terminó en fallo.
    def healthy(self) -> bool:
        return all(check.status is not CheckStatus.FAIL for check in self.checks)

    # Convierte el diagnóstico en datos serializables para JSON.
    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["generated_at_utc"] = self.generated_at_utc.isoformat()
        payload["healthy"] = self.healthy
        return payload


@dataclass(frozen=True, slots=True)
# Describe las propiedades técnicas de un símbolo proporcionadas por el bróker.
class SymbolDescriptor:
    name: str
    description: str
    path: str
    digits: int
    point: float
    currency_base: str
    currency_profit: str
    contract_size: float
    visible: bool


@dataclass(frozen=True, slots=True)
# Representa la última cotización disponible de un instrumento.
class MarketTick:
    time_msc: int
    bid: float
    ask: float
    last: float


@dataclass(frozen=True, slots=True)
# Representa una vela de un minuto con sus precios, volumen y spread.
class M1Bar:
    open_time_utc: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int
    real_volume: int
    spread_points: int


@dataclass(frozen=True, slots=True)
# Resume la cantidad y el intervalo de velas recientes devueltas por MT5.
class RatesCoverage:
    timeframe: str
    requested_count: int
    returned_count: int
    earliest_utc: datetime | None
    latest_utc: datetime | None


@dataclass(frozen=True, slots=True)
# Resume la cobertura efectiva de datos para un intervalo temporal solicitado.
class TimeRangeCoverage:
    source: str
    requested_from_utc: datetime
    requested_to_utc: datetime
    returned_count: int
    earliest_utc: datetime | None
    latest_utc: datetime | None
    out_of_range_count: int = 0


@dataclass(frozen=True, slots=True)
# Agrupa los resultados de varios sondeos sobre un mismo tipo de dato histórico.
class HistoryAvailability:
    source: str
    probes: tuple[TimeRangeCoverage, ...]

    @property
    # Devuelve la fecha más antigua observada entre los sondeos con datos.
    def oldest_observed_utc(self) -> datetime | None:
        timestamps = [probe.earliest_utc for probe in self.probes if probe.earliest_utc]
        return min(timestamps) if timestamps else None

    @property
    # Cuenta los sondeos que devolvieron al menos un registro dentro de su rango.
    def probes_with_data(self) -> int:
        return sum(probe.returned_count > 0 for probe in self.probes)


@dataclass(frozen=True, slots=True)
# Reúne los datos descubiertos para validar símbolo, terminal e historial disponible.
class DiscoveryReport:
    generated_at_utc: datetime
    terminal_version: str
    broker_server: str
    symbol: SymbolDescriptor
    latest_tick: MarketTick
    recent_rates: RatesCoverage
    m1_history: HistoryAvailability
    tick_history: HistoryAvailability | None

    # Convierte el descubrimiento en datos serializables para un reporte JSON.
    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return _serialize_datetimes(payload)


# Recorre estructuras anidadas y convierte fechas en texto ISO-8601.
def _serialize_datetimes(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_datetimes(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_datetimes(item) for item in value]
    return value
