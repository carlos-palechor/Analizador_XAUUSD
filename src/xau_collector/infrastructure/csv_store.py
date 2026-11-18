from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from xau_collector.domain.models import M1Bar


# Gestiona CSV de velas por temporalidad y manifiestos de integridad sin ser una base de datos.
class CsvBarStore:
    """Temporary local storage, intentionally not a database."""

    _field_names = (
        "open_time_utc",
        "open",
        "high",
        "low",
        "close",
        "tick_volume",
        "real_volume",
        "spread_points",
    )
    _manifest_schema_version = 2

    # Guarda velas M1 de forma atómica y devuelve el hash SHA-256 del archivo resultante.
    def write(self, destination: Path, bars: Sequence[M1Bar]) -> str:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".csv.partial")
        with temporary.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self._field_names)
            writer.writeheader()
            for bar in bars:
                writer.writerow(
                    {
                        "open_time_utc": bar.open_time_utc.isoformat(),
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "tick_volume": bar.tick_volume,
                        "real_volume": bar.real_volume,
                        "spread_points": bar.spread_points,
                    }
                )
        temporary.replace(destination)
        return self.sha256(destination)

    # Guarda de forma atómica el manifiesto asociado a un CSV de velas.
    def write_manifest(self, destination: Path, manifest: dict[str, object]) -> None:
        path = self.manifest_path(destination)
        temporary = path.with_suffix(".json.partial")
        content = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)

    # Devuelve un manifiesto solo si su solicitud, estructura, CSV y hash siguen siendo válidos.
    def completed_manifest(
        self,
        destination: Path,
        expected_start: str,
        expected_end: str,
        symbol_name: str,
        timeframe: str,
    ) -> dict[str, object] | None:
        path = self.manifest_path(destination)
        if not destination.is_file() or not path.is_file():
            return None
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not self._is_valid_manifest(
            manifest, expected_start, expected_end, symbol_name, timeframe
        ):
            return None
        if manifest["sha256"] != self.sha256(destination):
            return None
        if not self._csv_matches_manifest(destination, int(manifest["bar_count"])):
            return None
        return manifest

    # Comprueba los metadatos mínimos necesarios para reutilizar un bloque sin descargarlo.
    def _is_valid_manifest(
        self,
        manifest: object,
        expected_start: str,
        expected_end: str,
        symbol_name: str,
        timeframe: str,
    ) -> bool:
        if not isinstance(manifest, dict):
            return False
        quality = manifest.get("quality")
        return (
            manifest.get("schema_version") == self._manifest_schema_version
            and manifest.get("symbol") == symbol_name
            and manifest.get("timeframe") == timeframe
            and manifest.get("requested_start_utc") == expected_start
            and manifest.get("requested_end_utc") == expected_end
            and isinstance(manifest.get("sha256"), str)
            and len(manifest["sha256"]) == 64
            and isinstance(manifest.get("bar_count"), int)
            and manifest["bar_count"] >= 0
            and isinstance(quality, dict)
        )

    # Comprueba cabeceras y cantidad de velas antes de confiar en un CSV existente.
    def _csv_matches_manifest(self, destination: Path, expected_bar_count: int) -> bool:
        try:
            with destination.open(newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                if tuple(reader.fieldnames or ()) != self._field_names:
                    return False
                return sum(1 for _ in reader) == expected_bar_count
        except (OSError, csv.Error):
            return False

    @staticmethod
    # Calcula la ruta del manifiesto que acompaña a un CSV de velas.
    def manifest_path(destination: Path) -> Path:
        return destination.with_suffix(".manifest.json")

    @staticmethod
    # Calcula una huella SHA-256 sin cargar todo el archivo en memoria.
    def sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()


# Conserva el nombre anterior mientras los servicios M1 migran al almacenamiento genérico.
CsvM1Store = CsvBarStore
