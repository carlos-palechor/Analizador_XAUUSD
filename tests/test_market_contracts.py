from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.errors import InsufficientHistoricalDataError
from xau_collector.infrastructure.csv_market_repository import CsvMarketDataRepository
from xau_collector.services.consolidation_poi import rules_for_timeframe
from xau_collector.services.historical_replay import HistoricalReplay
from xau_collector.services.historical_technical_runner import HistoricalTechnicalRunner


# Comprueba contratos de datos, corte cronológico y ausencia de contexto insuficiente.
class MarketContractsTests(unittest.TestCase):
    # Verifica que el repositorio no entrega una vela aún activa en el corte.
    def test_csv_repository_returns_only_closed_bars(self) -> None:
        repository = CsvMarketDataRepository(Path("data/raw"))
        identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "csv")
        cutoff = datetime(2026, 10, 30, 20, tzinfo=UTC)
        bars = repository.closed_bars(identity, "M5", cutoff)
        self.assertTrue(bars)
        self.assertLessEqual(bars[-1].open_time_utc.minute % 5, 4)
        self.assertLessEqual(bars[-1].open_time_utc.timestamp() + 300, cutoff.timestamp())

    # Comprueba que cada paso histórico solo muestra datos cerrados hasta ese instante.
    def test_replay_is_sequential(self) -> None:
        repository = CsvMarketDataRepository(Path("data/raw"))
        identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "csv")
        replay = HistoricalReplay()
        steps = tuple(
            replay.steps(
                repository,
                identity,
                "M5",
                datetime(2026, 10, 30, 19, tzinfo=UTC),
                datetime(2026, 10, 30, 20, tzinfo=UTC),
            )
        )
        self.assertTrue(steps)
        self.assertTrue(
            all(
                step.closed_bars[-1].open_time_utc.timestamp() + 300 <= step.cutoff_utc.timestamp()
                for step in steps
            )
        )

    # Conserva los mismos pasos que el recorrido de referencia tras optimizar el replay incremental.
    def test_incremental_replay_matches_reference_steps(self) -> None:
        repository = CsvMarketDataRepository(Path("data/raw"))
        identity = InstrumentIdentity("Exness", "Exness Technologies Ltd", "XAUUSDm", "csv")
        start = datetime(2026, 10, 30, 19, tzinfo=UTC)
        end = datetime(2026, 10, 30, 20, tzinfo=UTC)
        actual = tuple(HistoricalReplay().steps(repository, identity, "M5", start, end, 3))
        bars = repository.closed_bars(identity, "M5")
        expected = tuple(
            (
                bar.open_time_utc + timedelta(minutes=5),
                tuple(
                    item
                    for item in bars
                    if item.open_time_utc + timedelta(minutes=5)
                    <= bar.open_time_utc + timedelta(minutes=5)
                )[-3:],
            )
            for bar in bars
            if start <= bar.open_time_utc + timedelta(minutes=5) <= end
        )

        self.assertEqual(
            tuple((step.cutoff_utc, step.closed_bars) for step in actual),
            expected,
        )

    # Rechaza análisis que pretendan deducir estructura sin contexto suficiente.
    def test_technical_runner_rejects_insufficient_history(self) -> None:
        with self.assertRaises(InsufficientHistoricalDataError):
            HistoricalTechnicalRunner().run(
                "M5",
                Path("data/raw/m5/XAUUSDm_20260810_20261109.csv"),
                rules_for_timeframe("M5"),
                datetime(2026, 8, 10, 1, tzinfo=UTC),
            )
