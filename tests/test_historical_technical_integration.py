from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.infrastructure.historical_csv import HistoricalCsvReader
from xau_collector.services.consolidation_poi import ConsolidationRules, _find_pois
from xau_collector.services.technical_structure import _macro_direction, _swing_highs, _swing_lows


# Verifica que todas las temporalidades históricas alimenten el análisis técnico local.
class HistoricalTechnicalIntegrationTests(unittest.TestCase):
    # Construye estructura y consolidaciones por temporalidad sin usar MT5 en vivo.
    def test_all_historical_timeframes_are_usable_together(self) -> None:
        reader = HistoricalCsvReader()
        cases = (
            ("H4", "data/raw/h4/XAUUSDm_20220101_20261109.csv", ConsolidationRules(3, 0.12)),
            ("H1", "data/raw/h1/XAUUSDm_20251110_20261109.csv", ConsolidationRules(3, 0.15)),
            ("M15", "data/raw/m15/XAUUSDm_20260510_20261109.csv", ConsolidationRules(3, 0.18)),
            ("M5", "data/raw/m5/XAUUSDm_20260810_20261109.csv", ConsolidationRules(3, 0.20)),
        )
        for timeframe, filename, rules in cases:
            with self.subTest(timeframe=timeframe):
                bars = reader.read(Path(filename))
                direction = _macro_direction(_swing_highs(bars, 2), _swing_lows(bars, 2))
                pois = _find_pois(bars, rules)
                self.assertTrue(direction.value)
                self.assertTrue(pois)


if __name__ == "__main__":
    unittest.main()
