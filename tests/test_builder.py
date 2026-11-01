"""Offline acceptance for source-based firmware staging; no hardware writes."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.profile import ProfileError, artifact_fits, load_target, validate_target
from scripts import build


class ProfileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_target("capsula-mini-native")

    def test_soc_and_pinned_source(self) -> None:
        self.assertEqual(self.profile["soc"], "amlogic-a113x")
        self.assertEqual(len(self.profile["kernel"]["revision"]), 40)
        self.assertFalse(self.profile["application"]["enabled"])
        self.assertEqual(self.profile["bootloader"]["mode"], "retain-vendor")

    def test_invalid_unsafe_target_paths(self) -> None:
        for value in ("../secret", "AA", "capsula/mini"):
            with self.assertRaises(ProfileError):
                load_target(value)

    def test_protected_region_must_not_overlap(self) -> None:
        changed = copy.deepcopy(self.profile)
        changed["nand"]["protected_until"] -= 131072
        with self.assertRaisesRegex(ProfileError, "unsafe NAND"):
            validate_target(changed)

    def test_erase_alignment_mandatory(self) -> None:
        changed = copy.deepcopy(self.profile)
        changed["nand"]["dtb_offset"] += 2048
        with self.assertRaisesRegex(ProfileError, "eraseblock aligned"):
            validate_target(changed)

    def test_vendor_bootloader_is_protected(self) -> None:
        changed = copy.deepcopy(self.profile)
        changed["bootloader"]["mode"] = "replace"
        with self.assertRaisesRegex(ProfileError, "forbidden"):
            validate_target(changed)

    def test_artifact_capacity_enforced(self) -> None:
        self.assertTrue(artifact_fits(self.profile, "Image", 16715784))
        self.assertFalse(artifact_fits(self.profile, "Image", 27000000))
        self.assertFalse(artifact_fits(self.profile, "ubi", 240000000))


class BuildTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = load_target("capsula-mini-native")

    def test_official_sources_pinned(self) -> None:
        for item in ("minirootfs", "host_apk_static"):
            source = build.SOURCES[item]
            self.assertTrue(source["url"].startswith("https://"))
            self.assertEqual(len(source["sha256"]), 64)
        self.assertNotIn("allow-untrusted", (ROOT / "scripts/build.py").read_text())

    def test_cached_download_hash_protected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "cached.tar"
            p.write_bytes(b"not-an-image")
            with self.assertRaisesRegex(build.BuildError, "Cached source hash mismatch"):
                build.verified_fetch({"url": "https://example.com/valid",
                                      "sha256": "1" * 64}, p)
            self.assertEqual(p.read_bytes(), b"not-an-image")

    def test_board_overlay_not_global(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "etc").mkdir()
            (root / "etc/inittab").write_text("# base\n")
            with self.assertRaises(FileNotFoundError):
                build.apply_overlay(self.profile, root, root / "missing.key")
            self.assertIn("SaeDisable=*", (root / "etc/iwd/main.conf").read_text())
            self.assertIn("ttyGS0", (root / "etc/inittab").read_text())
            self.assertFalse((root / "root/.ssh/authorized_keys").exists())

    def test_public_key_injection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "rootfs"
            root.mkdir()
            public = Path(td) / "test.pub"
            public.write_text("ssh-ed25519 " + "a" * 50 + " test-only\n")
            build.apply_overlay(self.profile, root, public)
            self.assertEqual((root / "root/.ssh/authorized_keys").stat().st_mode & 0o777, 0o600)

    def test_manifest_from_synthetic_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            images = Path(td) / "images"
            images.mkdir()
            (images / "Image").write_bytes(b"\0" * 56 + b"ARM\x64" + b"\0" * 8)
            (images / "board.dtb").write_bytes(bytes.fromhex("d00dfeed") + b"\0" * 40)
            (images / "rootfs.ubi").write_bytes(b"UBI#" + b"\0" * 40)
            build.package_manifest(self.profile, Path(td))
            data = json.loads((images / "manifest.json").read_text())
            self.assertEqual(data["status"], "NOT_HARDWARE_VALIDATED")
            self.assertFalse(data["application_included"])
            self.assertEqual(data["artifacts"]["Image"]["sha256"],
                             hashlib.sha256((images / "Image").read_bytes()).hexdigest())

    def test_empty_application_is_not_added(self) -> None:
        self.assertEqual(self.profile["application"]["enabled"], False)
        self.assertNotIn("audio-module-application", (ROOT / "scripts/build.py").read_text())


if __name__ == "__main__":
    unittest.main()
