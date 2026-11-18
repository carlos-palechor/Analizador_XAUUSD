from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from xau_collector.errors import ConfigurationError
from xau_collector.services.session_calendar import Mt5QuoteSessionCalendar

SESSION_SNAPSHOT = Path("data/reference/sessions/xau_collector_symbol_sessions.csv")


# Verifica que el calendario interprete las sesiones reales exportadas desde MT5.
class RealMt5SessionSnapshotTests(unittest.TestCase):
    # Carga el archivo real de sesiones y omite la prueba si todavía no fue exportado.
    def setUp(self) -> None:
        if not SESSION_SNAPSHOT.is_file():
            self.skipTest("No existe un archivo de sesiones reales exportado desde MT5.")
        self.calendar = Mt5QuoteSessionCalendar.from_csv(SESSION_SNAPSHOT, "XAUUSDm")

    # Comprueba la reapertura de cotizaciones del domingo reportada por MT5.
    def test_sunday_quote_session_opens_at_2200_server_time(self) -> None:
        self.assertTrue(
            self.calendar.is_expected_market_closed(datetime(2026, 11, 8, 21, 59, tzinfo=UTC))
        )
        self.assertFalse(
            self.calendar.is_expected_market_closed(datetime(2026, 11, 8, 22, tzinfo=UTC))
        )

    # Comprueba la pausa diaria de cotización entre 20:58 y 22:00 reportada por MT5.
    def test_weekday_rollover_pause_matches_the_real_snapshot(self) -> None:
        self.assertTrue(
            self.calendar.is_expected_market_closed(datetime(2026, 11, 9, 20, 58, tzinfo=UTC))
        )
        self.assertFalse(
            self.calendar.is_expected_market_closed(datetime(2026, 11, 9, 22, tzinfo=UTC))
        )

    # Comprueba el cierre semanal del viernes informado por la sesión de cotización.
    def test_friday_close_matches_the_real_snapshot(self) -> None:
        self.assertTrue(
            self.calendar.is_expected_market_closed(datetime(2026, 11, 13, 20, 58, tzinfo=UTC))
        )

    # Comprueba que un hueco de rollover sea esperado y uno intradía siga en revisión.
    def test_gap_classification_matches_the_real_snapshot(self) -> None:
        self.assertTrue(
            self.calendar.is_expected_gap(
                datetime(2026, 11, 10, 20, 57, tzinfo=UTC),
                datetime(2026, 11, 10, 22, tzinfo=UTC),
            )
        )

    # Obliga a renovar la exportación cuando una regla del bróker puede haber cambiado.
    def test_calendar_exposes_when_snapshot_is_stale(self) -> None:
        self.assertFalse(self.calendar.is_stale(datetime(2026, 11, 20, tzinfo=UTC)))
        self.assertTrue(self.calendar.is_stale(datetime(2026, 12, 20, tzinfo=UTC)))

    # Impide que una exportación vieja se use para validar datos recientes sin revisión.
    def test_stale_calendar_requires_a_new_export(self) -> None:
        with self.assertRaises(ConfigurationError):
            self.calendar.require_fresh(datetime(2026, 12, 20, tzinfo=UTC))
        self.assertFalse(
            self.calendar.is_expected_gap(
                datetime(2026, 11, 10, 15, 0, tzinfo=UTC),
                datetime(2026, 11, 10, 15, 5, tzinfo=UTC),
            )
        )


if __name__ == "__main__":
    unittest.main()
