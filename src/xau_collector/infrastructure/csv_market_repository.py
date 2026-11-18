from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from xau_collector.domain.market import InstrumentIdentity, MarketDataSnapshot
from xau_collector.domain.models import M1Bar
from xau_collector.errors import ConfigurationError
from xau_collector.services.historical_import_validation import HistoricalCsvValidator
from xau_collector.services.historical_technical_runner import timeframe_duration


# Lee históricos CSV mediante el mismo contrato que usará PostgreSQL posteriormente.
class CsvMarketDataRepository:
    # Recibe una carpeta de históricos organizada por temporalidad, sin nombres rígidos.
    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    # Expone la raíz únicamente mientras servicios antiguos terminan de migrar al contrato.
    def root(self) -> Path:
        return self._root

    # Devuelve velas cerradas existentes en el corte histórico indicado.
    def closed_bars(
        self,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[M1Bar, ...]:
        bars = HistoricalCsvValidator().validate(
            self.source_for(identity.symbol, timeframe)
        ).accepted_bars
        if cutoff_utc is not None:
            duration = timeframe_duration(timeframe)
            bars = tuple(bar for bar in bars if bar.open_time_utc + duration <= cutoff_utc)
        return bars[-limit:] if limit is not None else bars

    # Crea un snapshot explícito del conjunto exacto de velas consultadas.
    def snapshot(
        self,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime,
        limit: int | None = None,
    ) -> MarketDataSnapshot:
        return MarketDataSnapshot(
            identity=identity,
            timeframe=timeframe,
            bars=self.closed_bars(identity, timeframe, cutoff_utc, limit),
            received_at_utc=datetime.now(UTC),
            data_cutoff_utc=cutoff_utc,
            source_reference=str(self.source_for(identity.symbol, timeframe)),
        )

    # Resuelve un único CSV por temporalidad y símbolo evitando nombres de archivo quemados.
    def source_for(self, symbol: str, timeframe: str) -> Path:
        folder = self._root / timeframe.lower()
        matches = tuple(folder.glob(f"{symbol}_*.csv"))
        if not matches:
            raise ConfigurationError(f"No existe histórico CSV para {symbol} {timeframe}: {folder}")
        if len(matches) > 1:
            raise ConfigurationError(
                f"Hay más de un histórico CSV para {symbol} {timeframe}; "
                "defina una fuente explícita"
            )
        return matches[0]
