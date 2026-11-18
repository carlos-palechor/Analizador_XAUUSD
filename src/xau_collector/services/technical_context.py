from __future__ import annotations

from dataclasses import dataclass

from xau_collector.services.consolidation_context import ConsolidationRelationship
from xau_collector.services.consolidation_poi import ConsolidationPoiReport
from xau_collector.services.market_data_quality_brain import DataQualityBrainReport
from xau_collector.services.structural_targets import StructuralTarget
from xau_collector.services.technical_structure import (
    H1StructureReport,
    H4StructureReport,
    M5ObservationReport,
    M15PoiConfirmationReport,
)


# Reúne las respuestas técnicas para que el futuro cerebro líder las consulte juntas.
@dataclass(frozen=True, slots=True)
class TechnicalContext:
    data_quality: DataQualityBrainReport
    h4: H4StructureReport
    h1: H1StructureReport
    m15: M15PoiConfirmationReport
    m5: M5ObservationReport
    consolidations: ConsolidationPoiReport
    consolidation_relationships: tuple[ConsolidationRelationship, ...]
    targets_above: tuple[StructuralTarget, ...]
    targets_below: tuple[StructuralTarget, ...]


# Organiza contexto técnico sin emitir señales ni modificar decisiones de cada componente.
class TechnicalContextBuilder:
    # Construye un contexto inmutable a partir de resultados ya calculados.
    def build(
        self,
        data_quality: DataQualityBrainReport,
        h4: H4StructureReport,
        h1: H1StructureReport,
        m15: M15PoiConfirmationReport,
        m5: M5ObservationReport,
        consolidations: ConsolidationPoiReport,
        consolidation_relationships: tuple[ConsolidationRelationship, ...],
        targets_above: tuple[StructuralTarget, ...],
        targets_below: tuple[StructuralTarget, ...],
    ) -> TechnicalContext:
        return TechnicalContext(
            data_quality,
            h4,
            h1,
            m15,
            m5,
            consolidations,
            consolidation_relationships,
            targets_above,
            targets_below,
        )
