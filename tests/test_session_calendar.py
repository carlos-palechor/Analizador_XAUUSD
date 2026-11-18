from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from xau_collector.errors import ConfigurationError
from xau_collector.services.session_calendar import (
    Mt5QuoteSessionCalendar,
    QuoteSession,
    QuoteSessionPeriod,
    XauUsdWeekendSession,
)


# Verifica la clasificación del cierre semanal provisional de XAUUSD.
class XauUsdWeekendSessionTests(unittest.TestCase):
    # Crea un calendario independiente para cada escenario temporal.
    def setUp(self) -> None:
        self.sessions = XauUsdWeekendSession()

    # Confirma que el viernes posterior al cierre de Colombia sea mercado cerrado.
    def test_friday_after_colombia_close_is_expected_closed(self) -> None:
        self.assertTrue(
            self.sessions.is_expected_market_closed(datetime(2026, 10, 16, 22, tzinfo=UTC))
        )

    # Confirma que el domingo previo a la reapertura de Colombia sea mercado cerrado.
    def test_sunday_before_colombia_open_is_expected_closed(self) -> None:
        self.assertTrue(
            self.sessions.is_expected_market_closed(datetime(2026, 10, 18, 21, 59, tzinfo=UTC))
        )

    # Clasifica como esperado un hueco compuesto solo por minutos de fin de semana.
    def test_weekend_gap_is_not_an_error(self) -> None:
        friday = datetime(2026, 10, 16, 21, 59, tzinfo=UTC)
        sunday = datetime(2026, 10, 18, 22, tzinfo=UTC)
        self.assertTrue(self.sessions.is_expected_gap(friday, sunday))

    # Conserva para revisión un hueco ocurrido durante un día laborable.
    def test_weekday_gap_requires_review(self) -> None:
        monday = datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
        self.assertFalse(self.sessions.is_expected_gap(monday, monday.replace(minute=5)))

    # Usa el horario histórico de la fecha, incluso ante un cambio de desfase del servidor.
    def test_mt5_calendar_selects_the_effective_historical_period(self) -> None:
        session = QuoteSession("MONDAY", 7200, 10800)
        calendar = Mt5QuoteSessionCalendar.from_periods(
            (
                QuoteSessionPeriod(
                    (session,),
                    timedelta(hours=2),
                    datetime(2026, 1, 1, tzinfo=UTC),
                    datetime(2026, 3, 1, tzinfo=UTC),
                ),
                QuoteSessionPeriod(
                    (session,), timedelta(hours=3), datetime(2026, 3, 1, tzinfo=UTC)
                ),
            ),
            datetime(2026, 3, 1, tzinfo=UTC),
        )

        self.assertFalse(calendar.is_expected_market_closed(datetime(2026, 1, 5, tzinfo=UTC)))
        self.assertFalse(calendar.is_expected_market_closed(datetime(2026, 3, 1, 23, tzinfo=UTC)))

    # Rechaza dos horarios que pretenden estar vigentes durante el mismo período histórico.
    def test_mt5_calendar_rejects_overlapping_periods(self) -> None:
        session = QuoteSession("MONDAY", 0, 3600)
        with self.assertRaises(ConfigurationError):
            Mt5QuoteSessionCalendar.from_periods(
                (
                    QuoteSessionPeriod(
                        (session,), timedelta(hours=2), datetime(2026, 1, 1, tzinfo=UTC),
                        datetime(2026, 3, 2, tzinfo=UTC),
                    ),
                    QuoteSessionPeriod(
                        (session,), timedelta(hours=3), datetime(2026, 2, 1, tzinfo=UTC),
                    ),
                ),
                datetime(2026, 3, 1, tzinfo=UTC),
            )


if __name__ == "__main__":
    unittest.main()
