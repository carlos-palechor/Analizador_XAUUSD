from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from xau_collector.domain.models import M1Bar
from xau_collector.services.technical_structure import (
    MacroDirection,
    PoiConfirmationState,
    PointOfInterest,
    StructuralPivot,
    StructureBreak,
    _candidate_poi,
    _closed_bars,
    _latest_body_break,
    _m15_confirmation,
    _macro_direction,
    _resting_liquidity,
    _swing_highs,
    _swing_lows,
)


# Construye una vela válida y corta para expresar escenarios de estructura H4.
def bar(index: int, high: float, low: float) -> M1Bar:
    return M1Bar(
        datetime(2026, 1, 5, tzinfo=UTC) + timedelta(hours=index * 4),
        low,
        high,
        low,
        high,
        1,
        0,
        0,
    )


# Verifica detección de pivotes y dirección sin depender de MetaTrader 5.
class TechnicalStructureTests(unittest.TestCase):
    # Impide confirmar un pivote hasta que existan las velas posteriores exigidas por su radio.
    def test_pivot_requires_future_bars_to_be_available_before_confirmation(self) -> None:
        pending = (bar(0, 10, 5), bar(1, 11, 6), bar(2, 15, 7))
        confirmed = pending + (bar(3, 11, 6), bar(4, 10, 5))

        self.assertEqual(_swing_highs(pending, 2), [])
        pivots = _swing_highs(confirmed, 2)
        self.assertEqual([pivot.price for pivot in pivots], [15])
        self.assertEqual(pivots[0].open_time_utc, pending[2].open_time_utc)

    # Reconoce contexto alcista si máximos y mínimos estructurales ascienden juntos.
    def test_detects_bullish_context_from_ascending_pivots(self) -> None:
        bars = (
            bar(0, 10, 5),
            bar(1, 11, 6),
            bar(2, 15, 7),
            bar(3, 12, 8),
            bar(4, 11, 6),
            bar(5, 12, 7),
            bar(6, 16, 8),
            bar(7, 20, 9),
            bar(8, 17, 10),
            bar(9, 15, 9),
            bar(10, 14, 10),
        )
        highs = _swing_highs(bars, 1)
        lows = _swing_lows(bars, 1)

        self.assertEqual([pivot.price for pivot in highs], [15, 20])
        self.assertEqual([pivot.price for pivot in lows], [6, 9])
        self.assertEqual(_macro_direction(highs, lows), MacroDirection.BULLISH)

    # Clasifica como neutral una estructura que no tiene ambos tipos de pivotes alineados.
    def test_returns_neutral_when_only_highs_change_direction(self) -> None:
        highs = _swing_highs((bar(0, 10, 5), bar(1, 15, 6), bar(2, 11, 7)), 1)
        lows = _swing_lows((bar(0, 10, 5), bar(1, 15, 6), bar(2, 11, 7)), 1)

        self.assertEqual(_macro_direction(highs, lows), MacroDirection.NEUTRAL)

    # Excluye una vela H4 abierta aunque MT5 la entregue en la respuesta.
    def test_excludes_forming_h4_bar(self) -> None:
        first = bar(0, 10, 5)
        forming = bar(1, 11, 6)

        closed = _closed_bars(
            (first, forming), datetime(2026, 1, 5, 6, tzinfo=UTC), timedelta(hours=4)
        )

        self.assertEqual(closed, (first,))

    # Distingue una mecha que toma liquidez de una ruptura confirmada por cierre.
    def test_identifies_resting_liquidity_and_body_break(self) -> None:
        bars = (
            bar(0, 10, 5),
            bar(1, 15, 6),
            bar(2, 11, 7),
            bar(3, 16, 8),
            bar(4, 14, 9),
        )
        highs = _swing_highs(bars, 1)
        lows = _swing_lows(bars, 1)

        self.assertEqual([pivot.price for pivot in _resting_liquidity(highs, bars, "HIGH")], [16])
        latest_break = _latest_body_break(highs, lows, bars)

        self.assertIsNotNone(latest_break)
        self.assertEqual(latest_break.direction, "ALCISTA")
        self.assertEqual(latest_break.confirmed_at_utc, bars[3].open_time_utc)

    # Forma un POI alcista desde la última vela bajista anterior al BOS confirmado.
    def test_creates_candidate_poi_from_last_opposite_candle_before_break(self) -> None:
        bars = (
            bar(0, 10, 5),
            M1Bar(datetime(2026, 1, 5, 4, tzinfo=UTC), 12, 15, 10, 14, 1, 0, 0),
            M1Bar(datetime(2026, 1, 5, 8, tzinfo=UTC), 12, 13, 9, 10, 1, 0, 0),
            M1Bar(datetime(2026, 1, 5, 12, tzinfo=UTC), 10, 14, 9, 13, 1, 0, 0),
            M1Bar(datetime(2026, 1, 5, 16, tzinfo=UTC), 13, 16, 12, 16, 1, 0, 0),
        )
        latest_break = _latest_body_break(_swing_highs(bars, 1), _swing_lows(bars, 1), bars)

        poi = _candidate_poi(latest_break, bars)

        self.assertIsNotNone(poi)
        self.assertEqual(poi.kind, "ORIGEN_IMPULSO")
        self.assertEqual(poi.direction, "ALCISTA")
        self.assertEqual((poi.low, poi.high), (9, 13))

    # Confirma un POI alcista solo cuando M15 toca la zona y cierra alcista por encima.
    def test_confirms_bullish_poi_after_retest_and_reaction(self) -> None:
        pivot = StructuralPivot("HIGH", 15, datetime(2026, 1, 5, tzinfo=UTC))
        structure_break = StructureBreak("ALCISTA", pivot, datetime(2026, 1, 5, 4, tzinfo=UTC), 16)
        poi = PointOfInterest(
            "ORIGEN_IMPULSO", "ALCISTA", 10, 13, datetime(2026, 1, 5, tzinfo=UTC), structure_break
        )
        bars = (
            M1Bar(datetime(2026, 1, 5, 4, tzinfo=UTC), 13, 14, 12, 12.5, 1, 0, 0),
            M1Bar(datetime(2026, 1, 5, 4, 15, tzinfo=UTC), 13, 16, 12, 16, 1, 0, 0),
        )

        state, interaction = _m15_confirmation(poi, bars)

        self.assertEqual(state, PoiConfirmationState.CONFIRMED)
        self.assertEqual(interaction, bars[1])


if __name__ == "__main__":
    unittest.main()
