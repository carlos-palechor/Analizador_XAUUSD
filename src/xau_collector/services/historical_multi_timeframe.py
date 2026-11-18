from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.infrastructure.csv_market_repository import CsvMarketDataRepository
from xau_collector.ports.market_repository import MarketDataRepository
from xau_collector.services.consolidation_poi import (
    ConsolidationPoi,
    _find_pois,
    rules_for_timeframe,
)
from xau_collector.services.historical_confirmation import (
    HistoricalConfirmation,
    HistoricalConfirmationRunner,
)
from xau_collector.services.historical_key_levels import HistoricalKeyLevels, HistoricalPeriodLevel
from xau_collector.services.historical_technical_runner import (
    HistoricalTechnicalRun,
    HistoricalTechnicalRunner,
)


# Reúne resultados H4, H1, M15 y M5 generados solamente desde históricos locales.
@dataclass(frozen=True, slots=True)
class HistoricalMultiTimeframeAnalysis:
    h4: HistoricalTechnicalRun
    h1: HistoricalTechnicalRun
    m15: HistoricalTechnicalRun
    m5: HistoricalTechnicalRun
    h4_h1_alignment: str
    m15_context: str
    m5_context: str
    explanation: tuple[str, ...]
    targets_above: tuple[float, ...]
    targets_below: tuple[float, ...]
    confirmation: HistoricalConfirmation
    key_levels: tuple[HistoricalPeriodLevel, ...]
    consolidations: tuple[tuple[str, ConsolidationPoi], ...]


# Coordina análisis por temporalidad sin conexión MT5 ni seguimiento en vivo.
class HistoricalMultiTimeframeRunner:
    # Ejecuta las cuatro temporalidades descargadas con sus reglas respectivas.
    def run(
        self, root: Path, cutoff_utc: datetime | None = None
    ) -> HistoricalMultiTimeframeAnalysis:
        identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "csv")
        return self.run_from_repository(CsvMarketDataRepository(root), identity, cutoff_utc)

    # Ejecuta temporalidades con el contrato común, independiente de rutas fijas.
    def run_from_repository(
        self,
        repository: MarketDataRepository,
        identity: InstrumentIdentity,
        cutoff_utc: datetime | None = None,
    ) -> HistoricalMultiTimeframeAnalysis:
        runner = HistoricalTechnicalRunner()
        h4 = _run_timeframe(runner, repository, identity, "H4", cutoff_utc, 180)
        h1 = _run_timeframe(runner, repository, identity, "H1", cutoff_utc, 360)
        m15 = _run_timeframe(runner, repository, identity, "M15", cutoff_utc, 480)
        m5 = _run_timeframe(runner, repository, identity, "M5", cutoff_utc, 576)
        alignment = _alignment(h4.direction, h1.direction)
        m5_bars = repository.closed_bars(identity, "M5", cutoff_utc)
        consolidations = tuple(
            (timeframe, poi)
            for timeframe, bars in (
                ("H4", repository.closed_bars(identity, "H4", cutoff_utc, 180)),
                ("H1", repository.closed_bars(identity, "H1", cutoff_utc, 360)),
                ("M15", repository.closed_bars(identity, "M15", cutoff_utc, 480)),
                ("M5", m5_bars),
            )
            for poi in _find_pois(bars, rules_for_timeframe(timeframe))
        )
        key_levels = HistoricalKeyLevels().calculate(m5_bars)
        targets_above, targets_below = _targets(m5.latest_close, (h4, h1, m15, m5), key_levels)
        confirmation = HistoricalConfirmationRunner().run(repository, identity, cutoff_utc)
        return HistoricalMultiTimeframeAnalysis(
            h4,
            h1,
            m15,
            m5,
            alignment,
            _smaller_context(alignment, m15.direction),
            _smaller_context(alignment, m5.direction),
            _explanation(
                h4,
                h1,
                m15,
                m5,
                alignment,
                confirmation,
                targets_above,
                targets_below,
            ),
            targets_above,
            targets_below,
            confirmation,
            key_levels,
            consolidations,
        )


# Ejecuta el motor existente sobre una fuente resuelta por el repositorio común.
def _run_timeframe(
    runner: HistoricalTechnicalRunner,
    repository: MarketDataRepository,
    identity: InstrumentIdentity,
    timeframe: str,
    cutoff_utc: datetime | None,
    lookback_bars: int,
) -> HistoricalTechnicalRun:
    return runner.run_bars(
        timeframe,
        repository.closed_bars(identity, timeframe, cutoff_utc, lookback_bars),
        rules_for_timeframe(timeframe),
    )


# Resume coherencia H4/H1 sin crear una señal de trading.
def _alignment(h4: str, h1: str) -> str:
    if h4 == h1 and h4 in ("ALCISTA", "BAJISTA"):
        return f"ALINEADO_{h4}"
    if "NEUTRAL" in (h4, h1):
        return "NEUTRAL"
    return "CONFLICTO"


# Describe si una temporalidad menor acompaña el contexto mayor histórico.
def _smaller_context(alignment: str, direction: str) -> str:
    expected = alignment.removeprefix("ALINEADO_")
    if alignment.startswith("ALINEADO_") and direction == expected:
        return "ACOMPAÑA"
    if alignment.startswith("ALINEADO_") and direction in ("ALCISTA", "BAJISTA"):
        return "CONTRADICE"
    return "SIN_CONFIRMACION"


# Ordena límites históricos recientes como destinos posibles, sin predecir su alcance.
def _targets(
    price: float,
    runs: tuple[HistoricalTechnicalRun, ...],
    key_levels: tuple[HistoricalPeriodLevel, ...],
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    values = {
        *(value for run in runs for value in (run.window_high, run.window_low)),
        *(value for level in key_levels for value in (level.high, level.low)),
    }
    return tuple(sorted(value for value in values if value > price)), tuple(
        sorted((value for value in values if value < price), reverse=True)
    )


# Redacta evidencia histórica breve para revisar el análisis sin inspeccionar código.
def _explanation(
    h4: HistoricalTechnicalRun,
    h1: HistoricalTechnicalRun,
    m15: HistoricalTechnicalRun,
    m5: HistoricalTechnicalRun,
    alignment: str,
    confirmation: HistoricalConfirmation,
    targets_above: tuple[float, ...],
    targets_below: tuple[float, ...],
) -> tuple[str, ...]:
    return (
        f"H4: {h4.direction}; pivotes {h4.swing_high_count}/{h4.swing_low_count}.",
        (
            f"H1: {h1.direction}; BOS {h1.latest_body_break_direction or 'SIN_BOS'}; "
            f"liquidez arriba/abajo {h1.buy_side_liquidity_count}/{h1.sell_side_liquidity_count}."
        ),
        f"POI H1: {h1.candidate_poi_range or 'SIN_POI'}.",
        f"Contexto H4-H1: {alignment}.",
        f"M15: {m15.direction}; estado POI {confirmation.m15_state}.",
        (
            f"M5: {m5.direction}; barrido/reacción/ruptura "
            f"{confirmation.m5_sweep}/{confirmation.m5_reaction}/{confirmation.m5_body_break}."
        ),
        f"Objetivos arriba/abajo: {targets_above[:3]}/{targets_below[:3]}.",
    )
