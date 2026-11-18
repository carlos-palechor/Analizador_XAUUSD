from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.infrastructure.csv_market_repository import CsvMarketDataRepository
from xau_collector.services.historical_confirmation import HistoricalConfirmationRunner
from xau_collector.services.historical_multi_timeframe import HistoricalMultiTimeframeRunner


# Describe un escenario histórico evaluable antes de usar el sistema en vivo.
@dataclass(frozen=True, slots=True)
class HistoricalScenario:
    cutoff_utc: datetime
    category: str
    alignment: str
    m15_state: str


# Clasifica cortes locales para revisar bloqueos, confirmaciones e invalidaciones.
class HistoricalScenarioCatalog:
    # Evalúa cada corte histórico con el análisis multitemporal y la cadena POI-M15-M5.
    def evaluate(self, root: Path, cutoffs: tuple[datetime, ...]) -> tuple[HistoricalScenario, ...]:
        multi_runner = HistoricalMultiTimeframeRunner()
        confirmation_runner = HistoricalConfirmationRunner()
        repository = CsvMarketDataRepository(root)
        identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "csv")
        scenarios: list[HistoricalScenario] = []
        for cutoff in cutoffs:
            analysis = multi_runner.run(root, cutoff)
            confirmation = confirmation_runner.run(repository, identity, cutoff)
            category = _category(analysis.h4_h1_alignment, confirmation.m15_state)
            scenarios.append(
                HistoricalScenario(
                    cutoff, category, analysis.h4_h1_alignment, confirmation.m15_state
                )
            )
        return tuple(scenarios)


# Etiqueta el motivo principal del escenario sin convertirlo en una orden.
def _category(alignment: str, m15_state: str) -> str:
    if alignment in ("NEUTRAL", "CONFLICTO"):
        return "CONTEXTO_NO_ALINEADO"
    if m15_state == "INVALIDADO":
        return "POI_INVALIDADO"
    if m15_state == "CONFIRMADO":
        return "CONFIRMACION_M15"
    return "ESPERANDO_CONFIRMACION"
