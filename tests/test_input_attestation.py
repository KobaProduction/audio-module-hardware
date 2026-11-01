"""Offline attestation tests; no device secrets or network access."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder import build, input_attestation as att  # noqa: E402
from builder.profile import load_target  # noqa: E402


class InputAttestationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_target("capsula-mini-native")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.inputs = self.home / "project"
        self.inputs.mkdir()
        for p in att._source_paths(self.profile, ROOT):
            destination = self.inputs / p.relative_to(ROOT)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, destination)
        self.work = self.home / "stage"
        self.rootfs = self.work / "rootfs"
        db = self.rootfs / "lib/apk/db/installed"
        db.parent.mkdir(parents=True)
        db.write_text("P:busybox\nV:1.37.0-r1\nF:bin\nR:busybox\n\nP:openssl\nV:3.5.0-r0\n\n")

    def test_input_hash_is_deterministic_and_overlay_aware(self) -> None:
        initial = att.build_inputs(self.profile, root=self.inputs)
        self.assertEqual(initial, att.build_inputs(self.profile, root=self.inputs))
        overlay = self.inputs / "builder/devices/capsula-mini-native/overlay/etc/hostname"
        overlay.write_text("changed-hostname\n")
        self.assertNotEqual(initial, att.build_inputs(self.profile, root=self.inputs))

    def test_builder_code_change_also_invalidates_attestation(self) -> None:
        previous = att.build_inputs(self.profile, root=self.inputs)
        code = self.inputs / "hal/manifest.py"
        code.write_text(code.read_text() + "\n# source change\n")
        self.assertNotEqual(previous, att.build_inputs(self.profile, root=self.inputs))

    def test_package_inventory_includes_resolved_versions(self) -> None:
        self.assertEqual(att.installed_packages(self.rootfs), [
            {"name": "busybox", "version": "1.37.0-r1"},
            {"name": "openssl", "version": "3.5.0-r0"},
        ])

    def test_capture_and_verify_fail_on_source_drift(self) -> None:
        record = att.capture_stage(self.profile, self.work, self.rootfs, root=self.inputs)
        self.assertFalse(record["alpine_package_versions_locked"])
        self.assertEqual(att.verify_stage(self.profile, self.work, self.rootfs,
                                          root=self.inputs), record)
        overlay = self.inputs / "firmware/alpine/overlay/etc/init.d/usbgadget"
        overlay.write_text(overlay.read_text() + "\n# mutated\n")
        with self.assertRaisesRegex(att.InputAttestationError, "changed since"):
            att.verify_stage(self.profile, self.work, self.rootfs, root=self.inputs)

    def test_drifted_installed_package_set_is_rejected(self) -> None:
        att.capture_stage(self.profile, self.work, self.rootfs, root=self.inputs)
        db = self.rootfs / "lib/apk/db/installed"
        db.write_text(db.read_text() + "P:tampered\nV:1.0-r0\n\n")
        with self.assertRaisesRegex(att.InputAttestationError, "package set changed"):
            att.verify_stage(self.profile, self.work, self.rootfs, root=self.inputs)

    def test_missing_attestation_and_duplicate_capture_fail_closed(self) -> None:
        with self.assertRaisesRegex(att.InputAttestationError, "No successful"):
            att.verify_stage(self.profile, self.work, self.rootfs, root=self.inputs)
        att.capture_stage(self.profile, self.work, self.rootfs, root=self.inputs)
        with self.assertRaisesRegex(att.InputAttestationError, "refusing implicit overwrite"):
            att.capture_stage(self.profile, self.work, self.rootfs, root=self.inputs)

    def test_malformed_duplicate_installed_package_rejected(self) -> None:
        db = self.rootfs / "lib/apk/db/installed"
        db.write_text("P:busybox\nV:1-r0\n\nP:busybox\nV:2-r0\n\n")
        with self.assertRaisesRegex(att.InputAttestationError, "duplicated"):
            att.installed_packages(self.rootfs)

    def test_overlay_symlink_rejected_before_hashing(self) -> None:
        link = self.inputs / "firmware/alpine/overlay/invalid-link"
        link.symlink_to(self.home / "arbitrary-outside-file")
        with self.assertRaisesRegex(att.InputAttestationError, "symlink"):
            att.build_inputs(self.profile, root=self.inputs)

    def test_image_phase_rejects_missing_stamp_before_external_tools(self) -> None:
        with self.assertRaisesRegex(att.InputAttestationError, "No successful"):
            build.pack_images(self.profile, self.work)

    def test_no_dist_upgrade_and_no_provisioning_key_in_attestation(self) -> None:
        record = att.capture_stage(self.profile, self.work, self.rootfs, root=self.inputs)
        self.assertEqual(record["target"], "capsula-mini-native")
        self.assertEqual(record["kernel_revision"], self.profile["kernel"]["revision"])
        self.assertNotIn("password", json.dumps(record))
        self.assertNotIn("authorized_keys", json.dumps(record))
        self.assertNotIn("openwrt", json.dumps(record))


if __name__ == "__main__":
    unittest.main()
