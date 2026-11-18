from __future__ import annotations

import unittest

from xau_collector.services.technical_alignment import TechnicalAlignment


# Verifica que el catálogo de alineación conserve todos los estados esperados.
class TechnicalAlignmentTests(unittest.TestCase):
    # Mantiene disponibles los estados que el cerebro técnico debe explicar.
    def test_defines_all_alignment_states(self) -> None:
        self.assertEqual(
            {item.value for item in TechnicalAlignment},
            {
                "ALINEADO_ALCISTA",
                "ALINEADO_BAJISTA",
                "NEUTRAL",
                "CONFLICTO_DE_TEMPORALIDADES",
                "BLOQUEADO",
            },
        )


if __name__ == "__main__":
    unittest.main()
