from __future__ import annotations

import unittest
from datetime import UTC, datetime
from json import dumps

from xau_collector.config import (
    AppSettings,
    DiscoverySettings,
    Mt5Settings,
    OutputSettings,
    StorageSettings,
    SymbolSettings,
)
from xau_collector.domain.models import (
    MarketTick,
    RatesCoverage,
    SymbolDescriptor,
    TimeRangeCoverage,
)
from xau_collector.services.discovery import DiscoveryService
from xau_collector.services.history_probe import HistoryProbeService
from xau_collector.services.symbol_resolver import SymbolResolver


# Proporciona datos controlados para probar la coordinación de descubrimiento.
class FakeGateway:
    # Inicializa indicadores para comprobar apertura y cierre de la fuente.
    def __init__(self) -> None:
        self.connected = False
        self.closed = False

    # Registra que el servicio inició su conexión.
    def connect(self) -> None:
        self.connected = True

    # Registra que el servicio cerró la conexión incluso tras terminar su trabajo.
    def close(self) -> None:
        self.closed = True

    # Devuelve una versión estable para incluirla en el reporte de descubrimiento.
    def terminal_version(self) -> str:
        return "5.0.test"

    # Devuelve un servidor conocido para validar la procedencia del reporte.
    def broker_server(self) -> str:
        return "DemoBroker"

    # Devuelve un único símbolo válido para resolver el activo de prueba.
    def list_symbols(self) -> tuple[SymbolDescriptor, ...]:
        return (SymbolDescriptor("XAUUSDm", "Gold", "Metals", 2, 0.01, "XAU", "USD", 100, True),)

    # Conserva el símbolo seleccionado para comprobar la coordinación del servicio.
    def select_symbol(self, symbol_name: str) -> None:
        self.selected = symbol_name

    # Devuelve un tick estable para serializar el reporte sin consultar MT5.
    def latest_tick(self, symbol_name: str) -> MarketTick:
        return MarketTick(1_700_000_000_000, 2000.0, 2000.2, 0.0)

    # Devuelve cobertura reciente controlada para el reporte de descubrimiento.
    def recent_rates(self, symbol_name: str, timeframe: str, count: int) -> RatesCoverage:
        now = datetime.now(UTC)
        return RatesCoverage(timeframe, count, count, now, now)

    # Devuelve cobertura M1 controlada para cada ventana de sondeo.
    def rates_in_range(
        self, symbol_name: str, timeframe: str, start_utc: datetime, end_utc: datetime
    ) -> TimeRangeCoverage:
        return TimeRangeCoverage("M1", start_utc, end_utc, 60, start_utc, end_utc)

    # Devuelve cobertura de ticks controlada para cada ventana de sondeo.
    def ticks_in_range(
        self, symbol_name: str, start_utc: datetime, end_utc: datetime
    ) -> TimeRangeCoverage:
        return TimeRangeCoverage("ticks", start_utc, end_utc, 100, start_utc, end_utc)


# Verifica que el descubrimiento combine datos y cierre la fuente correctamente.
class DiscoveryServiceTests(unittest.TestCase):
    # Comprueba el recorrido exitoso completo usando una fuente de datos controlada.
    def test_gateway_is_closed_after_success(self) -> None:
        gateway = FakeGateway()
        settings = AppSettings(
            Mt5Settings(None, 60_000),
            SymbolSettings("XAUUSD", ("XAUUSD", "GOLD"), None),
            DiscoverySettings(100, "M1", (7, 30), 4, False),
            OutputSettings(__import__("pathlib").Path("reports")),
            StorageSettings(__import__("pathlib").Path("data/raw/m1")),
        )
        report = DiscoveryService(gateway, SymbolResolver(), HistoryProbeService()).run(settings)

        self.assertEqual(report.symbol.name, "XAUUSDm")
        self.assertTrue(gateway.connected)
        self.assertTrue(gateway.closed)
        self.assertEqual(report.m1_history.probes_with_data, 2)
        self.assertIsNone(report.tick_history)
        serialized = report.to_dict()
        self.assertIsInstance(serialized["m1_history"]["probes"], list)
        self.assertEqual(serialized["m1_history"]["probes"][0]["out_of_range_count"], 0)
        dumps(serialized)


if __name__ == "__main__":
    unittest.main()
