from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

from xau_collector.errors import ConfigurationError


# Clasifica el cierre semanal provisional de XAUUSD según el horario observado del bróker.
class XauUsdWeekendSession:
    """Initial UTC session policy from the user's Exness schedule.

    Colombia is UTC-5 year-round, so the observed Friday/Sunday 17:00 closure
    is 22:00 UTC. Broker holiday schedules are deliberately not inferred here.
    """

    _closure_time_utc = time(hour=22)

    # Indica si un instante UTC está dentro del cierre semanal provisional.
    def is_expected_market_closed(self, instant_utc: datetime) -> bool:
        weekday = instant_utc.weekday()
        current_time = instant_utc.timetz().replace(tzinfo=None)
        if weekday == 4:
            return current_time >= self._closure_time_utc
        if weekday == 5:
            return True
        if weekday == 6:
            return current_time < self._closure_time_utc
        return False

    # Determina si todos los minutos ausentes pertenecen al cierre semanal conocido.
    def is_expected_gap(self, previous_open: datetime, next_open: datetime) -> bool:
        """Return true only when every missing M1 interval is a known weekend closure."""
        if next_open <= previous_open + timedelta(minutes=1):
            return False
        cursor = previous_open + timedelta(minutes=1)
        while cursor < next_open:
            if not self.is_expected_market_closed(cursor):
                return False
            cursor += timedelta(minutes=1)
        return True


# Representa una sesión semanal de cotización exportada por la terminal MT5.
@dataclass(frozen=True, slots=True)
class QuoteSession:
    weekday: str
    start_seconds_server: int
    end_seconds_server: int


# Conserva una versión del horario del bróker con el período histórico en que fue vigente.
@dataclass(frozen=True, slots=True)
class QuoteSessionPeriod:
    sessions: tuple[QuoteSession, ...]
    server_utc_offset: timedelta
    effective_from_utc: datetime
    effective_until_utc: datetime | None = None

    # Indica si el instante pertenece al período de vigencia conocido de este horario.
    def contains(self, instant_utc: datetime) -> bool:
        instant = instant_utc.astimezone(UTC)
        return instant >= self.effective_from_utc and (
            self.effective_until_utc is None or instant < self.effective_until_utc
        )


# Clasifica huecos según las sesiones de cotización reales exportadas desde MT5.
class Mt5QuoteSessionCalendar:
    # Construye el calendario y el desfase observado entre la hora del servidor y UTC.
    def __init__(
        self,
        sessions: tuple[QuoteSession, ...],
        server_utc_offset: timedelta,
        observed_at_utc: datetime,
    ) -> None:
        self._periods = (
            QuoteSessionPeriod(sessions, server_utc_offset, datetime.min.replace(tzinfo=UTC)),
        )
        self._observed_at_utc = observed_at_utc

    # Construye un calendario histórico con uno o más horarios efectivos del bróker.
    @classmethod
    def from_periods(
        cls, periods: tuple[QuoteSessionPeriod, ...], observed_at_utc: datetime
    ) -> Mt5QuoteSessionCalendar:
        if not periods:
            raise ConfigurationError("El calendario requiere al menos un período de sesiones")
        ordered = tuple(sorted(periods, key=lambda period: period.effective_from_utc))
        _validate_periods(ordered)
        calendar = cls(ordered[0].sessions, ordered[0].server_utc_offset, observed_at_utc)
        calendar._periods = ordered
        return calendar

    @property
    # Devuelve cuándo MT5 informó el horario usado por este calendario.
    def observed_at_utc(self) -> datetime:
        return self._observed_at_utc

    # Indica si el calendario debe exportarse otra vez antes de validar datos recientes.
    def is_stale(
        self, reference_utc: datetime, maximum_age: timedelta = timedelta(days=30)
    ) -> bool:
        return reference_utc - self._observed_at_utc > maximum_age

    # Detiene validaciones recientes cuando el horario exportado ya no es confiable.
    def require_fresh(self, reference_utc: datetime) -> None:
        if self.is_stale(reference_utc):
            raise ConfigurationError(
                "El calendario de sesiones MT5 tiene más de 30 días; expórtelo nuevamente"
            )

    # Lee y valida un archivo de sesiones creado por ExportSymbolSessions.mq5.
    @classmethod
    def from_csv(cls, source: Path, expected_symbol: str) -> Mt5QuoteSessionCalendar:
        try:
            with source.open(newline="", encoding="utf-8") as file:
                rows = tuple(csv.DictReader(file, delimiter=";"))
        except OSError as exc:
            raise ConfigurationError(f"No fue posible leer sesiones MT5: {source}") from exc
        if not rows or any(row.get("schema_version") != "2" for row in rows):
            raise ConfigurationError("El archivo de sesiones MT5 no tiene un formato válido")
        if any(row.get("symbol") != expected_symbol for row in rows):
            raise ConfigurationError("El archivo de sesiones no corresponde al símbolo configurado")
        first = rows[0]
        try:
            generated_utc = datetime.strptime(
                first["generated_at_utc"], "%Y.%m.%d %H:%M:%S"
            ).replace(tzinfo=UTC)
            server_time = datetime.strptime(first["server_time"], "%Y.%m.%d %H:%M:%S").replace(
                tzinfo=UTC
            )
            sessions = tuple(
                QuoteSession(
                    weekday=row["weekday"],
                    start_seconds_server=int(row["start_seconds_server"]),
                    end_seconds_server=int(row["end_seconds_server"]),
                )
                for row in rows
                if row.get("session_kind") == "QUOTE"
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigurationError(
                "El archivo de sesiones MT5 contiene valores inválidos"
            ) from exc
        if not sessions:
            raise ConfigurationError(
                "El archivo de sesiones MT5 no contiene sesiones de cotización"
            )
        return cls.from_periods(
            (
                QuoteSessionPeriod(
                    sessions=sessions,
                    server_utc_offset=server_time - generated_utc,
                    effective_from_utc=generated_utc,
                ),
            ),
            generated_utc,
        )

    # Indica si el símbolo debería estar cerrado según la sesión de cotización vigente.
    def is_expected_market_closed(self, instant_utc: datetime) -> bool:
        period = self._period_for(instant_utc)
        server_time = instant_utc.astimezone(UTC) + period.server_utc_offset
        seconds = server_time.hour * 3600 + server_time.minute * 60 + server_time.second
        weekday = server_time.strftime("%A").upper()
        return not any(
            session.weekday == weekday and _contains_second(session, seconds)
            for session in period.sessions
        )

    # Determina si cada minuto ausente coincide con un cierre conocido de MT5.
    def is_expected_gap(self, previous_open: datetime, next_open: datetime) -> bool:
        if next_open <= previous_open + timedelta(minutes=1):
            return False
        cursor = previous_open + timedelta(minutes=1)
        while cursor < next_open:
            if not self.is_expected_market_closed(cursor):
                return False
            cursor += timedelta(minutes=1)
        return True

    # Selecciona el horario vigente e impide inventar horarios para períodos no documentados.
    def _period_for(self, instant_utc: datetime) -> QuoteSessionPeriod:
        for period in self._periods:
            if period.contains(instant_utc):
                return period
        raise ConfigurationError(
            "No existe un horario MT5 documentado para el instante solicitado; "
            "exporte o registre el período"
        )


# Comprueba si un segundo de la hora del servidor pertenece a una sesión exportada.
def _contains_second(session: QuoteSession, second: int) -> bool:
    if session.end_seconds_server == 0:
        return second >= session.start_seconds_server
    return session.start_seconds_server <= second < session.end_seconds_server


# Rechaza horarios contradictorios, períodos solapados y sesiones con segundos inválidos.
def _validate_periods(periods: tuple[QuoteSessionPeriod, ...]) -> None:
    previous_end: datetime | None = None
    for period in periods:
        if period.effective_until_utc and period.effective_until_utc <= period.effective_from_utc:
            raise ConfigurationError("Un período de sesiones tiene vigencia inválida")
        if previous_end and period.effective_from_utc < previous_end:
            raise ConfigurationError("Los períodos de sesiones se solapan")
        for session in period.sessions:
            if not 0 <= session.start_seconds_server < 86_400:
                raise ConfigurationError("La sesión contiene inicio inválido")
            if not 0 <= session.end_seconds_server < 86_400:
                raise ConfigurationError("La sesión contiene cierre inválido")
            if (
                session.end_seconds_server
                and session.end_seconds_server <= session.start_seconds_server
            ):
                raise ConfigurationError("La sesión contiene un intervalo inválido")
        previous_end = period.effective_until_utc
