from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from xau_collector.domain.models import M1Bar


# Enumera los estados que puede tener una interpretación antes y después del cierre.
class AnalysisState(StrEnum):
    PROVISIONAL = "PROVISIONAL"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    FINALIZED = "FINALIZED"


# Identifica sin ambigüedad el instrumento tal como lo entrega un proveedor concreto.
@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    broker: str
    server: str
    symbol: str
    source_name: str


# Describe un conjunto de velas que el cerebro puede usar en una ejecución reproducible.
@dataclass(frozen=True, slots=True)
class MarketDataSnapshot:
    identity: InstrumentIdentity
    timeframe: str
    bars: tuple[M1Bar, ...]
    received_at_utc: datetime
    data_cutoff_utc: datetime
    source_reference: str
