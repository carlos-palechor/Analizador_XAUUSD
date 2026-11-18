from __future__ import annotations

import unittest
from types import SimpleNamespace

from xau_collector.services.market_data_quality_brain import BrainStatus
from xau_collector.services.technical_alignment import TechnicalAlignment, evaluate_alignment
from xau_collector.services.technical_structure import (
    M5ObservationState,
    MacroDirection,
    PoiConfirmationState,
)


# Construye un contexto mínimo para aislar la regla de alineación.
def context(
    quality: BrainStatus,
    direction: MacroDirection,
    break_direction: str | None,
    m15: PoiConfirmationState,
    m5: M5ObservationState,
) -> SimpleNamespace:
    body_break = SimpleNamespace(direction=break_direction) if break_direction else None
    return SimpleNamespace(
        data_quality=SimpleNamespace(status=quality),
        h4=SimpleNamespace(direction=direction),
        h1=SimpleNamespace(latest_body_break=body_break),
        m15=SimpleNamespace(state=m15),
        m5=SimpleNamespace(state=m5),
    )


# Verifica decisiones de alineación sin depender de archivos ni MetaTrader 5.
class TechnicalAlignmentBehaviorTests(unittest.TestCase):
    # Reconoce bloqueo si M15 aún no confirmó el POI.
    def test_blocks_without_m15_confirmation(self) -> None:
        result, _ = evaluate_alignment(
            context(
                BrainStatus.VALID,
                MacroDirection.BULLISH,
                "ALCISTA",
                PoiConfirmationState.WAITING_FOR_RETEST,
                M5ObservationState.PREFERRED_SETUP,
            )
        )
        self.assertEqual(result, TechnicalAlignment.BLOCKED)

    # Reconoce H4 y H1 alineados al alza cuando M15/M5 ya cumplieron.
    def test_recognizes_bullish_alignment(self) -> None:
        result, _ = evaluate_alignment(
            context(
                BrainStatus.VALID,
                MacroDirection.BULLISH,
                "ALCISTA",
                PoiConfirmationState.CONFIRMED,
                M5ObservationState.PREFERRED_SETUP,
            )
        )
        self.assertEqual(result, TechnicalAlignment.BULLISH)

    # Reconoce H4 y H1 alineados a la baja cuando M15/M5 ya cumplieron.
    def test_recognizes_bearish_alignment(self) -> None:
        result, _ = evaluate_alignment(
            context(
                BrainStatus.VALID,
                MacroDirection.BEARISH,
                "BAJISTA",
                PoiConfirmationState.CONFIRMED,
                M5ObservationState.STANDARD_SETUP,
            )
        )
        self.assertEqual(result, TechnicalAlignment.BEARISH)

    # Mantiene neutralidad si H4 aún no define una dirección macro.
    def test_recognizes_neutral_context(self) -> None:
        result, _ = evaluate_alignment(
            context(
                BrainStatus.VALID,
                MacroDirection.NEUTRAL,
                "ALCISTA",
                PoiConfirmationState.CONFIRMED,
                M5ObservationState.PREFERRED_SETUP,
            )
        )
        self.assertEqual(result, TechnicalAlignment.NEUTRAL)

    # Declara conflicto cuando H4 y la última ruptura H1 apuntan en sentidos opuestos.
    def test_recognizes_conflicting_timeframes(self) -> None:
        result, _ = evaluate_alignment(
            context(
                BrainStatus.VALID,
                MacroDirection.BULLISH,
                "BAJISTA",
                PoiConfirmationState.CONFIRMED,
                M5ObservationState.PREFERRED_SETUP,
            )
        )
        self.assertEqual(result, TechnicalAlignment.CONFLICT)


if __name__ == "__main__":
    unittest.main()
