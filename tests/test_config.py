from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from xau_collector.config import load_settings
from xau_collector.errors import ConfigurationError

VALID_CONFIG = """
[mt5]
terminal_path = ""
initialize_timeout_ms = 60000
[symbol]
logical_name = "XAUUSD"
aliases = ["XAUUSD", "GOLD"]
real_name = ""
[discovery]
recent_bars = 100
timeframe = "M1"
[output]
reports_directory = "reports"
"""


# Verifica que la configuración TOML se convierta en valores seguros y válidos.
class SettingsTests(unittest.TestCase):
    # Confirma que cadenas vacías opcionales se representen como ausencia de valor.
    def test_empty_optional_values_become_none(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(VALID_CONFIG, encoding="utf-8")
            settings = load_settings(path)

        self.assertIsNone(settings.mt5.terminal_path)
        self.assertIsNone(settings.symbol.real_name)
        self.assertEqual(settings.symbol.aliases, ("XAUUSD", "GOLD"))

    # Rechaza una configuración que solicite una cantidad inválida de velas recientes.
    def test_non_positive_recent_bars_is_rejected(self) -> None:
        invalid = VALID_CONFIG.replace("recent_bars = 100", "recent_bars = 0")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text(invalid, encoding="utf-8")
            with self.assertRaises(ConfigurationError):
                load_settings(path)


if __name__ == "__main__":
    unittest.main()
