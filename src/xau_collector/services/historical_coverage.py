from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from xau_collector.domain.models import M1Bar


# Clasifica si una ventana puede interpretarse o requiere revisión de calendario.
class HistoricalCoverageState(StrEnum):
    SUFFICIENT = "SUFICIENTE"
    INSUFFICIENT = "INSUFICIENTE"
    GAPS_REQUIRE_REVIEW = "HUECOS_REQUIEREN_REVISION"


# Resume cantidad, intervalo y huecos de una ventana sin confundirlos con una decisión técnica.
@dataclass(frozen=True, slots=True)
class HistoricalCoverage:
    state: HistoricalCoverageState
    required_bar_count: int
    available_bar_count: int
    gap_count: int


# Revisa cobertura cronológica antes de permitir interpretar una ventana técnica.
def evaluate_historical_coverage(
    timeframe: str, bars: Sequence[M1Bar], required_bar_count: int
) -> HistoricalCoverage:
    if len(bars) < required_bar_count:
        return HistoricalCoverage(
            HistoricalCoverageState.INSUFFICIENT, required_bar_count, len(bars), 0
        )
    duration = _timeframe_duration(timeframe)
    gaps = _gap_count(bars, duration)
    state = (
        HistoricalCoverageState.GAPS_REQUIRE_REVIEW
        if gaps
        else HistoricalCoverageState.SUFFICIENT
    )
    return HistoricalCoverage(state, required_bar_count, len(bars), gaps)


# Cuenta separaciones superiores a una vela para que el calendario del bróker las clasifique.
def _gap_count(bars: Sequence[M1Bar], duration: timedelta) -> int:
    return sum(
        next_bar.open_time_utc - previous.open_time_utc > duration
        for previous, next_bar in zip(bars, bars[1:], strict=False)
    )


# Convierte la temporalidad a duración para verificar continuidad entre aperturas de vela.
def _timeframe_duration(timeframe: str) -> timedelta:
    durations = {
        "H4": timedelta(hours=4),
        "H1": timedelta(hours=1),
        "M15": timedelta(minutes=15),
        "M5": timedelta(minutes=5),
        "M1": timedelta(minutes=1),
    }
    return durations[timeframe]
