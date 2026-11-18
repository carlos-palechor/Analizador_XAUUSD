from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from xau_collector.services.consolidation_poi import ConsolidationPoi


# Relaciona una zona menor con la zona mayor dentro de la cual negocia el precio.
@dataclass(frozen=True, slots=True)
class ConsolidationRelationship:
    child_timeframe: str
    parent_timeframe: str
    child: ConsolidationPoi
    parent: ConsolidationPoi
    relation: str


# Vincula consolidaciones H4/H1/M15/M5 sin alterar sus reglas de detección.
class ConsolidationContextBuilder:
    # Relaciona cada zona hija con todas las zonas mayores que la contienen o solapan.
    def build(
        self,
        h4: Sequence[ConsolidationPoi],
        h1: Sequence[ConsolidationPoi],
        m15: Sequence[ConsolidationPoi],
        m5: Sequence[ConsolidationPoi],
    ) -> tuple[ConsolidationRelationship, ...]:
        relationships = [
            *_relationships(h1, h4, "H1", "H4"),
            *_relationships(m15, h1, "M15", "H1"),
            *_relationships(m5, m15, "M5", "M15"),
        ]
        return tuple(relationships)


# Clasifica contención o solape de dos zonas de precio sin decidir una estrategia.
def _relationships(
    children: Sequence[ConsolidationPoi],
    parents: Sequence[ConsolidationPoi],
    child_timeframe: str,
    parent_timeframe: str,
) -> list[ConsolidationRelationship]:
    result: list[ConsolidationRelationship] = []
    for child in children:
        for parent in parents:
            if child.low >= parent.low and child.high <= parent.high:
                result.append(
                    ConsolidationRelationship(
                        child_timeframe, parent_timeframe, child, parent, "CONTENIDA"
                    )
                )
            elif child.low <= parent.high and child.high >= parent.low:
                result.append(
                    ConsolidationRelationship(
                        child_timeframe, parent_timeframe, child, parent, "SOLAPADA"
                    )
                )
    return result
