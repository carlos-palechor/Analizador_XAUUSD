from __future__ import annotations

import unittest
from pathlib import Path

from xau_collector.cli import _parser


# Garantiza que la validación final de PostgreSQL esté expuesta por la consola del proyecto.
class CliValidationStageTests(unittest.TestCase):
    # Acepta el corte UTC y la raíz de históricos requeridos para la validación integral.
    def test_accepts_postgres_validation_command(self) -> None:
        arguments = _parser().parse_args(
            [
                "validate-postgres-stage",
                "--root",
                "data/raw",
                "--at",
                "2026-10-30T20:00",
            ]
        )

        self.assertEqual(arguments.command, "validate-postgres-stage")
        self.assertEqual(arguments.root, Path("data/raw"))
        self.assertEqual(arguments.at, "2026-10-30T20:00")


if __name__ == "__main__":
    unittest.main()
