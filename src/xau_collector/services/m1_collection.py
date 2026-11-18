from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from xau_collector.config import AppSettings
from xau_collector.errors import CollectorError
from xau_collector.infrastructure.csv_store import CsvM1Store
from xau_collector.ports.market_data import MarketDataGateway
from xau_collector.services.m1_quality import M1QualityValidator
from xau_collector.services.symbol_resolver import SymbolResolver


@dataclass(frozen=True, slots=True)
# Representa el resultado verificable de descargar o reutilizar un bloque M1.
class M1ChunkResult:
    start_utc: datetime
    end_utc: datetime
    file_path: str
    manifest_path: str
    status: str
    sha256: str
    bar_count: int
    invalid_bar_count: int
    duplicate_count: int
    expected_gap_count: int
    unexpected_gap_count: int
    gaps: tuple[object, ...]


@dataclass(frozen=True, slots=True)
# Agrupa los bloques M1 procesados durante una ejecución de recolección.
class M1CollectionReport:
    symbol: str
    started_at_utc: datetime
    finished_at_utc: datetime
    chunks: tuple[M1ChunkResult, ...]

    # Convierte el reporte de recolección en datos serializables para JSON.
    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        return _serialize_datetimes(payload)


# Recorre datos anidados y convierte fechas a texto ISO-8601.
def _serialize_datetimes(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize_datetimes(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize_datetimes(item) for item in value]
    return value


# Coordina descarga, validación y persistencia verificable de velas M1 por mes.
class M1CollectionService:
    # Recibe las dependencias necesarias para obtener, validar y guardar velas M1.
    def __init__(
        self,
        gateway: MarketDataGateway,
        resolver: SymbolResolver,
        validator: M1QualityValidator,
        store: CsvM1Store,
    ) -> None:
        self._gateway = gateway
        self._resolver = resolver
        self._validator = validator
        self._store = store

    # Procesa un intervalo UTC y devuelve el resultado de cada bloque mensual.
    def run(
        self, settings: AppSettings, start_utc: datetime, end_utc: datetime
    ) -> M1CollectionReport:
        if start_utc.tzinfo is None or end_utc.tzinfo is None:
            raise CollectorError("Las fechas de descarga deben incluir zona horaria UTC")
        if end_utc <= start_utc:
            raise CollectorError("La fecha final debe ser posterior a la fecha inicial")

        started = datetime.now(UTC)
        self._gateway.connect()
        try:
            symbol = self._resolver.resolve(
                self._gateway.list_symbols(),
                settings.symbol.logical_name,
                settings.symbol.aliases,
                settings.symbol.real_name,
            )
            self._gateway.select_symbol(symbol.name)
            previous_last_open: datetime | None = None
            chunks: list[M1ChunkResult] = []
            for chunk_start, chunk_end in _month_windows(start_utc, end_utc):
                path = _chunk_path(
                    settings.storage.raw_m1_directory, symbol.name, chunk_start, chunk_end
                )
                existing = self._store.completed_manifest(
                    path,
                    chunk_start.isoformat(),
                    chunk_end.isoformat(),
                    symbol.name,
                    "M1",
                )
                if existing is not None:
                    previous_last_open = _manifest_last_open(existing) or previous_last_open
                    chunks.append(_chunk_result_from_manifest(existing, path))
                    continue
                bars = tuple(
                    sorted(
                        self._gateway.bars_in_range(symbol.name, "M1", chunk_start, chunk_end),
                        key=lambda bar: bar.open_time_utc,
                    )
                )
                quality = self._validator.validate(bars, previous_last_open)
                previous_last_open = quality.last_open_utc or previous_last_open
                sha256 = self._store.write(path, bars)
                manifest = _manifest(
                    symbol.name,
                    chunk_start,
                    chunk_end,
                    sha256,
                    len(bars),
                    quality,
                )
                self._store.write_manifest(path, manifest)
                chunks.append(
                    M1ChunkResult(
                        start_utc=chunk_start,
                        end_utc=chunk_end,
                        file_path=str(path),
                        manifest_path=str(self._store.manifest_path(path)),
                        status="WRITTEN",
                        sha256=sha256,
                        bar_count=len(bars),
                        invalid_bar_count=quality.invalid_bar_count,
                        duplicate_count=quality.duplicate_count,
                        expected_gap_count=quality.expected_gap_count,
                        unexpected_gap_count=quality.unexpected_gap_count,
                        gaps=quality.gaps,
                    )
                )
            return M1CollectionReport(symbol.name, started, datetime.now(UTC), tuple(chunks))
        finally:
            self._gateway.close()


# Divide un intervalo UTC en bloques que no cruzan el límite de un mes.
def _month_windows(start_utc: datetime, end_utc: datetime) -> tuple[tuple[datetime, datetime], ...]:
    current = datetime(start_utc.year, start_utc.month, 1, tzinfo=UTC)
    windows: list[tuple[datetime, datetime]] = []
    while current < end_utc:
        next_month = _next_month(current)
        window_start = max(current, start_utc)
        window_end = min(next_month - timedelta(seconds=1), end_utc)
        windows.append((window_start, window_end))
        current = next_month
    return tuple(windows)


# Calcula el primer instante UTC del mes siguiente.
def _next_month(current: datetime) -> datetime:
    if current.month == 12:
        return datetime(current.year + 1, 1, 1, tzinfo=UTC)
    return datetime(current.year, current.month + 1, 1, tzinfo=UTC)


# Construye una ruta única para evitar que una descarga parcial reemplace a otra del mismo mes.
def _chunk_path(root: Path, symbol_name: str, start_utc: datetime, end_utc: datetime) -> Path:
    return (
        root
        / f"symbol={symbol_name}"
        / f"year={start_utc.year}"
        / f"month={start_utc.month:02d}"
        / f"m1_{start_utc:%Y%m%dT%H%M%SZ}_{end_utc:%Y%m%dT%H%M%SZ}.csv"
    )


# Construye el manifiesto que vincula un CSV con su rango, calidad y hash.
def _manifest(
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    sha256: str,
    bar_count: int,
    quality: object,
) -> dict[str, object]:
    quality_data = asdict(quality)
    return {
        "schema_version": 2,
        "symbol": symbol,
        "timeframe": "M1",
        "requested_start_utc": start_utc.isoformat(),
        "requested_end_utc": end_utc.isoformat(),
        "bar_count": bar_count,
        "sha256": sha256,
        "quality": _serialize_datetimes(quality_data),
    }


# Reconstruye el resultado de un bloque ya validado sin descargarlo otra vez.
def _chunk_result_from_manifest(manifest: dict[str, object], path: Path) -> M1ChunkResult:
    quality = manifest.get("quality", {})
    if not isinstance(quality, dict):
        raise CollectorError(f"Manifiesto inválido: {CsvM1Store.manifest_path(path)}")
    return M1ChunkResult(
        start_utc=datetime.fromisoformat(str(manifest["requested_start_utc"])),
        end_utc=datetime.fromisoformat(str(manifest["requested_end_utc"])),
        file_path=str(path),
        manifest_path=str(CsvM1Store.manifest_path(path)),
        status="SKIPPED_VERIFIED",
        sha256=str(manifest["sha256"]),
        bar_count=int(manifest["bar_count"]),
        invalid_bar_count=int(quality.get("invalid_bar_count", 0)),
        duplicate_count=int(quality.get("duplicate_count", 0)),
        expected_gap_count=int(quality.get("expected_gap_count", 0)),
        unexpected_gap_count=int(quality.get("unexpected_gap_count", 0)),
        gaps=tuple(quality.get("gaps", [])),
    )


# Extrae la última vela de un manifiesto reutilizado para conservar validación entre bloques.
def _manifest_last_open(manifest: dict[str, object]) -> datetime | None:
    quality = manifest.get("quality")
    if not isinstance(quality, dict):
        return None
    value = quality.get("last_open_utc")
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None
