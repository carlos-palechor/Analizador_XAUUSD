from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.domain.models import M1Bar
from xau_collector.errors import ConfigurationError


# Resume las velas válidas y rechazadas antes de escribir cualquier dato en PostgreSQL.
@dataclass(frozen=True, slots=True)
class CsvValidationResult:
    source: Path
    original_rows: int
    accepted_bars: tuple[M1Bar, ...]
    duplicate_rows: int
    rejected_rows: int
    period_start_utc: datetime | None
    period_end_utc: datetime | None


# Valida el formato OHLC y los duplicados internos de un CSV histórico.
class HistoricalCsvValidator:
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

    # Lee cada fila, conserva solo velas válidas y nunca modifica el archivo original.
    def validate(self, source: Path) -> CsvValidationResult:
        if not source.is_file():
            raise ConfigurationError(f"No existe el CSV histórico: {source}")
        accepted: list[M1Bar] = []
        seen_open_times: set[datetime] = set()
        original_rows = duplicate_rows = rejected_rows = 0
        try:
            with source.open(newline="", encoding="utf-8") as file:
                reader = csv.DictReader(file)
                if tuple(reader.fieldnames or ()) != self._field_names:
                    raise ConfigurationError(f"Columnas inválidas en CSV histórico: {source}")
                for row in reader:
                    original_rows += 1
                    bar = _parse_bar(row)
                    if bar is None:
                        rejected_rows += 1
                        continue
                    if bar.open_time_utc in seen_open_times:
                        duplicate_rows += 1
                        continue
                    seen_open_times.add(bar.open_time_utc)
                    accepted.append(bar)
        except OSError as exc:
            raise ConfigurationError(f"No fue posible leer CSV histórico: {source}") from exc
        accepted.sort(key=lambda bar: bar.open_time_utc)
        return CsvValidationResult(
            source,
            original_rows,
            tuple(accepted),
            duplicate_rows,
            rejected_rows,
            accepted[0].open_time_utc if accepted else None,
            accepted[-1].open_time_utc if accepted else None,
        )


# Convierte una fila a vela solo cuando todos sus datos tienen sentido técnico básico.
def _parse_bar(row: dict[str, str]) -> M1Bar | None:
    try:
        open_time = datetime.fromisoformat(row["open_time_utc"]).astimezone(UTC)
        bar = M1Bar(
            open_time,
            float(row["open"]),
            float(row["high"]),
            float(row["low"]),
            float(row["close"]),
            int(row["tick_volume"]),
            int(row["real_volume"]),
            int(row["spread_points"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if (
        bar.high < bar.low
        or not bar.low <= bar.open <= bar.high
        or not bar.low <= bar.close <= bar.high
        or bar.tick_volume < 0
        or bar.real_volume < 0
        or bar.spread_points < 0
    ):
        return None
    return bar
