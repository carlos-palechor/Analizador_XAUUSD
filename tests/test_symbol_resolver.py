from __future__ import annotations

import unittest

from xau_collector.domain.models import SymbolDescriptor
from xau_collector.errors import SymbolResolutionError
from xau_collector.services.symbol_resolver import SymbolResolver


# Construye un descriptor mínimo de símbolo para aislar las pruebas del resolutor.
def symbol(name: str, description: str = "") -> SymbolDescriptor:
    return SymbolDescriptor(name, description, "", 2, 0.01, "XAU", "USD", 100.0, True)


# Verifica que el resolutor elija símbolos válidos y rechace ambigüedades.
class SymbolResolverTests(unittest.TestCase):
    # Prepara un resolutor independiente para cada escenario de prueba.
    def setUp(self) -> None:
        self.resolver = SymbolResolver()

    # Da prioridad a un alias que coincide exactamente con el nombre de símbolo.
    def test_prefers_exact_alias(self) -> None:
        result = self.resolver.resolve(
            [symbol("XAUUSDm", "Gold"), symbol("XAUUSD", "Gold")],
            "XAUUSD",
            ("XAUUSD", "GOLD"),
            None,
        )
        self.assertEqual(result.name, "XAUUSD")

    # Permite resolver el sufijo que añade un bróker al símbolo lógico.
    def test_resolves_broker_suffix(self) -> None:
        result = self.resolver.resolve(
            [symbol("EURUSD"), symbol("XAUUSDm", "Gold versus US Dollar")],
            "XAUUSD",
            ("XAUUSD", "GOLD"),
            None,
        )
        self.assertEqual(result.name, "XAUUSDm")

    # Rechaza dos candidatos con la misma puntuación para evitar elegir al azar.
    def test_rejects_equal_score_ambiguity(self) -> None:
        with self.assertRaises(SymbolResolutionError):
            self.resolver.resolve(
                [symbol("XAUUSD.a", "Gold"), symbol("XAUUSD.b", "Gold")],
                "XAUUSD",
                ("XAUUSD",),
                None,
            )


if __name__ == "__main__":
    unittest.main()
