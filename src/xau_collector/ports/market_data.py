from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from xau_collector.domain.models import (
    M1Bar,
    MarketTick,
    RatesCoverage,
    SymbolDescriptor,
    TimeRangeCoverage,
)


# Define las operaciones de mercado que los servicios necesitan sin depender de MT5.
class MarketDataGateway(Protocol):
    # Establece una sesión con la fuente de datos.
    def connect(self) -> None: ...

    # Cierra la sesión abierta con la fuente de datos.
    def close(self) -> None: ...

    # Devuelve la versión del terminal o proveedor conectado.
    def terminal_version(self) -> str: ...

    # Devuelve el servidor o fuente que suministra los datos de la cuenta.
    def broker_server(self) -> str: ...

    # Lista los símbolos que puede consultar la fuente de datos.
    def list_symbols(self) -> Sequence[SymbolDescriptor]: ...

    # Activa un símbolo antes de solicitar cotizaciones o velas.
    def select_symbol(self, symbol_name: str) -> None: ...

    # Devuelve la última cotización conocida de un símbolo.
    def latest_tick(self, symbol_name: str) -> MarketTick: ...

    # Resume las velas recientes solicitadas para una temporalidad.
    def recent_rates(self, symbol_name: str, timeframe: str, count: int) -> RatesCoverage: ...

    # Resume la cobertura de velas devueltas en un intervalo temporal.
    def rates_in_range(
        self, symbol_name: str, timeframe: str, start_utc: datetime, end_utc: datetime
    ) -> TimeRangeCoverage: ...

    # Resume la cobertura de ticks devueltos en un intervalo temporal.
    def ticks_in_range(
        self, symbol_name: str, start_utc: datetime, end_utc: datetime
    ) -> TimeRangeCoverage: ...

    # Devuelve las velas de un intervalo para validación y almacenamiento local.
    def bars_in_range(
        self, symbol_name: str, timeframe: str, start_utc: datetime, end_utc: datetime
    ) -> Sequence[M1Bar]: ...
