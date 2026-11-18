from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from xau_collector.infrastructure.postgres_technical_audit_store import (
    _parameters_hash,
    code_revision,
    snapshot_content_hash,
)


# Protege que los parámetros equivalentes produzcan la misma identidad auditable.
class TechnicalAuditStoreTests(unittest.TestCase):
    # El orden del diccionario no debe crear una versión diferente de reglas.
    def test_parameter_hash_is_stable(self) -> None:
        first = _parameters_hash({"h4": 180, "m5": 576})
        second = _parameters_hash({"m5": 576, "h4": 180})
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

    # Comprueba que el snapshot identifica valores OHLC y no solo la cantidad de velas.
    def test_snapshot_hash_changes_when_a_bar_price_changes(self) -> None:
        bars = _snapshot_bars_for_test()
        same_content = tuple(bars)
        corrected = list(bars)
        first = list(corrected[0])
        first[5] = Decimal("4155.000")
        corrected[0] = tuple(first)

        self.assertEqual(snapshot_content_hash(bars), snapshot_content_hash(same_content))
        self.assertNotEqual(snapshot_content_hash(bars), snapshot_content_hash(tuple(corrected)))

    # Garantiza una identidad reproducible del código aunque el proyecto no tenga Git disponible.
    def test_code_revision_is_stable_and_identified(self) -> None:
        first = code_revision()
        second = code_revision()

        self.assertEqual(first, second)
        self.assertTrue(first.startswith(("git:", "source-sha256:")))


# Construye velas completas y ordenadas para probar la identidad reproducible del snapshot.
def _snapshot_bars_for_test() -> tuple[tuple[object, ...], ...]:
    opened_at = datetime(2026, 10, 30, 12, tzinfo=UTC)
    return (
        (
            UUID("00000000-0000-0000-0000-000000000001"),
            "H1",
            opened_at,
            opened_at + timedelta(hours=1),
            Decimal("4150.000"),
            Decimal("4152.000"),
            Decimal("4148.000"),
            Decimal("4151.000"),
            100,
            0,
            20,
            1,
        ),
    )


if __name__ == "__main__":
    unittest.main()
