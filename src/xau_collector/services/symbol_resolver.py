from __future__ import annotations

import re
from collections.abc import Sequence

from xau_collector.domain.models import SymbolDescriptor
from xau_collector.errors import SymbolResolutionError


# Normaliza un nombre de símbolo para compararlo sin separadores ni mayúsculas.
def _normalized(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


# Selecciona un símbolo de bróker a partir de un nombre lógico, alias o nombre explícito.
class SymbolResolver:
    # Resuelve el símbolo más apropiado y rechaza coincidencias ambiguas.
    def resolve(
        self,
        symbols: Sequence[SymbolDescriptor],
        logical_name: str,
        aliases: tuple[str, ...],
        explicit_name: str | None,
    ) -> SymbolDescriptor:
        if explicit_name:
            return self._resolve_explicit(symbols, explicit_name)

        scored = sorted(
            ((self._score(symbol, logical_name, aliases), symbol) for symbol in symbols),
            key=lambda item: (-item[0], item[1].name),
        )
        candidates = [item for item in scored if item[0] > 0]
        if not candidates:
            raise SymbolResolutionError("No se encontró un símbolo candidato para XAUUSD")
        if len(candidates) > 1 and candidates[0][0] == candidates[1][0]:
            names = ", ".join(item[1].name for item in candidates if item[0] == candidates[0][0])
            raise SymbolResolutionError(
                f"La detección es ambigua ({names}); configure symbol.real_name"
            )
        return candidates[0][1]

    @staticmethod
    # Busca un símbolo configurado explícitamente sin aplicar puntuaciones.
    def _resolve_explicit(
        symbols: Sequence[SymbolDescriptor], explicit_name: str
    ) -> SymbolDescriptor:
        for symbol in symbols:
            if symbol.name.casefold() == explicit_name.casefold():
                return symbol
        raise SymbolResolutionError(f"El símbolo configurado no existe: {explicit_name}")

    @staticmethod
    # Puntúa un símbolo según coincidencia de nombre, descripción, moneda y visibilidad.
    def _score(symbol: SymbolDescriptor, logical_name: str, aliases: tuple[str, ...]) -> int:
        name = _normalized(symbol.name)
        normalized_aliases = {_normalized(logical_name), *map(_normalized, aliases)}
        score = 0
        if name in normalized_aliases:
            score += 100
        elif any(name.startswith(alias) for alias in normalized_aliases):
            score += 70
        elif any(alias in name for alias in normalized_aliases):
            score += 40
        description = symbol.description.casefold()
        if "gold" in description or "oro" in description:
            score += 25
        if symbol.currency_profit.upper() == "USD":
            score += 5
        if symbol.visible:
            score += 1
        return score
