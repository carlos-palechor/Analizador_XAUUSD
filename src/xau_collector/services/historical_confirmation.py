from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.ports.market_repository import MarketDataRepository
from xau_collector.services.technical_structure import (
    PointOfInterest,
    PriceBar,
    _candidate_poi,
    _latest_body_break,
    _m5_conditions,
    _m15_confirmation,
    _m15_confirmation_time,
    _swing_highs,
    _swing_lows,
)


# Resume confirmación POI H1, M15 y M5 desde históricos locales.
@dataclass(frozen=True, slots=True)
class HistoricalConfirmation:
    m15_state: str
    poi_direction: str | None
    m15_confirmed_at_utc: datetime | None
    m5_sweep: bool
    m5_sweep_at_utc: datetime | None
    m5_reaction: bool
    m5_reaction_at_utc: datetime | None
    m5_body_break: bool
    m5_body_break_at_utc: datetime | None


# Evalúa la secuencia técnica usando velas locales anteriores a un corte.
class HistoricalConfirmationRunner:
    # Lee H1, M15 y M5 y devuelve estados sin conexión MT5.
    def run(
        self,
        repository: MarketDataRepository,
        identity: InstrumentIdentity,
        cutoff_utc: datetime | None = None,
    ) -> HistoricalConfirmation:
        h1 = repository.closed_bars(identity, "H1", cutoff_utc, 360)
        m15 = repository.closed_bars(identity, "M15", cutoff_utc, 480)
        m5 = repository.closed_bars(identity, "M5", cutoff_utc, 576)
        highs, lows = _swing_highs(h1, 2), _swing_lows(h1, 2)
        poi = _candidate_poi(_latest_body_break(highs, lows, h1), h1)
        state, interaction = _m15_confirmation(poi, m15)
        confirmed_at = _m15_confirmation_time(poi, m15, state, interaction)
        relevant_m5 = (
            tuple(
                bar
                for bar in m5
                if confirmed_at is not None and bar.open_time_utc >= confirmed_at
            )
            if poi is not None
            else ()
        )
        sweep, reaction, body_break = (
            _m5_conditions(poi, relevant_m5) if poi else (False, False, False)
        )
        sweep_at, reaction_at, body_break_at = _m5_event_times(poi, relevant_m5)
        return HistoricalConfirmation(
            state.value,
            poi.direction if poi else None,
            confirmed_at,
            sweep,
            sweep_at,
            reaction,
            reaction_at,
            body_break,
            body_break_at,
        )


# Determina la primera vela cerrada que hizo visible cada evento M5, sin mirar velas futuras.
def _m5_event_times(
    poi: PointOfInterest | None, bars: Sequence[PriceBar]
) -> tuple[datetime | None, datetime | None, datetime | None]:
    if poi is None:
        return None, None, None
    sweep_at = reaction_at = body_break_at = None
    for index, bar in enumerate(bars, start=1):
        sweep, reaction, body_break = _m5_conditions(poi, bars[:index])
        if sweep and sweep_at is None:
            sweep_at = bar.open_time_utc
        if reaction and reaction_at is None:
            reaction_at = bar.open_time_utc
        if body_break and body_break_at is None:
            body_break_at = bar.open_time_utc
    return sweep_at, reaction_at, body_break_at
