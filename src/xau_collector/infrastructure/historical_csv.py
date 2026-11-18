from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from xau_collector.domain.models import M1Bar


# Lee velas históricas locales para pruebas y backtesting sin conectarse a MT5.
class HistoricalCsvReader:
    # Convierte un CSV generado por CsvBarStore en velas ordenadas por apertura.
    def read(self, source: Path) -> tuple[M1Bar, ...]:
        with source.open(newline="", encoding="utf-8") as file:
            rows = csv.DictReader(file)
            bars = tuple(
                M1Bar(
                    datetime.fromisoformat(row["open_time_utc"]),
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    int(row["tick_volume"]),
                    int(row["real_volume"]),
                    int(row["spread_points"]),
                )
                for row in rows
            )
        return tuple(sorted(bars, key=lambda bar: bar.open_time_utc))
