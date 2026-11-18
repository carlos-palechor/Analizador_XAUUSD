from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.services.historical_multi_timeframe import HistoricalMultiTimeframeRunner


# Ejecuta cortes históricos representativos sin depender del mercado en vivo.
class HistoricalScenariosTests(unittest.TestCase):
    # Comprueba que distintos momentos históricos produzcan un análisis completo.
    def test_runs_multiple_historical_cutoffs(self) -> None:
        runner = HistoricalMultiTimeframeRunner()
        for cutoff in (
            datetime(2026, 8, 20, 20, tzinfo=UTC),
            datetime(2026, 9, 30, 20, tzinfo=UTC),
            datetime(2026, 10, 30, 20, tzinfo=UTC),
        ):
            with self.subTest(cutoff=cutoff):
                analysis = runner.run(Path("data/raw"), cutoff)
                self.assertTrue(analysis.explanation)
                self.assertIn(
                    analysis.h4_h1_alignment,
                    ("ALINEADO_ALCISTA", "ALINEADO_BAJISTA", "NEUTRAL", "CONFLICTO"),
                )

    # Conserva un resultado histórico revisable para evitar cambios silenciosos de reglas.
    def test_october_30_snapshot_has_expected_blocked_context(self) -> None:
        analysis = HistoricalMultiTimeframeRunner().run(
            Path("data/raw"), datetime(2026, 10, 30, 20, tzinfo=UTC)
        )

        self.assertEqual(analysis.h4_h1_alignment, "NEUTRAL")
        self.assertEqual(analysis.h1.direction, "BAJISTA")
        self.assertEqual(analysis.confirmation.m15_state, "SIN_POI")
        self.assertFalse(analysis.confirmation.m5_body_break)


if __name__ == "__main__":
    unittest.main()
