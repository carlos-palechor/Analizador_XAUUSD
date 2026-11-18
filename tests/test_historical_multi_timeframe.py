from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.infrastructure.csv_market_repository import CsvMarketDataRepository
from xau_collector.services.historical_multi_timeframe import HistoricalMultiTimeframeRunner
from xau_collector.services.history_source_comparison import HistoricalSourceComparisonService


# Verifica que las cuatro temporalidades locales se reúnan en un análisis único.
class HistoricalMultiTimeframeRunnerTests(unittest.TestCase):
    # Ejecuta el análisis completo desde archivos locales sin MT5.
    def test_runs_all_timeframes_from_raw_history(self) -> None:
        analysis = HistoricalMultiTimeframeRunner().run(Path("data/raw"))

        self.assertEqual(analysis.h4.timeframe, "H4")
        self.assertEqual(analysis.h1.timeframe, "H1")
        self.assertEqual(analysis.m15.timeframe, "M15")
        self.assertEqual(analysis.m5.timeframe, "M5")
        self.assertIn(
            analysis.h4_h1_alignment,
            ("ALINEADO_ALCISTA", "ALINEADO_BAJISTA", "NEUTRAL", "CONFLICTO"),
        )
        self.assertIn(analysis.m15_context, ("ACOMPAÑA", "CONTRADICE", "SIN_CONFIRMACION"))
        self.assertIn(analysis.m5_context, ("ACOMPAÑA", "CONTRADICE", "SIN_CONFIRMACION"))
        self.assertEqual(len(analysis.explanation), 7)
        self.assertTrue(analysis.targets_above or analysis.targets_below)

    # Aplica el mismo instante de corte a todas las temporalidades históricas.
    def test_applies_a_common_historical_cutoff(self) -> None:
        analysis = HistoricalMultiTimeframeRunner().run(
            Path("data/raw"), datetime(2026, 10, 30, 20, tzinfo=UTC)
        )

        self.assertGreater(analysis.h4.bar_count, 0)
        self.assertGreater(analysis.h1.bar_count, 0)
        self.assertGreater(analysis.m15.bar_count, 0)
        self.assertGreater(analysis.m5.bar_count, 0)

    # Comprueba que el coordinador completo depende solo del contrato de repositorio.
    def test_full_analysis_is_equivalent_for_same_repository_contract(self) -> None:
        repository = CsvMarketDataRepository(Path("data/raw"))
        equivalent, differences = HistoricalSourceComparisonService().compare_multitimeframe(
            repository,
            repository,
            InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "csv"),
            datetime(2026, 10, 30, 20, tzinfo=UTC),
        )
        self.assertTrue(equivalent)
        self.assertEqual(differences, ())


if __name__ == "__main__":
    unittest.main()
