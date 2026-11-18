from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from xau_collector.domain.models import M1Bar
from xau_collector.services.historical_coverage import (
    HistoricalCoverageState,
    evaluate_historical_coverage,
)


# Comprueba que la cobertura distingue falta de contexto de huecos que requieren calendario.
class HistoricalCoverageTests(unittest.TestCase):
    # Marca insuficiente una ventana que no alcanza el mínimo técnico solicitado.
    def test_marks_insufficient_history(self) -> None:
        coverage = evaluate_historical_coverage("M5", (_bar(0),), 2)

        self.assertEqual(coverage.state, HistoricalCoverageState.INSUFFICIENT)

    # Mantiene visible un hueco para que sesiones determine si era pausa válida o problema de datos.
    def test_marks_gaps_for_session_review(self) -> None:
        coverage = evaluate_historical_coverage("M5", (_bar(0), _bar(2)), 2)

        self.assertEqual(coverage.state, HistoricalCoverageState.GAPS_REQUIRE_REVIEW)
        self.assertEqual(coverage.gap_count, 1)


# Construye una vela M5 mínima y válida para aislar la prueba de cobertura.
def _bar(index: int) -> M1Bar:
    return M1Bar(
        datetime(2026, 1, 5, tzinfo=UTC) + timedelta(minutes=index * 5),
        10.0,
        11.0,
        9.0,
        10.5,
        1,
        0,
        0,
    )


if __name__ == "__main__":
    unittest.main()
