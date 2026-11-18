from __future__ import annotations

from datetime import UTC, datetime, timedelta

from xau_collector.config import DiscoverySettings
from xau_collector.domain.models import HistoryAvailability, TimeRangeCoverage
from xau_collector.ports.market_data import MarketDataGateway


# Sondea ventanas históricas pequeñas para conocer disponibilidad sin descargar todo el historial.
class HistoryProbeService:
    """Samples bounded windows to measure availability without mass downloading."""

    # Sondea disponibilidad de velas M1 en las fechas configuradas.
    def probe_m1(
        self,
        gateway: MarketDataGateway,
        symbol_name: str,
        settings: DiscoverySettings,
        now_utc: datetime | None = None,
    ) -> HistoryAvailability:
        return self._probe("M1", gateway, symbol_name, settings, now_utc)

    # Sondea disponibilidad de ticks en las fechas configuradas.
    def probe_ticks(
        self,
        gateway: MarketDataGateway,
        symbol_name: str,
        settings: DiscoverySettings,
        now_utc: datetime | None = None,
    ) -> HistoryAvailability:
        return self._probe("ticks", gateway, symbol_name, settings, now_utc)

    # Ejecuta el sondeo común de M1 o ticks sobre ventanas temporales limitadas.
    def _probe(
        self,
        source: str,
        gateway: MarketDataGateway,
        symbol_name: str,
        settings: DiscoverySettings,
        now_utc: datetime | None,
    ) -> HistoryAvailability:
        reference = (now_utc or datetime.now(UTC)).astimezone(UTC)
        window = timedelta(hours=settings.history_probe_window_hours)
        probes: list[TimeRangeCoverage] = []
        for days in settings.history_probe_lookback_days:
            end = reference - timedelta(days=days)
            start = end - window
            if source == "M1":
                coverage = gateway.rates_in_range(symbol_name, "M1", start, end)
            else:
                coverage = gateway.ticks_in_range(symbol_name, start, end)
            probes.append(coverage)
        return HistoryAvailability(source=source, probes=tuple(probes))
