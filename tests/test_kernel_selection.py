"""Builder driver selection can disable optional kernel features."""
from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from builder.profile import load_target
from builder.kernel_config import (
    KernelConfigurationError, desired_symbols, write_config_overlay,
    assert_options_match,
)


class KernelSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_target("capsula-mini-native")

    def test_selected_capabilities_resolve_kernel_modules(self) -> None:
        symbols = desired_symbols(self.profile)
        self.assertEqual(symbols["CONFIG_W1_AML"], "m")
        self.assertEqual(symbols["CONFIG_BH1730"], "y")
        self.assertEqual(symbols["CONFIG_KEYBOARD_CSK05T"], "y")
        self.assertEqual(symbols["CONFIG_SND_SOC_NTP8918"], "y")
        self.assertEqual(symbols["CONFIG_EXTRA_FIRMWARE"], '"eq_8918.bin"')

    def test_disabling_optional_components_removes_driver_symbols(self) -> None:
        p = copy.deepcopy(self.profile)
        p["firmware"]["components"] = ["base", "ssh"]
        symbols = desired_symbols(p)
        self.assertEqual(symbols["CONFIG_W1_AML"], "n")
        self.assertEqual(symbols["CONFIG_SND_SOC_NTP8918"], "n")
        self.assertEqual(symbols["CONFIG_EXTRA_FIRMWARE"], '""')
        self.assertEqual(symbols["CONFIG_BT_HCIUART_AML"], "n")
        self.assertEqual(symbols["CONFIG_BH1730"], "y")

    def test_disable_display_without_disabling_base_alpine(self) -> None:
        p = copy.deepcopy(self.profile)
        p["hal"]["enabled_capabilities"].remove("display.front")
        symbols = desired_symbols(p)
        self.assertEqual(symbols["CONFIG_SEG_LED_CLASS"], "n")
        self.assertEqual(symbols["CONFIG_LEDS_IS31FL32XX"], "n")
        self.assertEqual(symbols["CONFIG_KEYBOARD_CSK05T"], "y")
        self.assertIn("base", p["firmware"]["components"])

    def test_config_overlay_and_validation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / ".config"
            config.write_text(
                "CONFIG_BH1730=y\nCONFIG_W1_AML=m\nCONFIG_OTHER=y\n",
                encoding="utf-8",
            )
            options = {"CONFIG_BH1730": "n", "CONFIG_W1_AML": "m",
                       "CONFIG_KEYBOARD_CSK05T": "y"}
            write_config_overlay(config, options)
            assert_options_match(config, options)
            self.assertIn("CONFIG_OTHER=y", config.read_text())
            self.assertIn("# CONFIG_BH1730 is not set", config.read_text())
            with self.assertRaisesRegex(KernelConfigurationError, "CONFIG_BH1730"):
                assert_options_match(config, {"CONFIG_BH1730": "y"})

    def test_kconfig_does_not_claim_a_driver_is_usable_from_source_only(self) -> None:
        # A configured driver may fail probe, so it cannot replace runtime HAL.
        selected = desired_symbols(self.profile)
        self.assertIsInstance(selected["CONFIG_BH1730"], str)
        self.assertNotIn("ringled", " ".join(selected))


if __name__ == "__main__":
    unittest.main()
