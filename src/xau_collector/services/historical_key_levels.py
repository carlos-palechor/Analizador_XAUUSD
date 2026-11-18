from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from xau_collector.domain.models import M1Bar


# Representa máximo y mínimo de un periodo histórico delimitado por su última vela.
@dataclass(frozen=True, slots=True)
class HistoricalPeriodLevel:
    period: str
    high: float
    low: float


# Calcula niveles de periodos desde velas locales, sin conexión MT5.
class HistoricalKeyLevels:
    # Devuelve niveles D1, W1, MN1 y Y1 del periodo que contiene la última vela.
    def calculate(self, bars: Sequence[M1Bar]) -> tuple[HistoricalPeriodLevel, ...]:
        last = bars[-1].open_time_utc
        groups = (
            ("D1", lambda value: value.date() == last.date()),
            ("W1", lambda value: value.isocalendar()[:2] == last.isocalendar()[:2]),
            ("MN1", lambda value: (value.year, value.month) == (last.year, last.month)),
            ("Y1", lambda value: value.year == last.year),
        )
        return tuple(
            HistoricalPeriodLevel(
                name, max(bar.high for bar in selected), min(bar.low for bar in selected)
            )
            for name, matches in groups
            if (selected := tuple(bar for bar in bars if matches(bar.open_time_utc)))
        )
