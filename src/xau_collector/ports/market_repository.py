from __future__ import annotations

from datetime import datetime
from typing import Protocol

from xau_collector.domain.market import InstrumentIdentity, MarketDataSnapshot
from xau_collector.domain.models import M1Bar


# Define la lectura de velas cerradas sin revelar si proceden de CSV, PostgreSQL o MT5.
class MarketDataRepository(Protocol):
    # Devuelve solo velas completamente cerradas hasta el corte solicitado.
    def closed_bars(
        self,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[M1Bar, ...]: ...

    # Describe los datos usados para que una ejecución pueda reconstruirse después.
    def snapshot(
        self,
        identity: InstrumentIdentity,
        timeframe: str,
        cutoff_utc: datetime,
        limit: int | None = None,
    ) -> MarketDataSnapshot: ...
