"""Offline gates for a source-pinned, non-installable OpenWrt research lane."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.openwrt import (  # noqa: E402
    OpenWrtPortError, SOURCE_MANIFEST, plan_openwrt, validate_source_pins,
)
from builder.profile import load_target  # noqa: E402


class OpenWrtPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = load_target("capsula-mini-native")
        self.sources = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))

    def test_pinned_source_and_all_feeds(self) -> None:
        validate_source_pins(self.sources)
        self.assertEqual(self.sources["upstream"]["tag"], "v25.12.6")
        self.assertEqual(self.sources["upstream"]["commit"],
                         "64900e756efa667774214f9c6b17c113222e01f7")
        self.assertEqual(set(feed["name"] for feed in self.sources["feeds"]),
                         {"packages", "luci", "routing", "telephony", "video"})

    def test_missing_feed_commit_fails_closed(self) -> None:
        bad = copy.deepcopy(self.sources)
        bad["feeds"][0]["commit"] = "main"
        with self.assertRaisesRegex(OpenWrtPortError, "Invalid or unpinned"):
            validate_source_pins(bad)

    def test_duplicate_or_untrusted_feed_fails_closed(self) -> None:
        bad = copy.deepcopy(self.sources)
        bad["feeds"][1]["name"] = bad["feeds"][0]["name"]
        with self.assertRaises(OpenWrtPortError):
            validate_source_pins(bad)
        bad = copy.deepcopy(self.sources)
        bad["feeds"][0]["repository"] = "http://example.com/feed"
        with self.assertRaises(OpenWrtPortError):
            validate_source_pins(bad)

    def test_read_only_plan_cannot_authorize_flash(self) -> None:
        report = plan_openwrt(self.target)
        self.assertEqual(report["status"], "RESEARCH_ONLY_NOT_BUILDABLE")
        self.assertEqual(report["proposed_target"], "amlogic/a113x")
        self.assertFalse(report["may_build_openwrt_image"])
        self.assertFalse(report["may_install"])
        self.assertFalse(report["may_sysupgrade"])
        self.assertTrue(report["physical_nand_layout_unchanged"])
        self.assertEqual(report["existing_os_unchanged"], "alpine")
        self.assertNotIn("ethaddr", json.dumps(report))
        self.assertNotIn("serial", json.dumps(report))

    def test_enabled_port_flags_rejected_before_any_build(self) -> None:
        from builder import openwrt
        original = json.loads(
            (ROOT / "builder/devices/capsula-mini-native/openwrt-port.json").read_text()
        )
        with patch.object(openwrt.Path, "read_text", autospec=True) as read:
            def staged(path, *args, **kwargs):
                if path == SOURCE_MANIFEST:
                    return json.dumps(self.sources)
                modified = dict(original, allow_sysupgrade=True)
                return json.dumps(modified)
            read.side_effect = staged
            with self.assertRaisesRegex(OpenWrtPortError, "cannot be enabled"):
                plan_openwrt(self.target)


if __name__ == "__main__":
    unittest.main()
