from __future__ import annotations

from datetime import UTC, datetime

from xau_collector.config import AppSettings
from xau_collector.domain.models import DiscoveryReport
from xau_collector.ports.market_data import MarketDataGateway
from xau_collector.services.history_probe import HistoryProbeService
from xau_collector.services.symbol_resolver import SymbolResolver


# Coordina una exploración de terminal, símbolo, cotización e historial disponible.
class DiscoveryService:
    # Recibe servicios desacoplados para consultar datos y resolver el símbolo objetivo.
    def __init__(
        self,
        gateway: MarketDataGateway,
        resolver: SymbolResolver,
        history_probe: HistoryProbeService,
    ) -> None:
        self._gateway = gateway
        self._resolver = resolver
        self._history_probe = history_probe

    # Ejecuta la exploración y garantiza el cierre de la conexión al terminar.
    def run(self, settings: AppSettings) -> DiscoveryReport:
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(),
                settings.symbol.logical_name,
                settings.symbol.aliases,
                settings.symbol.real_name,
            )
            self._gateway.select_symbol(symbol.name)
            return DiscoveryReport(
                generated_at_utc=datetime.now(UTC),
                terminal_version=self._gateway.terminal_version(),
                broker_server=self._gateway.broker_server(),
                symbol=symbol,
                latest_tick=self._gateway.latest_tick(symbol.name),
                recent_rates=self._gateway.recent_rates(
                    symbol.name,
                    settings.discovery.timeframe,
                    settings.discovery.recent_bars,
                ),
                m1_history=self._history_probe.probe_m1(
                    self._gateway, symbol.name, settings.discovery
                ),
                tick_history=(
                    self._history_probe.probe_ticks(self._gateway, symbol.name, settings.discovery)
                    if settings.discovery.probe_tick_history
                    else None
                ),
            )
        finally:
            self._gateway.close()
