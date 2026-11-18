from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.infrastructure.historical_csv import HistoricalCsvReader
from xau_collector.services.consolidation_poi import ConsolidationRules, _find_pois


# Valida consolidaciones A-B sobre históricos locales, sin consultar MT5.
class HistoricalConsolidationTests(unittest.TestCase):
    # Comprueba que cada temporalidad produce zonas con límites y ruptura coherentes.
    def test_downloaded_histories_produce_valid_consolidation_candidates(self) -> None:
        reader = HistoricalCsvReader()
        cases = (
            ("H4", "data/raw/h4/XAUUSDm_20220101_20261109.csv", ConsolidationRules(3, 0.12)),
            ("H1", "data/raw/h1/XAUUSDm_20251110_20261109.csv", ConsolidationRules(3, 0.15)),
            ("M15", "data/raw/m15/XAUUSDm_20260510_20261109.csv", ConsolidationRules(3, 0.18)),
            ("M5", "data/raw/m5/XAUUSDm_20260810_20261109.csv", ConsolidationRules(3, 0.20)),
        )
        for timeframe, filename, rules in cases:
            with self.subTest(timeframe=timeframe):
                pois = _find_pois(reader.read(Path(filename)), rules)
                self.assertTrue(pois)
                self.assertTrue(all(poi.low < poi.high for poi in pois))
                self.assertTrue(
                    all(poi.breakout_direction in ("ALCISTA", "BAJISTA") for poi in pois)
                )


if __name__ == "__main__":
    unittest.main()
