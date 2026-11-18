from __future__ import annotations

import os
import unittest
from pathlib import Path

from xau_collector.config import load_settings
from xau_collector.infrastructure.metatrader import MetaTraderGateway
from xau_collector.services.symbol_resolver import SymbolResolver


# Ejecuta comprobaciones de solo lectura contra la terminal MT5 real cuando se autoricen.
class MetaTraderIntegrationTests(unittest.TestCase):
    # Detiene la prueba si el usuario no autorizó explícitamente usar su terminal real.
    def setUp(self) -> None:
        if os.environ.get("RUN_MT5_INTEGRATION") != "1":
            self.skipTest("Defina RUN_MT5_INTEGRATION=1 para probar la terminal MT5 real.")
        self.settings = load_settings(Path("config.toml"))
        self.gateway = MetaTraderGateway(self.settings.mt5)

    # Comprueba conexión, símbolo y datos recientes sin enviar ninguna orden al bróker.
    def test_reads_xauusd_market_data_from_the_real_terminal(self) -> None:
        self.gateway.connect()
        try:
            symbol = SymbolResolver().resolve(
                self.gateway.list_symbols(),
                self.settings.symbol.logical_name,
                self.settings.symbol.aliases,
                self.settings.symbol.real_name,
            )
            self.gateway.select_symbol(symbol.name)
            tick = self.gateway.latest_tick(symbol.name)
            rates = self.gateway.recent_rates(
                symbol.name,
                self.settings.discovery.timeframe,
                self.settings.discovery.recent_bars,
            )
        finally:
            self.gateway.close()

        self.assertEqual(symbol.name, "XAUUSDm")
        self.assertGreater(tick.ask, 0)
        self.assertGreater(tick.bid, 0)
        self.assertGreater(tick.ask, tick.bid)
        self.assertGreater(rates.returned_count, 0)


if __name__ == "__main__":
    unittest.main()
