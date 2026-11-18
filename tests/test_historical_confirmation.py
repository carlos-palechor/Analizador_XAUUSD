from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.infrastructure.csv_market_repository import CsvMarketDataRepository
from xau_collector.services.historical_confirmation import HistoricalConfirmationRunner


# Valida la cadena H1-M15-M5 usando un corte histórico y sin MT5.
class HistoricalConfirmationTests(unittest.TestCase):
    # Devuelve un estado M15 y banderas M5 coherentes desde CSV locales.
    def test_evaluates_poi_confirmation_chain(self) -> None:
        result = HistoricalConfirmationRunner().run(
            CsvMarketDataRepository(Path("data/raw")),
            InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "csv"),
            datetime(2026, 10, 30, 20, tzinfo=UTC),
        )
        self.assertIn(
            result.m15_state,
            ("SIN_POI", "ESPERANDO_RETESTEO", "ESPERANDO_REACCION", "CONFIRMADO", "INVALIDADO"),
        )
        self.assertIsInstance(result.m5_sweep, bool)
        self.assertIsInstance(result.m5_reaction, bool)
        self.assertIsInstance(result.m5_body_break, bool)


if __name__ == "__main__":
    unittest.main()
