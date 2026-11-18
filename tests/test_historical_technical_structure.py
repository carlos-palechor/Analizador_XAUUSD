from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.infrastructure.historical_csv import HistoricalCsvReader
from xau_collector.services.technical_structure import _macro_direction, _swing_highs, _swing_lows


# Valida que los históricos locales contienen estructura utilizable en cada temporalidad.
class HistoricalTechnicalStructureTests(unittest.TestCase):
    # Comprueba pivotes y dirección calculable sobre cada archivo histórico descargado.
    def test_downloaded_histories_produce_ordered_structures(self) -> None:
        reader = HistoricalCsvReader()
        for timeframe, filename in (
            ("H4", "data/raw/h4/XAUUSDm_20220101_20261109.csv"),
            ("H1", "data/raw/h1/XAUUSDm_20251110_20261109.csv"),
            ("M15", "data/raw/m15/XAUUSDm_20260510_20261109.csv"),
            ("M5", "data/raw/m5/XAUUSDm_20260810_20261109.csv"),
        ):
            with self.subTest(timeframe=timeframe):
                bars = reader.read(Path(filename))
                highs = _swing_highs(bars, 2)
                lows = _swing_lows(bars, 2)
                direction = _macro_direction(highs, lows)
                self.assertTrue(bars)
                self.assertGreater(len(highs), 1)
                self.assertGreater(len(lows), 1)
                self.assertIn(direction.value, ("ALCISTA", "BAJISTA", "NEUTRAL"))


if __name__ == "__main__":
    unittest.main()
