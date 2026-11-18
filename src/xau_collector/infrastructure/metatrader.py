# Pospone la evaluación de los tipos, evitando resolver sus referencias de inmediato.
from __future__ import annotations

# Importa datetime para manejar fechas y horas, y UTC para normalizarlas.
from datetime import UTC, datetime

# Permite indicar que una variable contiene un módulo de Python o None.
from types import ModuleType

# Permite manejar cualquier tipo de valor, incluidos objetos de MetaTrader 5 sin tipado.
from typing import Any

from xau_collector.config import Mt5Settings  # Configuración de conexión con MetaTrader 5
from xau_collector.domain.models import (
    M1Bar,  # Representar una vela de un minuto
    MarketTick,  # Representar datos de un tick
    RatesCoverage,  # Resumir disponibilidad de velas recientes
    SymbolDescriptor,  # Representar información de un instrumento financiero
    TimeRangeCoverage,  # Resumir cobertura de datos en un intervalo
)

# ConnectionFailureError=Representar un fallo al comunicarse con MT5
# DependencyUnavailableError=Señalar que falta una dependencia necesaria
from xau_collector.errors import ConnectionFailureError, DependencyUnavailableError


# Carga MetaTrader 5 o lanza un error personalizado conservando su causa.
def _load_mt5() -> ModuleType:
    try:
        import MetaTrader5 as mt5
    except ImportError as exc:
        raise DependencyUnavailableError(
            "El paquete MetaTrader5 no está instalado. Ejecute la instalación del extra mt5."
        ) from exc
    return mt5


# Convierte una marca de tiempo Unix expresada en segundos en una fecha UTC.
def datetime_from_epoch_seconds(seconds: int) -> datetime:
    return datetime.fromtimestamp(int(seconds), tz=UTC)


# Convierte segundos Unix en una fecha y hora UTC.
def utc_datetime_from_epoch_milliseconds(milliseconds: int) -> datetime:
    return datetime.fromtimestamp(int(milliseconds) / 1000, tz=UTC)


# Implementa el contrato de datos de mercado mediante el paquete oficial de MT5.
class MetaTraderGateway:
    # Inicializa configuración y deja MT5 en None hasta establecer la conexión.
    def __init__(self, settings: Mt5Settings) -> None:
        self._settings = settings
        self._mt5: ModuleType | None = None

    # Inicializa MetaTrader 5, verifica la conexión con el bróker y gestiona posibles errores.
    def connect(self) -> None:
        mt5 = _load_mt5()
        initialize_params: dict[str, Any] = {"timeout": self._settings.initialize_timeout_ms}
        if self._settings.terminal_path:
            initialize_params["path"] = self._settings.terminal_path
        if not mt5.initialize(**initialize_params):
            raise ConnectionFailureError(f"MT5 initialize falló: {mt5.last_error()}")
        terminal = mt5.terminal_info()
        if terminal is None or not terminal.connected:
            mt5.shutdown()
            raise ConnectionFailureError("MetaTrader 5 no está conectado al servidor del bróker")
        self._mt5 = mt5

    # Cierra la conexión con MetaTrader 5 y limpia su referencia si existe.
    def close(self) -> None:
        if self._mt5 is not None:
            self._mt5.shutdown()
            self._mt5 = None

    # Verifica la conexión con MetaTrader 5 antes de permitir su uso.
    def _get_mt5_api(self) -> ModuleType:
        if self._mt5 is None:
            raise ConnectionFailureError("La conexión con MetaTrader 5 no está inicializada")
        return self._mt5

    # Consulta y devuelve la versión de MetaTrader 5 en formato de texto separado por puntos.
    def terminal_version(self) -> str:
        version = self._get_mt5_api().version()
        return ".".join(str(part) for part in version) if version else "UNKNOWN"

    # Obtiene el servidor real de la cuenta para registrar la fuente de datos.
    def broker_server(self) -> str:
        account = self._get_mt5_api().account_info()
        return str(getattr(account, "server", "UNKNOWN")) if account is not None else "UNKNOWN"

    # Obtiene símbolos de MT5 y los devuelve como una tupla de SymbolDescriptor.
    def list_symbols(self) -> tuple[SymbolDescriptor, ...]:
        api = self._get_mt5_api()
        symbols = api.symbols_get()
        if symbols is None:
            raise ConnectionFailureError(f"symbols_get falló: {api.last_error()}")
        return tuple(self._to_symbol_descriptor(symbol) for symbol in symbols)

    # Convierte símbolos de MT5 en SymbolDescriptor sin acceder al estado de la instancia.
    @staticmethod
    def _to_symbol_descriptor(symbol: Any) -> SymbolDescriptor:
        return SymbolDescriptor(
            name=str(symbol.name),
            description=str(symbol.description),
            path=str(symbol.path),
            digits=int(symbol.digits),
            point=float(symbol.point),
            currency_base=str(symbol.currency_base),
            currency_profit=str(symbol.currency_profit),
            contract_size=float(symbol.trade_contract_size),
            visible=bool(symbol.visible),
        )

    # Selecciona un símbolo en MetaTrader 5 para habilitarlo en Market Watch.
    def select_symbol(self, symbol_name: str) -> None:
        api = self._get_mt5_api()
        if not api.symbol_select(symbol_name, True):
            raise ConnectionFailureError(
                f"No fue posible seleccionar {symbol_name}: {api.last_error()}"
            )

    # Consulta la última cotización en MT5 y devuelve sus precios y tiempo en un MarketTick.
    def latest_tick(self, symbol_name: str) -> MarketTick:
        api = self._get_mt5_api()
        tick = api.symbol_info_tick(symbol_name)
        if tick is None:
            raise ConnectionFailureError(
                f"No fue posible obtener el último tick: {api.last_error()}"
            )
        return MarketTick(
            time_msc=int(tick.time_msc),
            bid=float(tick.bid),
            ask=float(tick.ask),
            last=float(tick.last),
        )

    # Consulta las velas recientes de un símbolo y devuelve un resumen de su cantidad y fechas.
    def recent_rates(self, symbol_name: str, timeframe: str, count: int) -> RatesCoverage:
        api = self._get_mt5_api()
        timeframe_value = getattr(api, f"TIMEFRAME_{timeframe}", None)
        if timeframe_value is None:
            raise ConnectionFailureError(f"Temporalidad no soportada: {timeframe}")
        rates = api.copy_rates_from_pos(symbol_name, timeframe_value, 0, count)
        if rates is None:
            raise ConnectionFailureError(f"copy_rates_from_pos falló: {api.last_error()}")
        returned_count = len(rates)
        return RatesCoverage(
            timeframe=timeframe,
            requested_count=count,
            returned_count=returned_count,
            earliest_utc=datetime_from_epoch_seconds(rates[0]["time"]) if returned_count else None,
            latest_utc=datetime_from_epoch_seconds(rates[-1]["time"]) if returned_count else None,
        )

    # Resume las velas recibidas dentro de un intervalo UTC solicitado.
    def rates_in_range(
        self, symbol_name: str, timeframe: str, start_utc: datetime, end_utc: datetime
    ) -> TimeRangeCoverage:
        api = self._get_mt5_api()
        timeframe_value = getattr(api, f"TIMEFRAME_{timeframe}", None)
        if timeframe_value is None:
            raise ConnectionFailureError(f"Temporalidad no soportada: {timeframe}")
        rates = api.copy_rates_range(symbol_name, timeframe_value, start_utc, end_utc)
        if rates is None:
            raise ConnectionFailureError(f"copy_rates_range falló: {api.last_error()}")
        return self._range_coverage(
            timeframe, start_utc, end_utc, rates, "time", datetime_from_epoch_seconds
        )

    # Resume los ticks recibidos dentro de un intervalo UTC solicitado.
    def ticks_in_range(
        self, symbol_name: str, start_utc: datetime, end_utc: datetime
    ) -> TimeRangeCoverage:
        api = self._get_mt5_api()
        ticks = api.copy_ticks_range(symbol_name, start_utc, end_utc, api.COPY_TICKS_ALL)
        if ticks is None:
            raise ConnectionFailureError(f"copy_ticks_range falló: {api.last_error()}")
        return self._range_coverage(
            "ticks", start_utc, end_utc, ticks, "time_msc", utc_datetime_from_epoch_milliseconds
        )

    # Convierte velas MT5 a M1Bar y excluye registros fuera del rango pedido.
    def bars_in_range(
        self, symbol_name: str, timeframe: str, start_utc: datetime, end_utc: datetime
    ) -> tuple[M1Bar, ...]:
        api = self._get_mt5_api()
        timeframe_value = getattr(api, f"TIMEFRAME_{timeframe}", None)
        if timeframe_value is None:
            raise ConnectionFailureError(f"Temporalidad no soportada: {timeframe}")
        rates = api.copy_rates_range(symbol_name, timeframe_value, start_utc, end_utc)
        if rates is None:
            raise ConnectionFailureError(f"copy_rates_range falló: {api.last_error()}")
        return tuple(
            M1Bar(
                open_time_utc=datetime_from_epoch_seconds(rate["time"]),
                open=float(rate["open"]),
                high=float(rate["high"]),
                low=float(rate["low"]),
                close=float(rate["close"]),
                tick_volume=int(rate["tick_volume"]),
                real_volume=int(rate["real_volume"]),
                spread_points=int(rate["spread"]),
            )
            for rate in rates
            if start_utc <= datetime_from_epoch_seconds(rate["time"]) <= end_utc
        )

    # Calcula cobertura, límites temporales y registros devueltos fuera del rango.
    @staticmethod
    def _range_coverage(
        source: str,
        start_utc: datetime,
        end_utc: datetime,
        records: Any,
        timestamp_field: str,
        converter: Any,
    ) -> TimeRangeCoverage:
        timestamps = [converter(record[timestamp_field]) for record in records]
        in_range = [timestamp for timestamp in timestamps if start_utc <= timestamp <= end_utc]
        return TimeRangeCoverage(
            source=source,
            requested_from_utc=start_utc,
            requested_to_utc=end_utc,
            returned_count=len(in_range),
            earliest_utc=min(in_range) if in_range else None,
            latest_utc=max(in_range) if in_range else None,
            out_of_range_count=len(timestamps) - len(in_range),
        )
