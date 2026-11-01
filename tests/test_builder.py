"""Offline acceptance for source-based firmware staging; no hardware writes."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import nullcontext
from unittest.mock import patch
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.profile import ProfileError, artifact_fits, load_target, validate_target
from builder import build


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

    def test_device_profile_contains_only_board_kernel_selection(self) -> None:
        source = json.loads(
            (ROOT / "builder/devices/capsula-mini-native/profile.json").read_text()
        )
        self.assertEqual(set(source["kernel"]), {"defconfig", "dtb", "runtime_firmware"})
        soc = json.loads(
            (ROOT / "kernel/platforms/amlogic-a113x.json").read_text()
        )
        self.assertEqual(source["soc"], soc["soc"])
        self.assertEqual(self.profile["kernel"]["revision"], soc["kernel"]["revision"])
        self.assertFalse((ROOT / "targets").exists())

    def test_platform_is_not_overridden_by_device(self) -> None:
        original = ROOT / "builder/devices/capsula-mini-native/profile.json"
        device = json.loads(original.read_text())
        self.assertNotIn("revision", device["kernel"])
        self.assertNotIn("source", device["kernel"])
        self.assertIn("revision", self.profile["kernel"])

    def test_device_overlay_and_source_separation(self) -> None:
        build_source = (ROOT / "builder/build.py").read_text()
        self.assertIn('ROOT / "builder" / "devices" / t["id"] / "overlay"', build_source)
        self.assertNotIn('ROOT / "targets"', build_source)
        self.assertNotIn("capsula-mini", (ROOT / "firmware/alpine/components.json").read_text())
        self.assertNotIn("capsula-mini", (ROOT / "firmware/alpine/sources.json").read_text())

    def test_kernel_author_source_manifest(self) -> None:
        record = json.loads(
            (ROOT / "kernel/provenance/comp18man-a113x-delta.json").read_text()
        )
        self.assertEqual(record["file_count"], 246)
        self.assertEqual(record["source_revision"], self.profile["kernel"]["revision"])
        self.assertTrue(
            any(f["path"] == "drivers/auxdisplay/seg-led-class.c"
                for f in record["files"])
        )

    def test_invalid_firmware_component_type_is_rejected(self) -> None:
        changed = copy.deepcopy(self.profile)
        changed["firmware"]["components"].append({"invalid": "object"})
        with self.assertRaisesRegex(ProfileError, "Invalid firmware"):
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

    @staticmethod
    def _fake_service_files(root: Path, profile: dict) -> None:
        for services in build.enabled_services(profile).values():
            for name in services:
                p = root / "etc/init.d" / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("#!/sbin/openrc-run\\n")

    def test_official_sources_pinned(self) -> None:
        for item in ("minirootfs", "host_apk_static"):
            source = build.SOURCES[item]
            self.assertTrue(source["url"].startswith("https://"))
            self.assertEqual(len(source["sha256"]), 64)
        self.assertNotIn("allow-untrusted", (ROOT / "builder/build.py").read_text())

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

    def test_components_exclude_optional_firmware(self) -> None:
        import copy
        p = copy.deepcopy(self.profile)
        p["firmware"]["components"] = ["base", "ssh"]
        packages = build.apk_packages(p)
        services = build.enabled_services(p)
        self.assertIn("openssh", packages)
        self.assertNotIn("bluez", packages)
        self.assertNotIn("iwd", packages)
        self.assertNotIn("dnsmasq", packages)
        self.assertIn("sshd", services["default"])
        self.assertNotIn("usbgadget", services["boot"])

    def test_unknown_component_fails_closed(self) -> None:
        import copy
        p = copy.deepcopy(self.profile)
        p["firmware"]["components"].append("no-such-firmware")
        with self.assertRaisesRegex(build.BuildError, "Unknown firmware"):
            build.apk_packages(p)

    def test_firmware_owns_generic_gadget_and_ssh(self) -> None:
        common = ROOT / "firmware/alpine/overlay/etc"
        specific = ROOT / "builder/devices/capsula-mini-native/overlay/etc"
        self.assertTrue((common / "init.d/usbgadget").is_file())
        self.assertTrue((common / "ssh/sshd_config.d/10-audio-module.conf").is_file())
        self.assertFalse((specific / "init.d/usbgadget").exists())
        self.assertFalse((specific / "ssh/sshd_config.d/10-audio-module.conf").exists())
        self.assertTrue((specific / "conf.d/usbgadget").is_file())
        self.assertNotIn("Capsula", (common / "init.d/usbgadget").read_text())

    def test_public_key_injection(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "rootfs"
            root.mkdir()
            public = Path(td) / "test.pub"
            public.write_text("ssh-ed25519 " + "a" * 50 + " test-only\n")
            self._fake_service_files(root, self.profile)
            links = patch.object(Path, "symlink_to") if os.name == "nt" else nullcontext()
            with links:
                build.apply_overlay(self.profile, root, public)
            if os.name != "nt":
                self.assertEqual((root / "root/.ssh/authorized_keys").stat().st_mode & 0o777, 0o600)
            self.assertTrue((root / "root/.ssh/authorized_keys").is_file())

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
            self.assertFalse(data["runtime_hal_verified"])
            self.assertFalse(data["update_persistence"]["system_update"]["can_apply"])
            self.assertFalse(data["update_persistence"]["clean_install"]["can_apply"])
            self.assertEqual(data["hal_abi_major"], 1)
            self.assertNotIn("light.ring", data["capabilities_declared"])
            self.assertEqual(data["artifacts"]["Image"]["sha256"],
                             hashlib.sha256((images / "Image").read_bytes()).hexdigest())

    def test_firmware_blob_selection_follows_optional_components(self) -> None:
        import copy
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            kernel = root / "kernel"
            image = root / "rootfs"
            for component, files in self.profile["kernel"]["runtime_firmware"].items():
                for name in files:
                    p = kernel / "firmware" / name
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(("test-" + component).encode())
            p = copy.deepcopy(self.profile)
            p["firmware"]["components"] = ["base", "ssh", "audio"]
            validate_target(p)
            build.stage_driver_firmware(p, kernel, image)
            self.assertTrue((image / "lib/firmware/eq_8918.bin").is_file())
            self.assertFalse((image / "lib/firmware/aml/aml_wifi_rf_fn_link.txt").exists())

    def test_firmware_blob_traversal_rejected(self) -> None:
        import copy
        p = copy.deepcopy(self.profile)
        p["kernel"]["runtime_firmware"]["audio.playback.speaker"] = ["../user-keys"]
        with self.assertRaisesRegex(ProfileError, "Unsafe runtime firmware"):
            validate_target(p)

    def test_historical_flash_executable_is_quarantined(self) -> None:
        import subprocess
        for name in ("alpine_flash_windows.py", "raw_backup.py"):
            tool = (ROOT / "tools/amlogic/worldcup/windows/legacy" / name)
            result = subprocess.run(
                [sys.executable, str(tool)],
                capture_output=True, text=True, timeout=5, check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("LEGACY REFERENCE DISABLED", result.stderr)

    def test_empty_application_is_not_added(self) -> None:
        self.assertEqual(self.profile["application"]["enabled"], False)
        self.assertNotIn("audio-module-application", (ROOT / "builder/build.py").read_text())


if __name__ == "__main__":
    unittest.main()
