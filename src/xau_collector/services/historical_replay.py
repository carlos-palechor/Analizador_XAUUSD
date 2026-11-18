from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.domain.models import M1Bar
from xau_collector.ports.market_repository import MarketDataRepository
from xau_collector.services.historical_technical_runner import timeframe_duration


# Representa un instante reproducible en el que el cerebro puede evaluar solo datos conocidos.
@dataclass(frozen=True, slots=True)
class ReplayStep:
    cutoff_utc: datetime
    timeframe: str
    closed_bars: tuple[M1Bar, ...]


# Entrega pasos cronológicos sin filtrar información futura hacia el cerebro técnico.
class HistoricalReplay:
    # Recorre cada cierre de vela dentro del intervalo solicitado.
    def steps(
        self,
        repository: MarketDataRepository,
        identity: InstrumentIdentity,
        timeframe: str,
        start_utc: datetime,
        end_utc: datetime,
        lookback_bars: int | None = None,
    ) -> Iterator[ReplayStep]:
        all_bars = repository.closed_bars(identity, timeframe)
        duration = timeframe_duration(timeframe)
        visible: list[M1Bar] = []
        for bar in all_bars:
            cutoff = bar.open_time_utc + duration
            visible.append(bar)
            if cutoff < start_utc or cutoff > end_utc:
                continue
            available = tuple(visible)
            if lookback_bars is not None:
                available = available[-lookback_bars:]
            yield ReplayStep(cutoff, timeframe, available)
