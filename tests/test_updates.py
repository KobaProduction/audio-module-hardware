"""Signed metadata compatibility checks. No downloads or flash operations."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from builder.profile import load_target
from firmware.updates.check import ReleaseCheckError, check_release


class SignedUpdateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = load_target("capsula-mini-native")
        self.private = self.root / "temporary-test-signing-private.pem"
        self.public = self.root / "trusted-test-pub.pem"
        self.manifest = self.root / "release.json"
        self.signature = self.root / "release.sig"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(self.private)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(self.private),
             "-pubout", "-out", str(self.public)],
            check=True, capture_output=True,
        )
        self.release = {
            "schema": 1,
            "target": self.target["id"],
            "soc": self.target["soc"],
            "version": "1.0.1",
            "hal_abi_major": 1,
            "bootloader": "retain-vendor",
            "hardware_approved": True,
            "kernel_revision": self.target["kernel"]["revision"],
            "artifacts": {
                name: {
                    "sha256": "a" * 64,
                    "url": "https://updates.example.test/" + name,
                    "bytes": 100000,
                }
                for name in ("Image", "board.dtb", "rootfs.ubi")
            },
        }

    def signed_check(self, *, current_version: str = "1.0.0") -> dict:
        self.manifest.write_text(json.dumps(self.release, sort_keys=True), encoding="utf-8")
        subprocess.run(
            ["openssl", "pkeyutl", "-sign", "-rawin",
             "-inkey", str(self.private), "-in", str(self.manifest),
             "-out", str(self.signature)],
            check=True, capture_output=True,
        )
        return check_release(
            self.target, current_version,
            self.manifest, self.signature, self.public,
        )

    def test_newer_signed_release_is_compatible_but_not_flash_authorized(self) -> None:
        result = self.signed_check()
        self.assertEqual(result["status"], "upgrade-available")
        self.assertEqual(result["signature"], "ed25519-verified")
        self.assertFalse(result["artifact_digests_checked"])
        self.assertFalse(result["may_flash"])

    def test_signed_update_never_implies_settings_are_safe_to_overwrite(self) -> None:
        result = self.signed_check()
        retain = result["persistence"]
        self.assertEqual(retain["mode"], "system-update")
        self.assertTrue(retain["preserve_device_identity"])
        self.assertTrue(retain["preserve_user_settings"])
        self.assertFalse(retain["can_apply"])
        self.assertIn("unimplemented-verified-off-device-backup-restore", retain["blockers"])

    def test_clean_install_preserves_identity_not_user_settings(self) -> None:
        self.signed_check()
        result = check_release(
            self.target, "1.0.0", self.manifest, self.signature,
            self.public, mode="clean-install",
        )
        preserve = result["persistence"]
        self.assertTrue(preserve["preserve_device_identity"])
        self.assertFalse(preserve["preserve_user_settings"])
        self.assertTrue(preserve["reset_user_settings"])
        self.assertFalse(result["may_flash"])

    def test_same_version_is_current(self) -> None:
        self.assertEqual(
            self.signed_check(current_version="1.0.1")["status"], "up-to-date",
        )

    def test_downgrade_is_forbidden(self) -> None:
        with self.assertRaisesRegex(ReleaseCheckError, "Downgrade"):
            self.signed_check(current_version="1.0.2")

    def test_signed_wrong_soc_rejected(self) -> None:
        self.release["soc"] = "another-soc"
        with self.assertRaisesRegex(ReleaseCheckError, "another hardware"):
            self.signed_check()

    def test_signed_oversized_rootfs_rejected(self) -> None:
        self.release["artifacts"]["rootfs.ubi"]["bytes"] = 268435456
        with self.assertRaisesRegex(ReleaseCheckError, "too large"):
            self.signed_check()

    def test_non_https_and_embedded_credentials_rejected(self) -> None:
        for url in ("http://example.test/Image",
                    "https://user:pass@updates.example.test/Image"):
            self.release["artifacts"]["Image"]["url"] = url
            with self.assertRaisesRegex(ReleaseCheckError, "HTTPS"):
                self.signed_check()

    def test_hardware_not_approved_rejected(self) -> None:
        self.release["hardware_approved"] = False
        with self.assertRaisesRegex(ReleaseCheckError, "hardware acceptance"):
            self.signed_check()

    def test_kernel_revision_mismatch_rejected(self) -> None:
        self.release["kernel_revision"] = "0" * 40
        with self.assertRaisesRegex(ReleaseCheckError, "kernel revision"):
            self.signed_check()

    def test_tampered_signed_manifest_rejected(self) -> None:
        self.signed_check()
        self.manifest.write_text(
            self.manifest.read_text() + " ", encoding="utf-8",
        )
        with self.assertRaisesRegex(ReleaseCheckError, "Invalid signature"):
            check_release(
                self.target, "1.0.0",
                self.manifest, self.signature, self.public,
            )

    def test_missing_signature_refused(self) -> None:
        self.signed_check()
        self.signature.unlink()
        with self.assertRaisesRegex(ReleaseCheckError, "missing"):
            check_release(
                self.target, "1.0.0",
                self.manifest, self.signature, self.public,
            )

    def test_untrusted_public_key_refused(self) -> None:
        self.signed_check()
        other_private = self.root / "other.pem"
        other_pub = self.root / "other-pub.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519",
             "-out", str(other_private)],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(other_private),
             "-pubout", "-out", str(other_pub)],
            check=True, capture_output=True,
        )
        with self.assertRaisesRegex(ReleaseCheckError, "untrusted"):
            check_release(
                self.target, "1.0.0",
                self.manifest, self.signature, other_pub,
            )


if __name__ == "__main__":
    unittest.main()
