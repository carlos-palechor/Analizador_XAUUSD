from __future__ import annotations

import unittest
from datetime import UTC, datetime

from xau_collector.services.key_levels import PeriodRange
from xau_collector.services.structural_targets import StructuralTargetMapper


# Verifica que los objetivos se separen y ordenen respecto al precio actual.
class StructuralTargetMapperTests(unittest.TestCase):
    # Ordena primero el nivel superior e inferior que queda más cerca del precio.
    def test_orders_targets_above_and_below(self) -> None:
        levels = (
            PeriodRange("D1", datetime(2026, 1, 1, tzinfo=UTC), 110, 90),
            PeriodRange("W1", datetime(2026, 1, 1, tzinfo=UTC), 105, 80),
        )

        above, below = StructuralTargetMapper().map(100, levels, ())

        self.assertEqual([item.price for item in above], [105, 110])
        self.assertEqual([item.price for item in below], [90, 80])


if __name__ == "__main__":
    unittest.main()
