from __future__ import annotations

import importlib.util
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path

from xau_collector import __version__
from xau_collector.config import AppSettings
from xau_collector.domain.models import CheckStatus, DiagnosticCheck, DoctorReport


# Comprueba que el entorno local pueda ejecutar el recolector de forma segura.
class DoctorService:
    # Ejecuta todas las comprobaciones previas y devuelve un reporte consolidado.
    def run(self, settings: AppSettings) -> DoctorReport:
        checks = (
            self._check_operating_system(),
            self._check_python(),
            self._check_metatrader_dependency(),
            self._check_terminal_path(settings),
            self._check_output_directory(settings),
        )
        return DoctorReport(datetime.now(UTC), __version__, checks)

    @staticmethod
    # Verifica que el sistema operativo y su arquitectura sean compatibles con MT5.
    def _check_operating_system() -> DiagnosticCheck:
        supported = platform.system() == "Windows" and platform.machine().upper() in {
            "AMD64",
            "X86_64",
        }
        return DiagnosticCheck(
            "operating_system",
            CheckStatus.PASS if supported else CheckStatus.FAIL,
            f"{platform.system()} {platform.machine()}",
        )

    @staticmethod
    # Verifica la versión de Python admitida por el proyecto actual.
    def _check_python() -> DiagnosticCheck:
        supported = sys.version_info[:2] == (3, 13)
        return DiagnosticCheck(
            "python",
            CheckStatus.PASS if supported else CheckStatus.FAIL,
            platform.python_version(),
        )

    @staticmethod
    # Verifica que el paquete oficial MetaTrader5 esté instalado en Python.
    def _check_metatrader_dependency() -> DiagnosticCheck:
        installed = importlib.util.find_spec("MetaTrader5") is not None
        return DiagnosticCheck(
            "metatrader5_package",
            CheckStatus.PASS if installed else CheckStatus.FAIL,
            "Instalado" if installed else "No instalado; instale el extra 'mt5'",
        )

    @staticmethod
    # Verifica la ruta configurada de la terminal o informa detección automática.
    def _check_terminal_path(settings: AppSettings) -> DiagnosticCheck:
        configured_path = settings.mt5.terminal_path
        if configured_path is None:
            return DiagnosticCheck(
                "terminal_path",
                CheckStatus.WARNING,
                "Detección automática solicitada",
            )
        exists = Path(configured_path).is_file()
        return DiagnosticCheck(
            "terminal_path",
            CheckStatus.PASS if exists else CheckStatus.FAIL,
            configured_path,
        )

    @staticmethod
    # Verifica que exista el directorio padre destinado a reportes.
    def _check_output_directory(settings: AppSettings) -> DiagnosticCheck:
        path = settings.output.reports_directory
        parent_exists = path.parent.exists()
        return DiagnosticCheck(
            "reports_directory",
            CheckStatus.PASS if parent_exists else CheckStatus.FAIL,
            str(path),
        )
