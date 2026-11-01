"""Prevent accidental distro-port work in an architecture-only reference."""
from __future__ import annotations

import unittest
from pathlib import Path

from builder.profile import load_target

ROOT = Path(__file__).resolve().parents[1]


class ArchitectureReferenceTests(unittest.TestCase):
    def test_openwrt_is_not_a_builder_or_firmware_provider(self) -> None:
        self.assertFalse((ROOT / "builder/openwrt.py").exists())
        self.assertFalse((ROOT / "firmware/openwrt").exists())
        self.assertFalse((ROOT / "builder/devices/capsula-mini-native/openwrt-port.json").exists())
        source = (ROOT / "builder/build.py").read_text(encoding="utf-8")
        self.assertNotIn('"openwrt-plan"', source)
        self.assertNotIn("plan_openwrt", source)

    def test_current_os_and_boot_chain_unchanged(self) -> None:
        target = load_target("capsula-mini-native")
        self.assertEqual(target["os"]["distribution"], "alpine")
        self.assertEqual(target["bootloader"]["mode"], "retain-vendor")
        self.assertEqual(target["nand"]["protected_until"], 0x01200000)
        self.assertEqual(target["nand"]["ubi_offset"], 0x02c00000)

    def test_architecture_document_explicitly_rejects_os_port(self) -> None:
        text = (ROOT / "docs/ARCHITECTURE_REFERENCES.md").read_text(encoding="utf-8")
        self.assertIn("not as a target", text)
        self.assertIn("No OS migration or OpenWrt A113X port", text)
        self.assertIn("firmware/alpine/components.json", text)
        project_rules = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("architecture/development-workflow reference ONLY", project_rules)


if __name__ == "__main__":
    unittest.main()
