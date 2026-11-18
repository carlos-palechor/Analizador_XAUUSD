from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from xau_collector.services.technical_pivots import StructuralPivot


# Enumera el contexto macro que puede inferirse de pivotes H4 confirmados.
class MacroDirection(StrEnum):
    BULLISH = "ALCISTA"
    BEARISH = "BAJISTA"
    NEUTRAL = "NEUTRAL"


# Enumera el estado de confirmación M15 de un POI H1 antes de observar una entrada M5.
class PoiConfirmationState(StrEnum):
    NO_POI = "SIN_POI"
    WAITING_FOR_RETEST = "ESPERANDO_RETESTEO"
    WAITING_FOR_REACTION = "ESPERANDO_REACCION"
    CONFIRMED = "CONFIRMADO"
    INVALIDATED = "INVALIDADO"


# Enumera el resultado técnico M5 previo a cualquier estrategia de entrada.
class M5ObservationState(StrEnum):
    BLOCKED_BY_M15 = "BLOQUEADO_POR_M15"
    WAITING_FOR_REACTION = "ESPERANDO_REACCION"
    STANDARD_SETUP = "SETUP_ESTANDAR"
    PREFERRED_SETUP = "SETUP_PREFERENTE"


# Define la forma mínima de una vela que necesitan los cálculos de estructura reutilizables.
class PriceBar(Protocol):
    open_time_utc: datetime
    open: float
    high: float
    low: float
    close: float


# Describe una ruptura confirmada por cierre de cuerpo, no por una mecha aislada.
@dataclass(frozen=True, slots=True)
class StructureBreak:
    direction: str
    broken_pivot: StructuralPivot
    confirmed_at_utc: datetime
    close_price: float


# Representa una zona candidata originada antes de un BOS confirmado.
@dataclass(frozen=True, slots=True)
class PointOfInterest:
    kind: str
    direction: str
    low: float
    high: float
    source_open_time_utc: datetime
    confirmed_by: StructureBreak
