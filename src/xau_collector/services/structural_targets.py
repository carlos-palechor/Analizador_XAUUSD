from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from xau_collector.services.consolidation_poi import ConsolidationPoi
from xau_collector.services.key_levels import PeriodRange


# Representa un posible destino estructural por encima o debajo del precio actual.
@dataclass(frozen=True, slots=True)
class StructuralTarget:
    source: str
    price: float
    direction: str
    distance: float


# Ordena niveles y zonas para mostrar próximos destinos, sin emitir una predicción.
class StructuralTargetMapper:
    # Construye objetivos superiores e inferiores a partir de niveles y límites de zonas.
    def map(
        self,
        current_price: float,
        levels: Iterable[PeriodRange],
        zones: Iterable[ConsolidationPoi],
    ) -> tuple[tuple[StructuralTarget, ...], tuple[StructuralTarget, ...]]:
        candidates = [
            *(
                StructuralTarget(
                    level.timeframe,
                    price,
                    "ARRIBA" if price > current_price else "ABAJO",
                    abs(price - current_price),
                )
                for level in levels
                for price in (level.high, level.low)
                if price != current_price
            ),
            *(
                StructuralTarget(
                    "CONSOLIDACION",
                    price,
                    "ARRIBA" if price > current_price else "ABAJO",
                    abs(price - current_price),
                )
                for zone in zones
                for price in (zone.high, zone.low)
                if price != current_price
            ),
        ]
        above = tuple(
            sorted(
                (item for item in candidates if item.direction == "ARRIBA"),
                key=lambda item: item.distance,
            )
        )
        below = tuple(
            sorted(
                (item for item in candidates if item.direction == "ABAJO"),
                key=lambda item: item.distance,
            )
        )
        return above, below
