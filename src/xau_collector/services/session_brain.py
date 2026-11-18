from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.domain.models import M1Bar
from xau_collector.ports.market_repository import MarketDataRepository
from xau_collector.services.historical_technical_runner import timeframe_duration


# Describe una sesión internacional usando la zona horaria oficial de su mercado.
@dataclass(frozen=True, slots=True)
class TradingSessionDefinition:
    name: str
    timezone_name: str
    starts_at_local: time
    ends_at_local: time


# Conserva el rango observado de una sesión terminada, sin convertirlo en señal operativa.
@dataclass(frozen=True, slots=True)
class SessionRange:
    session_name: str
    timezone_name: str
    started_at_utc: datetime
    ended_at_utc: datetime
    bar_count: int
    expected_bar_count: int
    high: float | None
    low: float | None
    open: float | None
    close: float | None
    tick_volume: int
    status: str

    # Expone el recorrido de precio solamente cuando hubo velas suficientes.
    @property
    def range_size(self) -> float | None:
        return self.high - self.low if self.high is not None and self.low is not None else None


# Agrupa el mapa reciente de Asia, Londres y Nueva York para un corte histórico concreto.
@dataclass(frozen=True, slots=True)
class SessionBrainReport:
    timeframe: str
    data_cutoff_utc: datetime
    sessions: tuple[SessionRange, ...]

    # Convierte el reporte a estructuras simples para CLI, JSON y futuros cerebros.
    def to_dict(self) -> dict[str, object]:
        return {
            "timeframe": self.timeframe,
            "data_cutoff_utc": self.data_cutoff_utc.isoformat(),
            "sessions": [
                {
                    "name": session.session_name,
                    "timezone": session.timezone_name,
                    "started_at_utc": session.started_at_utc.isoformat(),
                    "ended_at_utc": session.ended_at_utc.isoformat(),
                    "bar_count": session.bar_count,
                    "expected_bar_count": session.expected_bar_count,
                    "high": session.high,
                    "low": session.low,
                    "open": session.open,
                    "close": session.close,
                    "range_size": session.range_size,
                    "tick_volume": session.tick_volume,
                    "status": session.status,
                }
                for session in self.sessions
            ],
        }


# Calcula rangos de sesiones desde velas cerradas y mantiene el horario de verano correcto.
class SessionBrain:
    _definitions = (
        TradingSessionDefinition("ASIA", "Asia/Tokyo", time(9), time(18)),
        TradingSessionDefinition("LONDRES", "Europe/London", time(8), time(17)),
        TradingSessionDefinition("NUEVA_YORK", "America/New_York", time(8), time(17)),
    )

    # Analiza la última sesión completamente cerrada de cada mercado usando el repositorio común.
    def run(
        self,
        repository: MarketDataRepository,
        identity: InstrumentIdentity,
        cutoff_utc: datetime,
        timeframe: str = "M5",
        lookback_bars: int = 2_000,
    ) -> SessionBrainReport:
        bars = repository.closed_bars(identity, timeframe, cutoff_utc, lookback_bars)
        interval = timeframe_duration(timeframe)
        return SessionBrainReport(
            timeframe,
            cutoff_utc,
            tuple(
                _last_completed_range(definition, bars, cutoff_utc, interval)
                for definition in self._definitions
            ),
        )


# Obtiene el último intervalo local cerrado y resume exclusivamente sus velas disponibles.
def _last_completed_range(
    definition: TradingSessionDefinition,
    bars: tuple[M1Bar, ...],
    cutoff_utc: datetime,
    interval: timedelta,
) -> SessionRange:
    timezone = ZoneInfo(definition.timezone_name)
    local_cutoff = cutoff_utc.astimezone(timezone)
    local_date = local_cutoff.date()
    start = datetime.combine(local_date, definition.starts_at_local, tzinfo=timezone)
    end = datetime.combine(local_date, definition.ends_at_local, tzinfo=timezone)
    if end <= start:
        end += timedelta(days=1)
    if end.astimezone(UTC) > cutoff_utc:
        start -= timedelta(days=1)
        end -= timedelta(days=1)
    start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
    included = tuple(bar for bar in bars if start_utc <= bar.open_time_utc < end_utc)
    expected = int((end_utc - start_utc) / interval)
    if not included:
        return SessionRange(
            definition.name, definition.timezone_name, start_utc, end_utc, 0, expected,
            None, None, None, None, 0, "SIN_DATOS"
        )
    status = "COMPLETA" if len(included) == expected else "INCOMPLETA"
    return SessionRange(
        definition.name,
        definition.timezone_name,
        start_utc,
        end_utc,
        len(included),
        expected,
        max(bar.high for bar in included),
        min(bar.low for bar in included),
        included[0].open,
        included[-1].close,
        sum(bar.tick_volume for bar in included),
        status,
    )
