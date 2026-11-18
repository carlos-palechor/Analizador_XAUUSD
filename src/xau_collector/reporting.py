from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


# Convierte un resultado estructurado en JSON legible para consola o archivo.
def render_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


# Guarda un reporte JSON de forma atómica para evitar archivos parcialmente escritos.
def write_json_report(payload: Mapping[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".partial")
    temporary.write_text(render_json(payload) + "\n", encoding="utf-8")
    temporary.replace(destination)
