from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from xau_collector.domain.models import M1Bar
from xau_collector.infrastructure.postgres_history_importer import (
    _bar_matches_current,
    _psycopg_connection_url,
    discover_historical_csvs,
)
from xau_collector.services.historical_import_validation import HistoricalCsvValidator


# Comprueba validación de OHLC, duplicados y descubrimiento de fuentes sin PostgreSQL.
class HistoricalImportValidationTests(unittest.TestCase):
    # Conserva una fila válida y separa una duplicada y una inválida.
    def test_validator_classifies_valid_duplicate_and_invalid_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "bars.csv"
            self._write_csv(
                source,
                (
                    self._row("2026-01-01T00:00:00+00:00", "10", "12", "9", "11"),
                    self._row("2026-01-01T00:00:00+00:00", "10", "12", "9", "11"),
                    self._row("2026-01-01T00:05:00+00:00", "10", "9", "11", "10"),
                ),
            )
            result = HistoricalCsvValidator().validate(source)
        self.assertEqual(result.original_rows, 3)
        self.assertEqual(len(result.accepted_bars), 1)
        self.assertEqual(result.duplicate_rows, 1)
        self.assertEqual(result.rejected_rows, 1)

    # Encuentra fuentes por temporalidad sin depender de nombres de descarga específicos.
    def test_discovers_csv_sources_by_timeframe_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for timeframe in ("h4", "h1", "m15", "m5"):
                folder = root / timeframe
                folder.mkdir()
                (folder / "history.csv").write_text("open_time_utc\n", encoding="utf-8")
            nested = root / "m1" / "symbol=XAUUSDm"
            nested.mkdir(parents=True)
            (nested / "history.csv").write_text("open_time_utc\n", encoding="utf-8")
            sources = discover_historical_csvs(root)
        self.assertEqual(
            tuple(timeframe for timeframe, _ in sources), ("H4", "H1", "M15", "M5", "M1")
        )

    # Acepta la misma URL SQLAlchemy usada por Alembic para abrir psycopg directamente.
    def test_adapts_sqlalchemy_postgres_url_for_psycopg(self) -> None:
        result = _psycopg_connection_url("postgresql+psycopg://user:secret@localhost/database")
        self.assertEqual(result, "postgresql://user:secret@localhost/database")

    # Reconoce una corrección OHLC para crear revisión nueva en vez de ignorar la vela.
    def test_detects_changed_content_against_current_bar_revision(self) -> None:
        bar = M1Bar(datetime(2026, 1, 1, tzinfo=UTC), 10.0, 12.0, 9.0, 11.0, 1, 0, 2)
        current = (
            "id",
            1,
            Decimal("10.0"),
            Decimal("12.0"),
            Decimal("9.0"),
            Decimal("11.0"),
            1,
            0,
            2,
        )
        corrected = M1Bar(datetime(2026, 1, 1, tzinfo=UTC), 10.0, 12.5, 9.0, 11.0, 1, 0, 2)

        self.assertTrue(_bar_matches_current(current, bar))
        self.assertFalse(_bar_matches_current(current, corrected))

    # Construye una fila compatible con el formato de históricos del proyecto.
    @staticmethod
    def _row(open_time: str, opening: str, high: str, low: str, close: str) -> dict[str, str]:
        return {
            "open_time_utc": open_time,
            "open": opening,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": "1",
            "real_volume": "0",
            "spread_points": "2",
        }

    # Escribe un CSV temporal conservando las cabeceras oficiales.
    @staticmethod
    def _write_csv(source: Path, rows: tuple[dict[str, str], ...]) -> None:
        with source.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=HistoricalCsvValidator._field_names)
            writer.writeheader()
            writer.writerows(rows)
