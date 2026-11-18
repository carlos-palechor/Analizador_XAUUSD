from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from xau_collector.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
# Agrupa los valores necesarios para inicializar la terminal de MetaTrader 5.
class Mt5Settings:
    terminal_path: str | None
    initialize_timeout_ms: int


@dataclass(frozen=True, slots=True)
# Describe el símbolo lógico y los nombres alternativos que puede usar un bróker.
class SymbolSettings:
    logical_name: str
    aliases: tuple[str, ...]
    real_name: str | None


@dataclass(frozen=True, slots=True)
# Define los límites y opciones de la exploración inicial de historial.
class DiscoverySettings:
    recent_bars: int
    timeframe: str
    history_probe_lookback_days: tuple[int, ...]
    history_probe_window_hours: int
    probe_tick_history: bool


@dataclass(frozen=True, slots=True)
# Define la ubicación donde se guardan los reportes generados por el programa.
class OutputSettings:
    reports_directory: Path


@dataclass(frozen=True, slots=True)
# Define la ubicación local temporal de las velas M1 descargadas.
class StorageSettings:
    raw_m1_directory: Path


@dataclass(frozen=True, slots=True)
# Define la ubicación del archivo de sesiones exportado desde MT5.
class SessionSettings:
    snapshot_path: Path


@dataclass(frozen=True, slots=True)
# Reúne toda la configuración validada que consume el recolector.
class AppSettings:
    mt5: Mt5Settings
    symbol: SymbolSettings
    discovery: DiscoverySettings
    output: OutputSettings
    storage: StorageSettings
    sessions: SessionSettings = SessionSettings(
        Path("data/reference/sessions/xau_collector_symbol_sessions.csv")
    )


# Convierte un valor opcional de configuración en texto útil o en None.
def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


# Lee el archivo TOML y construye una configuración tipada para el programa.
def load_settings(config_path: Path) -> AppSettings:
    if not config_path.is_file():
        raise ConfigurationError(f"No existe el archivo de configuración: {config_path}")

    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    try:
        mt5 = raw["mt5"]
        symbol = raw["symbol"]
        discovery = raw["discovery"]
        output = raw["output"]
        storage = raw.get("storage", {})
        sessions = raw.get("sessions", {})
        settings = AppSettings(
            mt5=Mt5Settings(
                terminal_path=_optional_text(mt5.get("terminal_path")),
                initialize_timeout_ms=int(mt5["initialize_timeout_ms"]),
            ),
            symbol=SymbolSettings(
                logical_name=str(symbol["logical_name"]).upper(),
                aliases=tuple(str(alias).upper() for alias in symbol["aliases"]),
                real_name=_optional_text(symbol.get("real_name")),
            ),
            discovery=DiscoverySettings(
                recent_bars=int(discovery["recent_bars"]),
                timeframe=str(discovery["timeframe"]).upper(),
                history_probe_lookback_days=tuple(
                    int(days)
                    for days in discovery.get(
                        "history_probe_lookback_days",
                        [7, 30, 90, 180, 365, 730, 1460, 2920],
                    )
                ),
                history_probe_window_hours=int(discovery.get("history_probe_window_hours", 4)),
                probe_tick_history=bool(discovery.get("probe_tick_history", False)),
            ),
            output=OutputSettings(reports_directory=Path(output["reports_directory"])),
            storage=StorageSettings(
                raw_m1_directory=Path(storage.get("raw_m1_directory", "data/raw/m1"))
            ),
            sessions=SessionSettings(
                snapshot_path=Path(
                    sessions.get(
                        "snapshot_path",
                        "data/reference/sessions/xau_collector_symbol_sessions.csv",
                    )
                )
            ),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ConfigurationError(f"Configuración inválida: {exc}") from exc

    _validate(settings)
    return settings


# Rechaza configuraciones incompletas o con límites numéricos inválidos.
def _validate(settings: AppSettings) -> None:
    if settings.mt5.initialize_timeout_ms <= 0:
        raise ConfigurationError("initialize_timeout_ms debe ser mayor que cero")
    if settings.discovery.recent_bars <= 0:
        raise ConfigurationError("recent_bars debe ser mayor que cero")
    if not settings.discovery.history_probe_lookback_days:
        raise ConfigurationError("Debe existir al menos un periodo de sondeo histórico")
    if any(days <= 0 for days in settings.discovery.history_probe_lookback_days):
        raise ConfigurationError("Los días de sondeo histórico deben ser mayores que cero")
    if settings.discovery.history_probe_window_hours <= 0:
        raise ConfigurationError("history_probe_window_hours debe ser mayor que cero")
    if not settings.symbol.aliases:
        raise ConfigurationError("Debe existir al menos un alias de símbolo")
