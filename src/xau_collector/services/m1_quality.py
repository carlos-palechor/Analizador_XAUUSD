from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from xau_collector.domain.models import M1Bar
from xau_collector.services.session_calendar import XauUsdWeekendSession


@dataclass(frozen=True, slots=True)
# Describe un intervalo sin velas y si el calendario lo considera esperado.
class GapFinding:
    previous_open_utc: datetime
    next_open_utc: datetime
    missing_minutes: int
    expected_market_closed: bool


@dataclass(frozen=True, slots=True)
# Reúne los conteos y hallazgos de calidad de un conjunto de velas M1.
class QualitySummary:
    invalid_bar_count: int
    duplicate_count: int
    out_of_order_count: int
    expected_gap_count: int
    unexpected_gap_count: int
    last_open_utc: datetime | None
    gaps: tuple[GapFinding, ...]


# Valida coherencia OHLC, duplicados y huecos de las velas M1 recibidas.
class M1QualityValidator:
    # Conserva el calendario de sesiones necesario para clasificar huecos temporales.
    def __init__(self, sessions: XauUsdWeekendSession) -> None:
        self._sessions = sessions

    # Revisa las velas y devuelve un resumen de inconsistencias y huecos encontrados.
    def validate(
        self, bars: tuple[M1Bar, ...], previous_last_open: datetime | None = None
    ) -> QualitySummary:
        invalid = 0
        duplicates = 0
        out_of_order = 0
        expected_gaps = 0
        unexpected_gaps = 0
        gaps: list[GapFinding] = []
        previous = previous_last_open
        for bar in bars:
            if not self._is_valid_bar(bar):
                invalid += 1
            if previous is not None:
                difference_seconds = (bar.open_time_utc - previous).total_seconds()
                if difference_seconds == 0:
                    duplicates += 1
                elif difference_seconds < 0:
                    out_of_order += 1
                elif difference_seconds > 60:
                    expected = self._sessions.is_expected_gap(previous, bar.open_time_utc)
                    gaps.append(
                        GapFinding(
                            previous_open_utc=previous,
                            next_open_utc=bar.open_time_utc,
                            missing_minutes=int(difference_seconds // 60) - 1,
                            expected_market_closed=expected,
                        )
                    )
                    if expected:
                        expected_gaps += 1
                    else:
                        unexpected_gaps += 1
            previous = bar.open_time_utc
        return QualitySummary(
            invalid_bar_count=invalid,
            duplicate_count=duplicates,
            out_of_order_count=out_of_order,
            expected_gap_count=expected_gaps,
            unexpected_gap_count=unexpected_gaps,
            last_open_utc=previous,
            gaps=tuple(gaps),
        )

    @staticmethod
    # Comprueba que precios, spread y volúmenes de una vela tengan valores coherentes.
    def _is_valid_bar(bar: M1Bar) -> bool:
        return (
            bar.high >= max(bar.open, bar.close)
            and bar.low <= min(bar.open, bar.close)
            and bar.high >= bar.low
            and bar.spread_points >= 0
            and bar.tick_volume >= 0
            and bar.real_volume >= 0
        )
