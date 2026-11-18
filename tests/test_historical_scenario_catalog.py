from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.services.historical_scenario_catalog import HistoricalScenarioCatalog, _category


# Verifica que cortes históricos puedan clasificarse sin usar MT5 en vivo.
class HistoricalScenarioCatalogTests(unittest.TestCase):
    # Clasifica varios instantes históricos en categorías técnicas explicables.
    def test_classifies_historical_cutoffs(self) -> None:
        scenarios = HistoricalScenarioCatalog().evaluate(
            Path("data/raw"),
            (
                datetime(2026, 8, 20, 20, tzinfo=UTC),
                datetime(2026, 9, 30, 20, tzinfo=UTC),
                datetime(2026, 10, 30, 20, tzinfo=UTC),
            ),
        )
        self.assertEqual(len(scenarios), 3)
        self.assertTrue(
            all(
                item.category
                in (
                    "CONTEXTO_NO_ALINEADO",
                    "POI_INVALIDADO",
                    "CONFIRMACION_M15",
                    "ESPERANDO_CONFIRMACION",
                )
                for item in scenarios
            )
        )

    # Clasifica cada estado de validación sin depender de que ocurra hoy en el histórico.
    def test_classifies_all_scenario_categories(self) -> None:
        self.assertEqual(_category("NEUTRAL", "CONFIRMADO"), "CONTEXTO_NO_ALINEADO")
        self.assertEqual(_category("ALINEADO_ALCISTA", "INVALIDADO"), "POI_INVALIDADO")
        self.assertEqual(_category("ALINEADO_BAJISTA", "CONFIRMADO"), "CONFIRMACION_M15")
        self.assertEqual(
            _category("ALINEADO_ALCISTA", "ESPERANDO_RETESTEO"), "ESPERANDO_CONFIRMACION"
        )


if __name__ == "__main__":
    unittest.main()
