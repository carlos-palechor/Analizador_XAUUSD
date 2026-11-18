from __future__ import annotations

import unittest

from xau_collector.services.consolidation_poi import rules_for_timeframe


# Verifica que cada temporalidad tenga filtros de consolidación visibles y ajustables.
class ConsolidationRulesTests(unittest.TestCase):
    # H4/H1 requieren más duración que M15/M5 para representar una zona mayor.
    def test_uses_timeframe_specific_rules(self) -> None:
        h4 = rules_for_timeframe("H4")
        h1 = rules_for_timeframe("H1")
        m15 = rules_for_timeframe("M15")
        m5 = rules_for_timeframe("M5")

        self.assertGreaterEqual(h4.minimum_bars, h1.minimum_bars)
        self.assertGreater(h1.minimum_bars, m15.minimum_bars)
        self.assertGreater(m15.minimum_bars, m5.minimum_bars - 1)
        self.assertEqual(h4.minimum_boundary_touches, 3)
        self.assertEqual(m5.minimum_boundary_touches, 3)


if __name__ == "__main__":
    unittest.main()
