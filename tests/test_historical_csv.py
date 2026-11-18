from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.infrastructure.historical_csv import HistoricalCsvReader


# Verifica que las pruebas puedan leer históricos locales sin usar MetaTrader 5.
class HistoricalCsvReaderTests(unittest.TestCase):
    # Lee el histórico H4 descargado y valida que contiene velas ordenadas.
    def test_reads_downloaded_h4_history(self) -> None:
        source = Path("data/raw/h4/XAUUSDm_20220101_20261109.csv")
        if not source.is_file():
            self.skipTest("No existe el histórico H4 local")

        bars = HistoricalCsvReader().read(source)

        self.assertTrue(bars)
        self.assertEqual(tuple(sorted(bars, key=lambda bar: bar.open_time_utc)), bars)


if __name__ == "__main__":
    unittest.main()
