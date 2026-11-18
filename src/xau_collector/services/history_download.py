from __future__ import annotations

from datetime import datetime
from pathlib import Path

from xau_collector.infrastructure.csv_store import CsvBarStore
from xau_collector.ports.market_data import MarketDataGateway


# Descarga un rango histórico y lo guarda con un manifiesto reutilizable.
class HistoryDownloadService:
    # Conserva la fuente MT5 y el almacenamiento CSV genérico.
    def __init__(self, gateway: MarketDataGateway, store: CsvBarStore) -> None:
        self._gateway = gateway
        self._store = store

    # Guarda velas de una temporalidad sin depender del seguimiento en vivo.
    def download(
        self, symbol: str, timeframe: str, start_utc: datetime, end_utc: datetime, root: Path
    ) -> Path:
        self._gateway.connect()
        try:
            self._gateway.select_symbol(symbol)
            bars = self._gateway.bars_in_range(symbol, timeframe, start_utc, end_utc)
            destination = (
                root / timeframe.lower() / f"{symbol}_{start_utc:%Y%m%d}_{end_utc:%Y%m%d}.csv"
            )
            digest = self._store.write(destination, bars)
            self._store.write_manifest(
                destination,
                {
                    "schema_version": 2,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "requested_start_utc": start_utc.isoformat(),
                    "requested_end_utc": end_utc.isoformat(),
                    "bar_count": len(bars),
                    "sha256": digest,
                    "quality": {},
                },
            )
            return destination
        finally:
            self._gateway.close()
