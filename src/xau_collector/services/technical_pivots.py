from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from xau_collector.services.technical_structure_types import PriceBar


# Representa un máximo o mínimo que quedó confirmado por velas posteriores.
@dataclass(frozen=True, slots=True)
class StructuralPivot:
    kind: str
    price: float
    open_time_utc: datetime


# Obtiene máximos estructurales confirmados usando el radio de velas indicado.
def swing_highs(bars: Sequence[PriceBar], radius: int) -> list[StructuralPivot]:
    return pivots(bars, radius, "HIGH")


# Obtiene mínimos estructurales confirmados usando el radio de velas indicado.
def swing_lows(bars: Sequence[PriceBar], radius: int) -> list[StructuralPivot]:
    return pivots(bars, radius, "LOW")


# Construye pivotes sin usar velas posteriores que aún no existían en el corte analizado.
def pivots(bars: Sequence[PriceBar], radius: int, kind: str) -> list[StructuralPivot]:
    results: list[StructuralPivot] = []
    for index in range(radius, len(bars) - radius):
        current = bars[index]
        neighbours = bars[index - radius : index] + bars[index + 1 : index + radius + 1]
        price = current.high if kind == "HIGH" else current.low
        compared = [bar.high if kind == "HIGH" else bar.low for bar in neighbours]
        valid = (
            all(price > other for other in compared)
            if kind == "HIGH"
            else all(price < other for other in compared)
        )
        if valid:
            results.append(StructuralPivot(kind, price, current.open_time_utc))
    return results
