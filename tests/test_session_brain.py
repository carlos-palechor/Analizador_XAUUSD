from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from xau_collector.domain.market import InstrumentIdentity
from xau_collector.domain.models import M1Bar
from xau_collector.services.session_brain import SessionBrain


# Simula un repositorio para comprobar el cerebro sin archivos, MT5 ni PostgreSQL.
class _Repository:
    # Entrega las velas preparadas por cada caso de prueba.
    def __init__(self, bars: tuple[M1Bar, ...]) -> None:
        self._bars = bars

    # Implementa la lectura mínima requerida por el contrato común.
    def closed_bars(self, identity, timeframe, cutoff_utc=None, limit=None):
        bars = tuple(
            bar for bar in self._bars if cutoff_utc is None or bar.open_time_utc < cutoff_utc
        )
        return bars[-limit:] if limit else bars


# Verifica rangos, horario de verano y ausencia de datos de cada sesión.
class SessionBrainTests(unittest.TestCase):
    # Crea velas M5 consecutivas para un intervalo UTC controlado.
    def _bars(self, start: datetime, count: int) -> tuple[M1Bar, ...]:
        return tuple(
            M1Bar(start + timedelta(minutes=5 * index), 100 + index, 102 + index, 99 + index,
                  101 + index, 10, 0, 1)
            for index in range(count)
        )

    # Reconoce la sesión de Londres y ajusta sus horas UTC según verano europeo.
    def test_uses_official_timezone_for_london_session(self) -> None:
        report = SessionBrain().run(
            _Repository(self._bars(datetime(2026, 7, 6, 7, tzinfo=UTC), 120)),
            InstrumentIdentity("broker", "server", "XAUUSDm", "test"),
            datetime(2026, 7, 6, 18, tzinfo=UTC),
        )
        london = next(item for item in report.sessions if item.session_name == "LONDRES")
        self.assertEqual(london.started_at_utc, datetime(2026, 7, 6, 7, tzinfo=UTC))
        self.assertEqual(london.ended_at_utc, datetime(2026, 7, 6, 16, tzinfo=UTC))
        self.assertEqual(london.bar_count, 108)
        self.assertEqual(london.status, "COMPLETA")

    # Marca incompleta una sesión cuando faltan velas, en lugar de inventar un rango fiable.
    def test_marks_incomplete_session_when_coverage_is_missing(self) -> None:
        report = SessionBrain().run(
            _Repository(self._bars(datetime(2026, 7, 6, 7, tzinfo=UTC), 10)),
            InstrumentIdentity("broker", "server", "XAUUSDm", "test"),
            datetime(2026, 7, 6, 18, tzinfo=UTC),
        )
        london = next(item for item in report.sessions if item.session_name == "LONDRES")
        self.assertEqual(london.status, "INCOMPLETA")
        self.assertEqual(london.bar_count, 10)


if __name__ == "__main__":
    unittest.main()
