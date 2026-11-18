from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from xau_collector.domain.models import M1Bar
from xau_collector.services.historical_technical_runner import _timeframe_duration
from xau_collector.services.technical_structure import (
    PoiConfirmationState,
    PointOfInterest,
    StructuralPivot,
    StructureBreak,
    _m15_confirmation,
    _m15_confirmation_time,
)


# Protege reglas corregidas que no deben volver a introducir información inválida.
class TechnicalRegressionTests(unittest.TestCase):
    # Usa la duración de cada temporalidad para excluir velas todavía activas.
    def test_timeframe_duration_excludes_open_bar_at_cutoff(self) -> None:
        opening = datetime(2026, 10, 30, 20, tzinfo=UTC)
        self.assertGreater(opening + _timeframe_duration("H4"), opening)
        self.assertEqual(opening + _timeframe_duration("M5"), opening + timedelta(minutes=5))
        self.assertEqual(opening + _timeframe_duration("M1"), opening + timedelta(minutes=1))

    # Declara explícitamente que no hay confirmación cuando no existe POI H1.
    def test_reports_no_poi_instead_of_waiting_for_retest(self) -> None:
        state, interaction = _m15_confirmation(None, ())
        self.assertEqual(state, PoiConfirmationState.NO_POI)
        self.assertIsNone(interaction)

    # Encuentra la vela M15 exacta que habilita la observación posterior de M5.
    def test_uses_confirmation_candle_as_m5_start(self) -> None:
        opened = datetime(2026, 1, 5, tzinfo=UTC)
        pivot = StructuralPivot("HIGH", 10, opened)
        structure_break = StructureBreak("ALCISTA", pivot, opened, 11)
        poi = PointOfInterest("ORIGEN_IMPULSO", "ALCISTA", 5, 7, opened, structure_break)
        interaction = M1Bar(opened + timedelta(minutes=15), 7, 7, 6, 6.5, 1, 0, 0)
        confirmation = M1Bar(opened + timedelta(minutes=30), 7, 8, 7, 8, 1, 0, 0)

        state, last_interaction = _m15_confirmation(poi, (interaction, confirmation))
        confirmed_at = _m15_confirmation_time(
            poi, (interaction, confirmation), state, last_interaction
        )

        self.assertEqual(state, PoiConfirmationState.CONFIRMED)
        self.assertEqual(confirmed_at, confirmation.open_time_utc)


if __name__ == "__main__":
    unittest.main()
