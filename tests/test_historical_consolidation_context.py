from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.infrastructure.historical_csv import HistoricalCsvReader
from xau_collector.services.consolidation_context import ConsolidationContextBuilder
from xau_collector.services.consolidation_poi import ConsolidationRules, _find_pois


# Valida relaciones fractales entre consolidaciones creadas desde históricos locales.
class HistoricalConsolidationContextTests(unittest.TestCase):
    # Confirma que las relaciones devueltas usan únicamente estados de relación válidos.
    def test_relates_h4_h1_m15_and_m5_zones(self) -> None:
        reader = HistoricalCsvReader()
        h4 = _find_pois(
            reader.read(Path("data/raw/h4/XAUUSDm_20220101_20261109.csv")),
            ConsolidationRules(3, 0.12),
        )
        h1 = _find_pois(
            reader.read(Path("data/raw/h1/XAUUSDm_20251110_20261109.csv")),
            ConsolidationRules(3, 0.15),
        )
        m15 = _find_pois(
            reader.read(Path("data/raw/m15/XAUUSDm_20260510_20261109.csv")),
            ConsolidationRules(3, 0.18),
        )
        m5 = _find_pois(
            reader.read(Path("data/raw/m5/XAUUSDm_20260810_20261109.csv")),
            ConsolidationRules(3, 0.20),
        )

        relationships = ConsolidationContextBuilder().build(h4, h1, m15, m5)

        self.assertTrue(relationships)
        self.assertTrue(all(item.relation in ("CONTENIDA", "SOLAPADA") for item in relationships))


if __name__ == "__main__":
    unittest.main()
