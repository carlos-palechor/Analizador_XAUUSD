from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from xau_collector.domain.models import M1Bar
from xau_collector.errors import InsufficientHistoricalDataError
from xau_collector.services.consolidation_poi import ConsolidationRules, _find_pois
from xau_collector.services.historical_coverage import evaluate_historical_coverage
from xau_collector.services.historical_import_validation import HistoricalCsvValidator
from xau_collector.services.technical_structure import (
    _candidate_poi,
    _latest_body_break,
    _macro_direction,
    _resting_liquidity,
    _swing_highs,
    _swing_lows,
)


# Resume un análisis técnico ejecutado solamente con archivos históricos locales.
@dataclass(frozen=True, slots=True)
class HistoricalTechnicalRun:
    timeframe: str
    bar_count: int
    direction: str
    swing_high_count: int
    swing_low_count: int
    buy_side_liquidity_count: int
    sell_side_liquidity_count: int
    latest_body_break_direction: str | None
    latest_body_break_at_utc: datetime | None
    candidate_poi_range: tuple[float, float] | None
    consolidation_count: int
    coverage_state: str
    coverage_gap_count: int
    latest_close: float
    window_high: float
    window_low: float


# Ejecuta estructura y consolidaciones sobre un CSV sin conectarse a MT5.
class HistoricalTechnicalRunner:
    # Lee un archivo y devuelve sus resultados técnicos básicos verificables.
    def run(
        self,
        timeframe: str,
        source: Path,
        rules: ConsolidationRules,
        cutoff_utc: datetime | None = None,
        lookback_bars: int | None = None,
    ) -> HistoricalTechnicalRun:
        bars = HistoricalCsvValidator().validate(source).accepted_bars
        return self.run_bars(timeframe, bars, rules, cutoff_utc, lookback_bars)

    # Calcula estructura desde velas entregadas por cualquier repositorio compatible.
    def run_bars(
        self,
        timeframe: str,
        bars: tuple[M1Bar, ...],
        rules: ConsolidationRules,
        cutoff_utc: datetime | None = None,
        lookback_bars: int | None = None,
    ) -> HistoricalTechnicalRun:
        if cutoff_utc is not None:
            duration = _timeframe_duration(timeframe)
            bars = tuple(bar for bar in bars if bar.open_time_utc + duration <= cutoff_utc)
        if lookback_bars is not None:
            bars = bars[-lookback_bars:]
        minimum = _require_sufficient_bars(timeframe, bars)
        coverage = evaluate_historical_coverage(timeframe, bars, minimum)
        highs = _swing_highs(bars, 2)
        lows = _swing_lows(bars, 2)
        direction = _macro_direction(highs, lows)
        buy_side = _resting_liquidity(highs, bars, "HIGH")
        sell_side = _resting_liquidity(lows, bars, "LOW")
        latest_break = _latest_body_break(highs, lows, bars)
        candidate_poi = _candidate_poi(latest_break, bars)
        return HistoricalTechnicalRun(
            timeframe,
            len(bars),
            direction.value,
            len(highs),
            len(lows),
            len(buy_side),
            len(sell_side),
            latest_break.direction if latest_break else None,
            latest_break.confirmed_at_utc if latest_break else None,
            (candidate_poi.low, candidate_poi.high) if candidate_poi else None,
            len(_find_pois(bars, rules)),
            coverage.state.value,
            coverage.gap_count,
            bars[-1].close,
            max(bar.high for bar in bars),
            min(bar.low for bar in bars),
        )


# Devuelve la duración necesaria para excluir velas activas en un corte histórico.
def timeframe_duration(timeframe: str) -> timedelta:
    durations = {
        "H4": timedelta(hours=4),
        "H1": timedelta(hours=1),
        "M15": timedelta(minutes=15),
        "M5": timedelta(minutes=5),
        "M1": timedelta(minutes=1),
    }
    try:
        return durations[timeframe]
    except KeyError as exc:
        raise ValueError(f"Temporalidad no soportada: {timeframe}") from exc


# Conserva compatibilidad temporal para código que aún importa el nombre anterior.
_timeframe_duration = timeframe_duration


# Impide interpretar estructura sin el mínimo contexto de velas cerradas.
def _require_sufficient_bars(timeframe: str, bars: tuple[M1Bar, ...]) -> int:
    required = {"H4": 12, "H1": 20, "M15": 30, "M5": 40}.get(timeframe)
    if required is None:
        raise ValueError(f"Temporalidad no soportada: {timeframe}")
    if len(bars) < required:
        raise InsufficientHistoricalDataError(
            f"{timeframe} requiere al menos {required} velas cerradas; recibió {len(bars)}"
        )
    return required
