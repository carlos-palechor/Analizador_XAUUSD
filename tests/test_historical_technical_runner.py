from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.services.consolidation_poi import ConsolidationRules
from xau_collector.services.historical_technical_runner import HistoricalTechnicalRunner


# Verifica el ejecutor integrado sobre todas las temporalidades locales.
class HistoricalTechnicalRunnerTests(unittest.TestCase):
    # Ejecuta análisis local sin MT5 y devuelve resultados para cada CSV descargado.
    def test_runs_on_all_downloaded_timeframes(self) -> None:
        runner = HistoricalTechnicalRunner()
        cases = (
            ("H4", "data/raw/h4/XAUUSDm_20220101_20261109.csv", ConsolidationRules(3, 0.12)),
            ("H1", "data/raw/h1/XAUUSDm_20251110_20261109.csv", ConsolidationRules(3, 0.15)),
            ("M15", "data/raw/m15/XAUUSDm_20260510_20261109.csv", ConsolidationRules(3, 0.18)),
            ("M5", "data/raw/m5/XAUUSDm_20260810_20261109.csv", ConsolidationRules(3, 0.20)),
        )
        for timeframe, filename, rules in cases:
            with self.subTest(timeframe=timeframe):
                result = runner.run(timeframe, Path(filename), rules)
                self.assertGreater(result.bar_count, 0)
                self.assertGreater(result.consolidation_count, 0)

    # Comprueba que el motor recibe velas por contrato, sin depender de un archivo CSV.
    def test_runs_same_result_from_preloaded_bars(self) -> None:
        source = Path("data/raw/m5/XAUUSDm_20260810_20261109.csv")
        rules = ConsolidationRules(3, 0.20)
        runner = HistoricalTechnicalRunner()
        from_file = runner.run("M5", source, rules, lookback_bars=100)
        from xau_collector.infrastructure.historical_csv import HistoricalCsvReader

        from_bars = runner.run_bars(
            "M5", HistoricalCsvReader().read(source), rules, lookback_bars=100
        )
        self.assertEqual(from_bars, from_file)


if __name__ == "__main__":
    unittest.main()
