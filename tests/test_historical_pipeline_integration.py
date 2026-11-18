from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.infrastructure.csv_market_repository import CsvMarketDataRepository
from xau_collector.services.historical_multi_timeframe import HistoricalMultiTimeframeRunner
from xau_collector.services.historical_replay import HistoricalReplay
from xau_collector.services.history_source_comparison import HistoricalSourceComparisonService


# Valida el flujo técnico histórico completo con el contrato de datos que usará PostgreSQL.
class HistoricalPipelineIntegrationTests(unittest.TestCase):
    _cutoff = datetime(2026, 10, 30, 20, tzinfo=UTC)
    _identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "mt5_csv")

    # Comprueba estructura, confirmación, niveles y consolidaciones con un corte reproducible.
    def test_complete_analysis_is_reproducible_from_validated_csv_data(self) -> None:
        repository = CsvMarketDataRepository(Path("data/raw"))
        first = HistoricalMultiTimeframeRunner().run_from_repository(
            repository, self._identity, self._cutoff
        )
        second = HistoricalMultiTimeframeRunner().run_from_repository(
            repository, self._identity, self._cutoff
        )

        self.assertEqual(first, second)
        self.assertEqual(first.h4.timeframe, "H4")
        self.assertEqual(first.h1.timeframe, "H1")
        self.assertEqual(first.m15.timeframe, "M15")
        self.assertEqual(first.m5.timeframe, "M5")
        self.assertEqual(len(first.explanation), 7)

    # Confirma análisis multitemporal equivalente sin depender de rutas internas.
    def test_common_repository_contract_produces_equivalent_full_analysis(self) -> None:
        repository = CsvMarketDataRepository(Path("data/raw"))
        equivalent, differences = HistoricalSourceComparisonService().compare_multitimeframe(
            repository, repository, self._identity, self._cutoff
        )

        self.assertTrue(equivalent)
        self.assertEqual(differences, ())

    # Garantiza que cada paso del replay entrega exclusivamente velas cerradas en su instante.
    def test_replay_never_exposes_future_m5_bars(self) -> None:
        repository = CsvMarketDataRepository(Path("data/raw"))
        steps = tuple(
            HistoricalReplay().steps(
                repository,
                self._identity,
                "M5",
                datetime(2026, 10, 30, 19, tzinfo=UTC),
                self._cutoff,
                576,
            )
        )

        self.assertTrue(steps)
        for step in steps:
            self.assertTrue(
                all(
                    bar.open_time_utc.timestamp() + 300 <= step.cutoff_utc.timestamp()
                    for bar in step.closed_bars
                )
            )


if __name__ == "__main__":
    unittest.main()
