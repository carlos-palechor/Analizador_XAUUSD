from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


# Define una descarga histórica fija para construir y probar una temporalidad.
@dataclass(frozen=True, slots=True)
class HistoryDownloadRequest:
    timeframe: str
    start_utc: datetime
    end_utc: datetime


# Centraliza el plan de históricos sin mezclarlo con el seguimiento en vivo.
class HistoryDownloadPlan:
    # Devuelve las temporalidades y rangos acordados para la construcción inicial.
    def build(
        self, start_h4_utc: datetime, end_utc: datetime
    ) -> tuple[HistoryDownloadRequest, ...]:
        return (
            HistoryDownloadRequest("H4", start_h4_utc, end_utc),
            HistoryDownloadRequest("H1", start_h4_utc, end_utc),
            HistoryDownloadRequest("M15", start_h4_utc, end_utc),
            HistoryDownloadRequest("M5", start_h4_utc, end_utc),
        )
