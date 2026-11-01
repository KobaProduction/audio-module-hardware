"""Pure HAL source-to-descriptor checks; no physical device is accessed."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from builder.profile import load_target
from hal.manifest import CapabilityError, compile_manifest, write_manifest

TARGET = load_target("capsula-mini-native")
DEVICE_DIR = Path(__file__).resolve().parents[1] / "builder/devices/capsula-mini-native"


class HalContractTests(unittest.TestCase):
    def test_capsula_descriptor_distinguishes_unknown_counts(self) -> None:
        m = compile_manifest(TARGET)
        self.assertEqual(m["version"], 1)
        self.assertEqual(m["origin"], "builder-declared")
        self.assertIs(m["runtime_verified"], False)
        cap = {c["id"]: c for c in m["capabilities"]}
        self.assertNotIn("light.ring", cap)
        self.assertNotIn("audio.playback.spdif", cap)
        self.assertEqual(cap["display.front"]["properties"]["digits"], 4)
        self.assertIsNone(cap["audio.capture.pdm"]["properties"]["physical_microphones"])
        self.assertIsNone(cap["audio.capture.pdm"]["properties"]["capture_channels"])
        self.assertIsNone(cap["audio.playback.speaker"]["properties"]["physical_speakers"])
        self.assertIsNone(cap["audio.playback.speaker"]["properties"]["playback_channels"])

    def test_optional_component_removal_changes_emitted_capabilities(self) -> None:
        p = copy.deepcopy(TARGET)
        p["firmware"]["components"] = ["base", "audio"]
        m = compile_manifest(p)
        cap = {c["id"] for c in m["capabilities"]}
        self.assertIn("display.front", cap)
        self.assertIn("audio.capture.pdm", cap)
        self.assertNotIn("network.bluetooth", cap)
        self.assertNotIn("network.wifi", cap)

    def test_future_pixel_display_with_one_mic_without_other_features(self) -> None:
        # A synthetic product variant only; not a real supported device.
        p = copy.deepcopy(TARGET)
        p["id"] = "fictional-one-mic-display"
        p["firmware"]["components"] = ["base", "audio"]
        p["hal"]["enabled_capabilities"] = ["audio.capture.front", "display.main"]
        data = {
            "schema": 1, "device": p["id"],
            "capabilities": [
                {"id": "audio.capture.front", "kind": "audio.capture",
                 "component": "audio", "support": "declared", "provider": "alsa",
                 "actions": ["stream"],
                 "properties": {"physical_microphones": 1, "capture_channels": 2}},
                {"id": "display.main", "kind": "display.pixel", "component": "base",
                 "support": "declared", "provider": "drm", "actions": ["pixels"],
                 "properties": {"width": 128, "height": 64}},
                {"id": "light.ring", "kind": "light.addressable", "component": "base",
                 "support": "planned", "provider": "unresolved",
                 "actions": ["color"], "properties": {"pixels": None}},
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "capabilities.json").write_text(json.dumps(data))
            result = compile_manifest(p, folder)
        caps = {r["id"]: r for r in result["capabilities"]}
        self.assertEqual(len(caps), 2)
        self.assertEqual(caps["audio.capture.front"]["properties"]["physical_microphones"], 1)
        self.assertEqual(caps["audio.capture.front"]["properties"]["capture_channels"], 2)
        self.assertEqual(caps["display.main"]["properties"]["width"], 128)

    def test_duplicate_and_unsafe_capabilities_are_rejected(self) -> None:
        p = copy.deepcopy(TARGET)
        raw = json.loads((DEVICE_DIR / "capabilities.json").read_text())
        raw["capabilities"].append(copy.deepcopy(raw["capabilities"][0]))
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            source = d / "capabilities.json"
            source.write_text(json.dumps(raw))
            with self.assertRaisesRegex(CapabilityError, "Duplicate"):
                compile_manifest(p, d)
            raw["capabilities"][-1]["id"] = "../shell"
            source.write_text(json.dumps(raw))
            with self.assertRaisesRegex(CapabilityError, "Invalid stable"):
                compile_manifest(p, d)
            raw["capabilities"][-1]["id"] = "audio.capture.copy"
            raw["capabilities"][-1]["actions"] = [["shell"]]
            source.write_text(json.dumps(raw))
            with self.assertRaisesRegex(CapabilityError, "action"):
                compile_manifest(p, d)

    def test_bad_physical_count_and_unknown_provider_are_rejected(self) -> None:
        raw = json.loads((DEVICE_DIR / "capabilities.json").read_text())
        raw["capabilities"][0]["properties"]["physical_microphones"] = 0
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            source = d / "capabilities.json"
            source.write_text(json.dumps(raw))
            with self.assertRaisesRegex(CapabilityError, "physical_microphones"):
                compile_manifest(TARGET, d)
            raw["capabilities"][0]["properties"]["physical_microphones"] = 4
            raw["capabilities"][0]["provider"] = "run-custom-shell"
            source.write_text(json.dumps(raw))
            with self.assertRaisesRegex(CapabilityError, "Linux provider"):
                compile_manifest(TARGET, d)

    def test_explicitly_disabled_display_does_not_appear(self) -> None:
        p = copy.deepcopy(TARGET)
        p["hal"]["enabled_capabilities"].remove("display.front")
        compiled = compile_manifest(p)
        self.assertNotIn("display.front", [x["id"] for x in compiled["capabilities"]])
        self.assertIn("input.touch", [x["id"] for x in compiled["capabilities"]])

    def test_planned_ring_may_not_be_enabled_by_builder(self) -> None:
        p = copy.deepcopy(TARGET)
        p["hal"]["enabled_capabilities"].append("light.ring")
        with self.assertRaisesRegex(CapabilityError, "unimplemented"):
            compile_manifest(p)

    def test_rootfs_contains_statically_declared_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = write_manifest(TARGET, Path(tmp))
            self.assertEqual(
                path.relative_to(tmp).as_posix(),
                "usr/share/audio-module/capabilities-v1.json",
            )
            payload = json.loads(path.read_text())
            self.assertIs(payload["runtime_verified"], False)
            self.assertEqual(payload["device"], TARGET["id"])


if __name__ == "__main__":
    unittest.main()
