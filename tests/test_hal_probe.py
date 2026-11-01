"""Read-only sysfs probes never promote declared status without evidence."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from builder.profile import load_target
from hal.manifest import compile_manifest
from hal.probe import inspect


class HalProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.descriptor = compile_manifest(load_target("capsula-mini-native"))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.sys = Path(self.temp.name)

    def test_no_sysfs_keeps_all_declared_features_unknown(self) -> None:
        outcome = inspect(self.descriptor, self.sys)
        self.assertFalse(outcome["all_hardware_verified"])
        self.assertTrue(outcome["capabilities"])
        self.assertTrue(all(x["state"] == "unknown" for x in outcome["capabilities"]))

    def test_matches_verified_kernel_input_and_iio_names_only(self) -> None:
        iio = self.sys / "bus/iio/devices/iio:device8/name"
        iio.parent.mkdir(parents=True)
        iio.write_text("bh1730\n")
        touch = self.sys / "class/input/input13/name"
        touch.parent.mkdir(parents=True)
        touch.write_text("Hynitron CSK05T\n")
        outcome = inspect(self.descriptor, self.sys)
        by_id = {x["id"]: x for x in outcome["capabilities"]}
        self.assertEqual(by_id["sensor.ambient"]["state"], "available")
        self.assertEqual(by_id["input.touch"]["state"], "available")
        self.assertEqual(by_id["display.front"]["state"], "unknown")
        self.assertEqual(by_id["audio.playback.speaker"]["state"], "unknown")
        self.assertFalse(outcome["all_hardware_verified"])

    def test_broken_identity_does_not_claim_available(self) -> None:
        iio = self.sys / "bus/iio/devices/iio:device2/name"
        iio.parent.mkdir(parents=True)
        iio.write_text("other-sensor\n")
        outcome = inspect(self.descriptor, self.sys)
        state = {x["id"]: x["state"] for x in outcome["capabilities"]}
        self.assertEqual(state["sensor.ambient"], "unknown")

    def test_reject_unverified_input_descriptor(self) -> None:
        invalid = json.loads(json.dumps(self.descriptor))
        invalid["runtime_verified"] = True
        with self.assertRaisesRegex(ValueError, "misleading"):
            inspect(invalid, self.sys)


if __name__ == "__main__":
    unittest.main()
