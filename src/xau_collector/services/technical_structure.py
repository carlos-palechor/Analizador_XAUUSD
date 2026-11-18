from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from xau_collector.domain.models import M1Bar, MarketTick, SymbolDescriptor
from xau_collector.ports.market_data import MarketDataGateway
from xau_collector.services.symbol_resolver import SymbolResolver
from xau_collector.services.technical_pivots import StructuralPivot
from xau_collector.services.technical_pivots import swing_highs as _swing_highs
from xau_collector.services.technical_pivots import swing_lows as _swing_lows
from xau_collector.services.technical_structure_types import (
    M5ObservationState,
    MacroDirection,
    PoiConfirmationState,
    PointOfInterest,
    PriceBar,
    StructureBreak,
)


# Agrupa el contexto H4 explicable sin sugerir una operación.
@dataclass(frozen=True, slots=True)
class H4StructureReport:
    engine_id: str
    engine_version: str
    symbol: str
    calculated_at_utc: datetime
    market_timestamp_utc: datetime
    direction: MacroDirection
    closed_bar_count: int
    pivot_radius: int
    swing_highs: tuple[StructuralPivot, ...]
    swing_lows: tuple[StructuralPivot, ...]
    explanation: tuple[str, ...]

    # Convierte el reporte H4 en valores compatibles con un reporte JSON.
    def to_dict(self) -> dict[str, Any]:
        return _serialize_datetimes(asdict(self))


# Agrupa liquidez pendiente y la última ruptura de estructura detectada en H1.
@dataclass(frozen=True, slots=True)
class H1StructureReport:
    engine_id: str
    engine_version: str
    symbol: str
    calculated_at_utc: datetime
    market_timestamp_utc: datetime
    closed_bar_count: int
    pivot_radius: int
    resting_buy_side_liquidity: tuple[StructuralPivot, ...]
    resting_sell_side_liquidity: tuple[StructuralPivot, ...]
    latest_body_break: StructureBreak | None
    candidate_poi: PointOfInterest | None
    explanation: tuple[str, ...]

    # Convierte el mapa H1 en valores compatibles con un reporte JSON.
    def to_dict(self) -> dict[str, Any]:
        return _serialize_datetimes(asdict(self))


# Resume cómo M15 interactuó con un POI H1, sin producir una orden de entrada.
@dataclass(frozen=True, slots=True)
class M15PoiConfirmationReport:
    engine_id: str
    engine_version: str
    symbol: str
    calculated_at_utc: datetime
    market_timestamp_utc: datetime
    poi: PointOfInterest | None
    state: PoiConfirmationState
    closed_bar_count: int
    last_interaction_utc: datetime | None
    confirmed_at_utc: datetime | None
    explanation: tuple[str, ...]

    # Convierte la confirmación M15 en valores compatibles con un reporte JSON.
    def to_dict(self) -> dict[str, Any]:
        return _serialize_datetimes(asdict(self))


# Resume la reacción M5 sin convertirla en una orden de compra o venta.
@dataclass(frozen=True, slots=True)
class M5ObservationReport:
    engine_id: str
    engine_version: str
    symbol: str
    calculated_at_utc: datetime
    m15_state: PoiConfirmationState
    state: M5ObservationState
    closed_bar_count: int
    sweep_detected: bool
    reaction_detected: bool
    body_break_detected: bool
    explanation: tuple[str, ...]

    # Convierte la observación M5 en valores compatibles con un reporte JSON.
    def to_dict(self) -> dict[str, Any]:
        return _serialize_datetimes(asdict(self))


# Aísla las lecturas de mercado que requiere el cerebro técnico.
class StructureGateway(Protocol):
    # Abre una sesión con la fuente de datos.
    def connect(self) -> None: ...

    # Cierra la sesión con la fuente de datos.
    def close(self) -> None: ...

    # Lista los símbolos disponibles para resolver el activo configurado.
    def list_symbols(self) -> Sequence[SymbolDescriptor]: ...

    # Activa un símbolo antes de consultar precios.
    def select_symbol(self, symbol_name: str) -> None: ...

    # Devuelve el último tick disponible.
    def latest_tick(self, symbol_name: str) -> MarketTick: ...

    # Devuelve velas de la temporalidad solicitada en un intervalo UTC.
    def bars_in_range(
        self, symbol_name: str, timeframe: str, start_utc: datetime, end_utc: datetime
    ) -> Sequence[M1Bar]: ...


# Detecta pivotes H4 y determina el contexto macro a partir de ellos.
class H4StructureBrain:
    # Guarda las dependencias y límites de lectura sin persistir datos de mercado.
    def __init__(
        self,
        gateway: MarketDataGateway,
        resolver: SymbolResolver,
        pivot_radius: int = 2,
        lookback_bars: int = 180,
    ) -> None:
        if pivot_radius < 1:
            raise ValueError("pivot_radius debe ser al menos 1")
        if lookback_bars <= pivot_radius * 2:
            raise ValueError("lookback_bars debe superar el doble de pivot_radius")
        self._gateway = gateway
        self._resolver = resolver
        self._pivot_radius = pivot_radius
        self._lookback_bars = lookback_bars

    # Analiza velas H4 cerradas y devuelve dirección macro con sus pivotes de respaldo.
    def run(
        self, logical_name: str, aliases: tuple[str, ...], real_name: str | None
    ) -> H4StructureReport:
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(), logical_name, aliases, real_name
            )
            self._gateway.select_symbol(symbol.name)
            tick = self._gateway.latest_tick(symbol.name)
            market_time = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
            bars = self._gateway.bars_in_range(
                symbol.name,
                "H4",
                market_time - timedelta(hours=self._lookback_bars * 4 + 4),
                market_time,
            )
            closed_bars = _closed_bars(bars, market_time, timedelta(hours=4))[
                -self._lookback_bars :
            ]
            highs = _swing_highs(closed_bars, self._pivot_radius)
            lows = _swing_lows(closed_bars, self._pivot_radius)
            direction = _macro_direction(highs, lows)
            return H4StructureReport(
                engine_id="estructura_tecnica_h4",
                engine_version="0.1.0",
                symbol=symbol.name,
                calculated_at_utc=datetime.now(UTC),
                market_timestamp_utc=market_time,
                direction=direction,
                closed_bar_count=len(closed_bars),
                pivot_radius=self._pivot_radius,
                swing_highs=tuple(highs),
                swing_lows=tuple(lows),
                explanation=_explanation(direction, highs, lows),
            )
        finally:
            self._gateway.close()


# Construye el mapa H1 de liquidez y BOS sin decidir POI ni emitir una entrada.
class H1StructureBrain:
    # Guarda dependencias y límites para analizar H1 únicamente en memoria.
    def __init__(
        self,
        gateway: MarketDataGateway,
        resolver: SymbolResolver,
        pivot_radius: int = 2,
        lookback_bars: int = 360,
    ) -> None:
        if pivot_radius < 1:
            raise ValueError("pivot_radius debe ser al menos 1")
        if lookback_bars <= pivot_radius * 2:
            raise ValueError("lookback_bars debe superar el doble de pivot_radius")
        self._gateway = gateway
        self._resolver = resolver
        self._pivot_radius = pivot_radius
        self._lookback_bars = lookback_bars

    # Detecta liquidez H1 pendiente y la última ruptura confirmada por cierre de vela.
    def run(
        self, logical_name: str, aliases: tuple[str, ...], real_name: str | None
    ) -> H1StructureReport:
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(), logical_name, aliases, real_name
            )
            self._gateway.select_symbol(symbol.name)
            tick = self._gateway.latest_tick(symbol.name)
            market_time = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
            bars = self._gateway.bars_in_range(
                symbol.name,
                "H1",
                market_time - timedelta(hours=self._lookback_bars + 1),
                market_time,
            )
            closed_bars = _closed_bars(bars, market_time, timedelta(hours=1))[
                -self._lookback_bars :
            ]
            highs = _swing_highs(closed_bars, self._pivot_radius)
            lows = _swing_lows(closed_bars, self._pivot_radius)
            buy_side = _resting_liquidity(highs, closed_bars, "HIGH")
            sell_side = _resting_liquidity(lows, closed_bars, "LOW")
            latest_break = _latest_body_break(highs, lows, closed_bars)
            candidate_poi = _candidate_poi(latest_break, closed_bars)
            return H1StructureReport(
                engine_id="estructura_tecnica_h1",
                engine_version="0.1.0",
                symbol=symbol.name,
                calculated_at_utc=datetime.now(UTC),
                market_timestamp_utc=market_time,
                closed_bar_count=len(closed_bars),
                pivot_radius=self._pivot_radius,
                resting_buy_side_liquidity=tuple(buy_side),
                resting_sell_side_liquidity=tuple(sell_side),
                latest_body_break=latest_break,
                candidate_poi=candidate_poi,
                explanation=_h1_explanation(buy_side, sell_side, latest_break, candidate_poi),
            )
        finally:
            self._gateway.close()


# Confirma en M15 si el precio retestea, reacciona o invalida el POI H1 más reciente.
class M15PoiConfirmationBrain:
    # Reutiliza el mapa H1 y conserva dependencias para una lectura M15 sin persistencia.
    def __init__(
        self,
        gateway: MarketDataGateway,
        resolver: SymbolResolver,
        h1_brain: H1StructureBrain,
        lookback_bars: int = 192,
    ) -> None:
        if lookback_bars <= 0:
            raise ValueError("lookback_bars debe ser mayor que cero")
        self._gateway = gateway
        self._resolver = resolver
        self._h1_brain = h1_brain
        self._lookback_bars = lookback_bars

    # Evalúa M15 contra el último POI H1 y devuelve solamente su estado de confirmación.
    def run(
        self, logical_name: str, aliases: tuple[str, ...], real_name: str | None
    ) -> M15PoiConfirmationReport:
        h1_report = self._h1_brain.run(logical_name, aliases, real_name)
        poi = h1_report.candidate_poi
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(), logical_name, aliases, real_name
            )
            self._gateway.select_symbol(symbol.name)
            tick = self._gateway.latest_tick(symbol.name)
            market_time = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
            bars = self._gateway.bars_in_range(
                symbol.name,
                "M15",
                market_time - timedelta(minutes=self._lookback_bars * 15 + 15),
                market_time,
            )
            closed_bars = _closed_bars(bars, market_time, timedelta(minutes=15))[
                -self._lookback_bars :
            ]
            state, interaction = _m15_confirmation(poi, closed_bars)
            confirmed_at = _m15_confirmation_time(poi, closed_bars, state, interaction)
            return M15PoiConfirmationReport(
                engine_id="confirmacion_poi_m15",
                engine_version="0.1.0",
                symbol=symbol.name,
                calculated_at_utc=datetime.now(UTC),
                market_timestamp_utc=market_time,
                poi=poi,
                state=state,
                closed_bar_count=len(closed_bars),
                last_interaction_utc=interaction.open_time_utc if interaction else None,
                confirmed_at_utc=confirmed_at,
                explanation=_m15_explanation(poi, state, interaction),
            )
        finally:
            self._gateway.close()


# Excluye la vela H4 en formación para no confirmar una estructura que aún puede cambiar.
# Protege la observación M5: sin confirmación M15 no analiza ni propone una entrada.
class M5ReactionBrain:
    # Conserva la confirmación M15 como requisito previo para cualquier setup M5.
    def __init__(
        self,
        gateway: MarketDataGateway,
        resolver: SymbolResolver,
        m15_brain: M15PoiConfirmationBrain,
    ) -> None:
        self._gateway = gateway
        self._resolver = resolver
        self._m15_brain = m15_brain

    # Devuelve un bloqueo o habilita la siguiente fase de reacción M5 en memoria.
    def run(
        self, logical_name: str, aliases: tuple[str, ...], real_name: str | None
    ) -> M5ObservationReport:
        confirmation = self._m15_brain.run(logical_name, aliases, real_name)
        state = _m5_gate(confirmation.state)
        if state is M5ObservationState.BLOCKED_BY_M15:
            return M5ObservationReport(
                "observacion_reaccion_m5",
                "0.1.0",
                confirmation.symbol,
                datetime.now(UTC),
                confirmation.state,
                state,
                0,
                False,
                False,
                False,
                _m5_explanation(confirmation.state, state),
            )
        poi = confirmation.poi
        self._gateway.connect()
        try:
            self._gateway.select_symbol(confirmation.symbol)
            tick = self._gateway.latest_tick(confirmation.symbol)
            market_time = datetime.fromtimestamp(tick.time_msc / 1000, tz=UTC)
            bars = _closed_bars(
                self._gateway.bars_in_range(
                    confirmation.symbol, "M5", market_time - timedelta(hours=8), market_time
                ),
                market_time,
                timedelta(minutes=5),
            )
            relevant_bars = tuple(
                bar
                for bar in bars
                if confirmation.confirmed_at_utc is not None
                and bar.open_time_utc >= confirmation.confirmed_at_utc
            )
            sweep, reaction, body_break = _m5_conditions(poi, relevant_bars)
            state = _m5_setup_state(sweep, reaction, body_break)
            return M5ObservationReport(
                "observacion_reaccion_m5",
                "0.1.0",
                confirmation.symbol,
                datetime.now(UTC),
                confirmation.state,
                state,
                len(bars),
                sweep,
                reaction,
                body_break,
                _m5_explanation(confirmation.state, state),
            )
        finally:
            self._gateway.close()


def _closed_bars(
    bars: Sequence[PriceBar], market_time: datetime, timeframe: timedelta
) -> tuple[PriceBar, ...]:
    return tuple(bar for bar in bars if bar.open_time_utc + timeframe <= market_time)


# Determina la dirección solo cuando máximos y mínimos recientes coinciden estructuralmente.
def _macro_direction(
    swing_highs: Sequence[StructuralPivot], swing_lows: Sequence[StructuralPivot]
) -> MacroDirection:
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return MacroDirection.NEUTRAL
    high_before, high_last = swing_highs[-2:]
    low_before, low_last = swing_lows[-2:]
    if high_last.price > high_before.price and low_last.price > low_before.price:
        return MacroDirection.BULLISH
    if high_last.price < high_before.price and low_last.price < low_before.price:
        return MacroDirection.BEARISH
    return MacroDirection.NEUTRAL


# Conserva pivotes cuya mecha todavía no fue alcanzada por velas posteriores.
def _resting_liquidity(
    pivots: Sequence[StructuralPivot], bars: Sequence[PriceBar], kind: str
) -> list[StructuralPivot]:
    resting: list[StructuralPivot] = []
    for pivot in pivots:
        later_bars = (bar for bar in bars if bar.open_time_utc > pivot.open_time_utc)
        was_taken = (
            any(bar.high >= pivot.price for bar in later_bars)
            if kind == "HIGH"
            else any(bar.low <= pivot.price for bar in later_bars)
        )
        if not was_taken:
            resting.append(pivot)
    return resting


# Encuentra la última ruptura cuyo cierre supera un máximo o mínimo estructural anterior.
def _latest_body_break(
    swing_highs: Sequence[StructuralPivot],
    swing_lows: Sequence[StructuralPivot],
    bars: Sequence[PriceBar],
) -> StructureBreak | None:
    breaks: list[StructureBreak] = []
    for pivot in swing_highs:
        for bar in bars:
            if bar.open_time_utc > pivot.open_time_utc and bar.close > pivot.price:
                breaks.append(StructureBreak("ALCISTA", pivot, bar.open_time_utc, bar.close))
                break
    for pivot in swing_lows:
        for bar in bars:
            if bar.open_time_utc > pivot.open_time_utc and bar.close < pivot.price:
                breaks.append(StructureBreak("BAJISTA", pivot, bar.open_time_utc, bar.close))
                break
    return max(breaks, key=lambda item: item.confirmed_at_utc, default=None)


# Extrae la última vela contraria entre el pivote roto y el BOS para formar un POI candidato.
def _candidate_poi(
    structure_break: StructureBreak | None, bars: Sequence[PriceBar]
) -> PointOfInterest | None:
    if structure_break is None:
        return None
    direction = structure_break.direction
    candidates = (
        bar
        for bar in bars
        if structure_break.broken_pivot.open_time_utc
        < bar.open_time_utc
        < structure_break.confirmed_at_utc
        and _is_opposite_candle(bar, direction)
    )
    source = max(candidates, key=lambda bar: bar.open_time_utc, default=None)
    if source is None:
        return None
    return PointOfInterest(
        kind="ORIGEN_IMPULSO",
        direction=direction,
        low=source.low,
        high=source.high,
        source_open_time_utc=source.open_time_utc,
        confirmed_by=structure_break,
    )


# Indica si una vela tiene dirección opuesta al BOS que posteriormente fue confirmado.
def _is_opposite_candle(bar: PriceBar, break_direction: str) -> bool:
    return bar.close < bar.open if break_direction == "ALCISTA" else bar.close > bar.open


# Determina el estado M15 al observar el último retesteo y sus cierres posteriores.
def _m15_confirmation(
    poi: PointOfInterest | None, bars: Sequence[PriceBar]
) -> tuple[PoiConfirmationState, PriceBar | None]:
    if poi is None:
        return PoiConfirmationState.NO_POI, None
    relevant = tuple(bar for bar in bars if bar.open_time_utc >= poi.confirmed_by.confirmed_at_utc)
    interactions = tuple(bar for bar in relevant if bar.low <= poi.high and bar.high >= poi.low)
    last_interaction = interactions[-1] if interactions else None
    if poi.direction == "ALCISTA":
        if any(bar.close < poi.low for bar in relevant):
            return PoiConfirmationState.INVALIDATED, last_interaction
        if last_interaction is None:
            return PoiConfirmationState.WAITING_FOR_RETEST, None
        after_interaction = tuple(
            bar for bar in relevant if bar.open_time_utc >= last_interaction.open_time_utc
        )
        if any(bar.close > poi.high and bar.close > bar.open for bar in after_interaction):
            return PoiConfirmationState.CONFIRMED, last_interaction
        return PoiConfirmationState.WAITING_FOR_REACTION, last_interaction
    if any(bar.close > poi.high for bar in relevant):
        return PoiConfirmationState.INVALIDATED, last_interaction
    if last_interaction is None:
        return PoiConfirmationState.WAITING_FOR_RETEST, None
    after_interaction = tuple(
        bar for bar in relevant if bar.open_time_utc >= last_interaction.open_time_utc
    )
    if any(bar.close < poi.low and bar.close < bar.open for bar in after_interaction):
        return PoiConfirmationState.CONFIRMED, last_interaction
    return PoiConfirmationState.WAITING_FOR_REACTION, last_interaction


# Devuelve la apertura de la vela M15 que confirmó un POI después de su interacción.
def _m15_confirmation_time(
    poi: PointOfInterest | None,
    bars: Sequence[PriceBar],
    state: PoiConfirmationState,
    interaction: PriceBar | None,
) -> datetime | None:
    if poi is None or interaction is None or state is not PoiConfirmationState.CONFIRMED:
        return None
    candidates = tuple(bar for bar in bars if bar.open_time_utc >= interaction.open_time_utc)
    if poi.direction == "ALCISTA":
        confirmed = next(
            (bar for bar in candidates if bar.close > poi.high and bar.close > bar.open),
            None,
        )
    else:
        confirmed = next(
            (bar for bar in candidates if bar.close < poi.low and bar.close < bar.open),
            None,
        )
    return confirmed.open_time_utc if confirmed else None


# Explica el estado M15 sin convertir el resultado en una recomendación de trading.
def _m15_explanation(
    poi: PointOfInterest | None,
    state: PoiConfirmationState,
    interaction: PriceBar | None,
) -> tuple[str, ...]:
    if poi is None:
        return ("No existe POI H1 candidato que M15 pueda confirmar.",)
    if state is PoiConfirmationState.WAITING_FOR_RETEST:
        return ("El precio aún no retestea el POI H1 después del BOS.",)
    if state is PoiConfirmationState.INVALIDATED:
        return ("Un cierre M15 cruzó el límite de invalidación del POI H1.",)
    if state is PoiConfirmationState.CONFIRMED:
        return ("M15 reaccionó y cerró fuera del POI en la dirección del BOS H1.",)
    return (
        "M15 tocó el POI H1; falta cierre de reacción fuera de la zona.",
        f"Última interacción M15: {interaction.open_time_utc.isoformat()}." if interaction else "",
    )


# Explica qué liquidez sigue pendiente y si existe una ruptura H1 confirmada.
def _h1_explanation(
    buy_side: Sequence[StructuralPivot],
    sell_side: Sequence[StructuralPivot],
    latest_break: StructureBreak | None,
    candidate_poi: PointOfInterest | None,
) -> tuple[str, ...]:
    explanation = [
        f"Liquidez compradora pendiente: {len(buy_side)} máximos H1.",
        f"Liquidez vendedora pendiente: {len(sell_side)} mínimos H1.",
    ]
    if latest_break is None:
        explanation.append("No se detectó BOS H1 por cierre de cuerpo en la ventana analizada.")
    else:
        explanation.append(
            f"Último BOS H1 {latest_break.direction}: cierre {latest_break.close_price} "
            f"rompió {latest_break.broken_pivot.price}."
        )
    if candidate_poi is None:
        explanation.append("No hay POI candidato de origen de impulso para el último BOS.")
    else:
        explanation.append(
            f"POI candidato H1 {candidate_poi.direction}: "
            f"{candidate_poi.low} a {candidate_poi.high}."
        )
    return tuple(explanation)


# Redacta la evidencia mínima para que una persona pueda auditar la dirección devuelta.
def _explanation(
    direction: MacroDirection,
    swing_highs: Sequence[StructuralPivot],
    swing_lows: Sequence[StructuralPivot],
) -> tuple[str, ...]:
    if direction is MacroDirection.NEUTRAL:
        return ("No hay dos máximos y dos mínimos recientes alineados en la misma dirección.",)
    adjective = "ascendentes" if direction is MacroDirection.BULLISH else "descendentes"
    return (
        f"Los dos últimos máximos H4 son {adjective}.",
        f"Los dos últimos mínimos H4 son {adjective}.",
    )


# Convierte fechas anidadas en texto ISO-8601 para conservar reportes legibles.
def _serialize_datetimes(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_datetimes(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_datetimes(item) for item in value]
    return value


# Bloquea M5 hasta recibir una confirmación M15 del POI H1.
def _m5_gate(m15_state: PoiConfirmationState) -> M5ObservationState:
    return (
        M5ObservationState.WAITING_FOR_REACTION
        if m15_state is PoiConfirmationState.CONFIRMED
        else M5ObservationState.BLOCKED_BY_M15
    )


# Detecta barrido, reacción direccional y ruptura interna M5 para el POI confirmado.
def _m5_conditions(
    poi: PointOfInterest | None, bars: Sequence[PriceBar]
) -> tuple[bool, bool, bool]:
    if poi is None:
        return False, False, False
    highs = _swing_highs(bars, 1)
    lows = _swing_lows(bars, 1)
    if poi.direction == "ALCISTA":
        sweep = any(
            bar.open_time_utc > pivot.open_time_utc and bar.low < pivot.price < bar.close
            for pivot in lows
            for bar in bars
        )
        reaction = any(bar.close > poi.high and bar.close > bar.open for bar in bars)
        body_break = any(
            bar.open_time_utc > pivot.open_time_utc and bar.close > pivot.price
            for pivot in highs
            for bar in bars
        )
        return sweep, reaction, body_break
    sweep = any(
        bar.open_time_utc > pivot.open_time_utc and bar.high > pivot.price > bar.close
        for pivot in highs
        for bar in bars
    )
    reaction = any(bar.close < poi.low and bar.close < bar.open for bar in bars)
    body_break = any(
        bar.open_time_utc > pivot.open_time_utc and bar.close < pivot.price
        for pivot in lows
        for bar in bars
    )
    return sweep, reaction, body_break


# Clasifica el setup M5 sin recomendar una orden ni asignar tamaño de riesgo.
def _m5_setup_state(sweep: bool, reaction: bool, body_break: bool) -> M5ObservationState:
    if reaction and body_break:
        return M5ObservationState.PREFERRED_SETUP if sweep else M5ObservationState.STANDARD_SETUP
    return M5ObservationState.WAITING_FOR_REACTION


# Explica por qué M5 permanece bloqueado o queda listo para observar una reacción.
def _m5_explanation(m15_state: PoiConfirmationState, state: M5ObservationState) -> tuple[str, ...]:
    if state is M5ObservationState.BLOCKED_BY_M15:
        return (f"M5 bloqueado: M15 está en estado {m15_state.value}.",)
    if state is M5ObservationState.PREFERRED_SETUP:
        return ("M5 detectó barrido, reacción y ruptura: setup preferente observado.",)
    if state is M5ObservationState.STANDARD_SETUP:
        return ("M5 detectó reacción y ruptura sin barrido: setup estándar observado.",)
    return ("M15 confirmó el POI; M5 puede observar barrido, reacción y ruptura.",)
