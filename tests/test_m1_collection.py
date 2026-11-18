from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.config import (
    AppSettings,
    DiscoverySettings,
    Mt5Settings,
    OutputSettings,
    StorageSettings,
    SymbolSettings,
)
from xau_collector.domain.models import M1Bar, SymbolDescriptor
from xau_collector.infrastructure.csv_store import CsvM1Store
from xau_collector.services.m1_collection import M1CollectionService
from xau_collector.services.m1_quality import M1QualityValidator
from xau_collector.services.session_calendar import XauUsdWeekendSession
from xau_collector.services.symbol_resolver import SymbolResolver


# Simula únicamente el origen de velas para aislar la lógica de almacenamiento M1.
class CollectionGateway:
    # Inicializa contadores que permiten comprobar cierre y reutilización del archivo.
    def __init__(self) -> None:
        self.closed = False
        self.bar_requests = 0

    # Representa una conexión sin efectos externos para la prueba de recolección.
    def connect(self) -> None:
        pass

    # Registra que el servicio cerró correctamente la fuente de datos.
    def close(self) -> None:
        self.closed = True

    # Devuelve el símbolo mínimo necesario para que el resolutor elija XAUUSDm.
    def list_symbols(self) -> tuple[SymbolDescriptor, ...]:
        return (SymbolDescriptor("XAUUSDm", "Gold", "Metals", 3, 0.001, "XAU", "USD", 100, True),)

    # Registra el símbolo que el servicio activa antes de solicitar velas.
    def select_symbol(self, symbol_name: str) -> None:
        self.selected_symbol = symbol_name

    # Devuelve dos velas deterministas y cuenta las solicitudes de descarga.
    def bars_in_range(
        self, symbol_name: str, timeframe: str, start_utc: datetime, end_utc: datetime
    ) -> tuple[M1Bar, ...]:
        self.bar_requests += 1
        first = M1Bar(start_utc, 100.0, 101.0, 99.0, 100.5, 10, 0, 2)
        second = M1Bar(start_utc.replace(minute=1), 100.5, 102.0, 100.0, 101.0, 12, 0, 2)
        return (first, second)


# Verifica guardado local, manifiesto y reanudación de una recolección M1.
class M1CollectionServiceTests(unittest.TestCase):
    # Señala velas inválidas, repetidas y desordenadas para no analizar datos inseguros.
    def test_quality_validator_detects_invalid_duplicate_and_out_of_order_bars(self) -> None:
        opened_at = datetime(2026, 1, 5, tzinfo=UTC)
        bars = (
            M1Bar(opened_at.replace(minute=2), 100.0, 99.0, 101.0, 100.5, 10, 0, 2),
            M1Bar(opened_at.replace(minute=2), 100.0, 101.0, 99.0, 100.5, 10, 0, 2),
            M1Bar(opened_at.replace(minute=0), 100.0, 101.0, 99.0, 100.5, 10, 0, 2),
        )
        summary = M1QualityValidator(XauUsdWeekendSession()).validate(
            bars,
            opened_at.replace(minute=1),
        )

        self.assertEqual(summary.invalid_bar_count, 1)
        self.assertEqual(summary.duplicate_count, 1)
        self.assertEqual(summary.out_of_order_count, 1)

    # Confirma que el segundo intento reutilice el CSV validado sin otra descarga.
    def test_collects_one_month_chunk_to_local_csv(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = AppSettings(
                Mt5Settings(None, 60_000),
                SymbolSettings("XAUUSD", ("XAUUSD",), None),
                DiscoverySettings(100, "M1", (7,), 4, False),
                OutputSettings(root / "reports"),
                StorageSettings(root / "raw"),
            )
            gateway = CollectionGateway()
            service = M1CollectionService(
                gateway,
                SymbolResolver(),
                M1QualityValidator(XauUsdWeekendSession()),
                CsvM1Store(),
            )

            report = service.run(
                settings,
                datetime(2026, 1, 5, tzinfo=UTC),
                datetime(2026, 1, 6, tzinfo=UTC),
            )

            self.assertEqual(report.symbol, "XAUUSDm")
            self.assertEqual(len(report.chunks), 1)
            self.assertEqual(report.chunks[0].bar_count, 2)
            self.assertTrue(Path(report.chunks[0].file_path).is_file())
            self.assertTrue(gateway.closed)

            resumed = service.run(
                settings,
                datetime(2026, 1, 5, tzinfo=UTC),
                datetime(2026, 1, 6, tzinfo=UTC),
            )
            self.assertEqual(gateway.bar_requests, 1)
            self.assertEqual(resumed.chunks[0].status, "SKIPPED_VERIFIED")

    # Conserva una descarga parcial cuando posteriormente se solicita el mes completo.
    def test_partial_and_full_month_downloads_use_different_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = AppSettings(
                Mt5Settings(None, 60_000),
                SymbolSettings("XAUUSD", ("XAUUSD",), None),
                DiscoverySettings(100, "M1", (7,), 4, False),
                OutputSettings(root / "reports"),
                StorageSettings(root / "raw"),
            )
            gateway = CollectionGateway()
            service = M1CollectionService(
                gateway,
                SymbolResolver(),
                M1QualityValidator(XauUsdWeekendSession()),
                CsvM1Store(),
            )

            partial = service.run(
                settings,
                datetime(2026, 1, 5, tzinfo=UTC),
                datetime(2026, 1, 5, 23, 59, 59, tzinfo=UTC),
            )
            full_month = service.run(
                settings,
                datetime(2026, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 31, 23, 59, 59, tzinfo=UTC),
            )

            self.assertEqual(gateway.bar_requests, 2)
            self.assertNotEqual(partial.chunks[0].file_path, full_month.chunks[0].file_path)
            self.assertTrue(Path(partial.chunks[0].file_path).is_file())
            self.assertTrue(Path(full_month.chunks[0].file_path).is_file())

    # Descarga de nuevo un bloque cuando su CSV ya no coincide con el manifiesto guardado.
    def test_corrupted_csv_is_not_reused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = AppSettings(
                Mt5Settings(None, 60_000),
                SymbolSettings("XAUUSD", ("XAUUSD",), None),
                DiscoverySettings(100, "M1", (7,), 4, False),
                OutputSettings(root / "reports"),
                StorageSettings(root / "raw"),
            )
            gateway = CollectionGateway()
            service = M1CollectionService(
                gateway,
                SymbolResolver(),
                M1QualityValidator(XauUsdWeekendSession()),
                CsvM1Store(),
            )
            start = datetime(2026, 1, 5, tzinfo=UTC)
            end = datetime(2026, 1, 6, tzinfo=UTC)

            first = service.run(settings, start, end)
            Path(first.chunks[0].file_path).write_text("archivo alterado\n", encoding="utf-8")
            repeated = service.run(settings, start, end)

            self.assertEqual(gateway.bar_requests, 2)
            self.assertEqual(repeated.chunks[0].status, "WRITTEN")


if __name__ == "__main__":
    unittest.main()
