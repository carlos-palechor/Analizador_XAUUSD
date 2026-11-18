from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.infrastructure.historical_csv import HistoricalCsvReader
from xau_collector.services.historical_key_levels import HistoricalKeyLevels


# Valida niveles de periodo desde velas M5 locales.
class HistoricalKeyLevelsTests(unittest.TestCase):
    # Produce los cuatro niveles de contexto histórico esperados.
    def test_calculates_day_week_month_and_year_levels(self) -> None:
        bars = HistoricalCsvReader().read(Path("data/raw/m5/XAUUSDm_20260810_20261109.csv"))
        levels = HistoricalKeyLevels().calculate(bars)

        self.assertEqual({level.period for level in levels}, {"D1", "W1", "MN1", "Y1"})
        self.assertTrue(all(level.low < level.high for level in levels))


if __name__ == "__main__":
    unittest.main()
