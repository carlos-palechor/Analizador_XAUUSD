from __future__ import annotations

from enum import StrEnum

from xau_collector.services.market_data_quality_brain import BrainStatus
from xau_collector.services.technical_context import TechnicalContext
from xau_collector.services.technical_structure import (
    M5ObservationState,
    MacroDirection,
    PoiConfirmationState,
)


# Enumera la coherencia entre temporalidades antes de que una estrategia evalúe una entrada.
class TechnicalAlignment(StrEnum):
    BULLISH = "ALINEADO_ALCISTA"
    BEARISH = "ALINEADO_BAJISTA"
    NEUTRAL = "NEUTRAL"
    CONFLICT = "CONFLICTO_DE_TEMPORALIDADES"
    BLOCKED = "BLOQUEADO"


# Resume una alineación y el motivo verificable que la produjo.
def evaluate_alignment(context: TechnicalContext) -> tuple[TechnicalAlignment, str]:
    """Evalúa contexto técnico sin emitir una señal ni una orden."""
    if context.data_quality.status is not BrainStatus.VALID:
        return TechnicalAlignment.BLOCKED, "La calidad de datos no permite continuar."
    if context.m15.state is not PoiConfirmationState.CONFIRMED:
        return TechnicalAlignment.BLOCKED, "M15 aún no confirmó el POI."
    if context.m5.state not in (
        M5ObservationState.PREFERRED_SETUP,
        M5ObservationState.STANDARD_SETUP,
    ):
        return TechnicalAlignment.BLOCKED, "M5 aún no completó un setup técnico."
    direction = context.h4.direction
    break_direction = (
        context.h1.latest_body_break.direction if context.h1.latest_body_break else None
    )
    if direction is MacroDirection.BULLISH and break_direction == "ALCISTA":
        return TechnicalAlignment.BULLISH, "H4 y H1 están alineados al alza."
    if direction is MacroDirection.BEARISH and break_direction == "BAJISTA":
        return TechnicalAlignment.BEARISH, "H4 y H1 están alineados a la baja."
    if direction is MacroDirection.NEUTRAL or break_direction is None:
        return TechnicalAlignment.NEUTRAL, "No existe una dirección mayor suficientemente definida."
    return TechnicalAlignment.CONFLICT, "H4 y H1 muestran direcciones distintas."
