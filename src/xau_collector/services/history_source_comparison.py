from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.ports.market_repository import MarketDataRepository
from xau_collector.services.consolidation_poi import rules_for_timeframe
from xau_collector.services.historical_multi_timeframe import (
    HistoricalMultiTimeframeAnalysis,
    HistoricalMultiTimeframeRunner,
)
from xau_collector.services.historical_technical_runner import HistoricalTechnicalRunner


# Resume si CSV y PostgreSQL producen la misma lectura técnica con igual corte.
@dataclass(frozen=True, slots=True)
class SourceComparison:
    timeframe: str
    csv_bar_count: int
    postgres_bar_count: int
    equivalent: bool
    differences: tuple[str, ...]

    # Convierte el resultado en una estructura simple para CLI y reportes auditables.
    def to_dict(self) -> dict[str, object]:
        return {
            "timeframe": self.timeframe,
            "csv_bar_count": self.csv_bar_count,
            "postgres_bar_count": self.postgres_bar_count,
            "equivalent": self.equivalent,
            "differences": self.differences,
        }


# Ejecuta el mismo motor técnico sobre dos repositorios sin conocer su infraestructura.
class HistoricalSourceComparisonService:
    # Compara conteo, OHLC y resultado técnico de una temporalidad concreta.
    def compare(
        self,
        csv_repository: MarketDataRepository,
        postgres_repository: MarketDataRepository,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime | None = None,
        lookback_bars: int = 180,
    ) -> SourceComparison:
        csv_bars = csv_repository.closed_bars(identity, timeframe, cutoff_utc, lookback_bars)
        postgres_bars = postgres_repository.closed_bars(
            identity, timeframe, cutoff_utc, lookback_bars
        )
        differences = _bar_differences(csv_bars, postgres_bars)
        runner = HistoricalTechnicalRunner()
        csv_result = runner.run_bars(timeframe, csv_bars, rules_for_timeframe(timeframe))
        postgres_result = runner.run_bars(timeframe, postgres_bars, rules_for_timeframe(timeframe))
        if csv_result != postgres_result:
            differences += ("RESULTADO_TECNICO_DIFERENTE",)
        return SourceComparison(
            timeframe, len(csv_bars), len(postgres_bars), not differences, differences
        )

    # Compara el coordinador completo H4/H1/M15/M5, incluidas confirmaciones y explicaciones.
    def compare_multitimeframe(
        self,
        csv_repository: MarketDataRepository,
        postgres_repository: MarketDataRepository,
        identity: InstrumentIdentity,
        cutoff_utc: datetime | None = None,
    ) -> tuple[bool, tuple[str, ...]]:
        runner = HistoricalMultiTimeframeRunner()
        csv_analysis = runner.run_from_repository(csv_repository, identity, cutoff_utc)
        postgres_analysis = runner.run_from_repository(postgres_repository, identity, cutoff_utc)
        return _analysis_equivalence(csv_analysis, postgres_analysis)


# Compara cada OHLC y su hora de apertura sin aceptar diferencias silenciosas.
def _bar_differences(
    csv_bars: tuple[object, ...], postgres_bars: tuple[object, ...]
) -> tuple[str, ...]:
    if len(csv_bars) != len(postgres_bars):
        return ("CANTIDAD_DE_VELAS_DIFERENTE",)
    for csv_bar, postgres_bar in zip(csv_bars, postgres_bars, strict=True):
        if csv_bar != postgres_bar:
            return ("OHLC_O_TIEMPO_DIFERENTE",)
    return ()


# Compara la respuesta completa sin ocultar un cambio de estructura, objetivos o explicación.
def _analysis_equivalence(
    csv_analysis: HistoricalMultiTimeframeAnalysis,
    postgres_analysis: HistoricalMultiTimeframeAnalysis,
) -> tuple[bool, tuple[str, ...]]:
    differences: list[str] = []
    for timeframe in ("h4", "h1", "m15", "m5"):
        if getattr(csv_analysis, timeframe) != getattr(postgres_analysis, timeframe):
            differences.append(f"{timeframe.upper()}_DIFERENTE")
    for field in (
        "h4_h1_alignment",
        "m15_context",
        "m5_context",
        "confirmation",
        "key_levels",
        "consolidations",
        "targets_above",
        "targets_below",
        "explanation",
    ):
        if getattr(csv_analysis, field) != getattr(postgres_analysis, field):
            differences.append(f"{field.upper()}_DIFERENTE")
    return not differences, tuple(differences)
