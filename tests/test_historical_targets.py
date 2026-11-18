from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.infrastructure.historical_csv import HistoricalCsvReader
from xau_collector.services.key_levels import PeriodRange
from xau_collector.services.structural_targets import StructuralTargetMapper


# Valida objetivos estructurales usando precios extraídos de un histórico local.
class HistoricalTargetsTests(unittest.TestCase):
    # Separa niveles históricos por encima y debajo del último cierre observado.
    def test_maps_targets_from_downloaded_h4_history(self) -> None:
        bars = HistoricalCsvReader().read(Path("data/raw/h4/XAUUSDm_20220101_20261109.csv"))
        recent = bars[-20:]
        current_price = recent[-1].close
        level = PeriodRange(
            "H4_HISTORICO",
            recent[0].open_time_utc,
            max(bar.high for bar in recent),
            min(bar.low for bar in recent),
        )

        above, below = StructuralTargetMapper().map(current_price, (level,), ())

        self.assertTrue(above or below)
        self.assertTrue(all(item.price > current_price for item in above))
        self.assertTrue(all(item.price < current_price for item in below))


if __name__ == "__main__":
    unittest.main()
