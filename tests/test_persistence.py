"""Retention-mode assertions; never interact with the actual NAND device."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from builder.profile import load_target
from firmware.updates.persistence import (
    PersistenceError, load_policy, plan, validate_policy,
)

TARGET = load_target("capsula-mini-native")


class RetentionPolicyTests(unittest.TestCase):
    def test_actual_ubi_volume_has_no_separate_persistence(self) -> None:
        p = load_policy(TARGET)
        self.assertEqual(p["current_storage"]["rootfs_volume"], "rootfs")
        self.assertEqual(p["current_storage"]["rootfs_volume_lebs"], 1652)
        self.assertEqual(p["current_storage"]["available_ubi_lebs"], 0)
        self.assertFalse(p["current_storage"]["independent_data_volume"])
        self.assertFalse(p["factory"]["unique_serial_storage_verified"])

    def test_system_update_preserves_identity_and_settings_but_is_blocked(self) -> None:
        result = plan(TARGET, "system-update")
        self.assertTrue(result["preserve_device_identity"])
        self.assertTrue(result["preserve_user_settings"])
        self.assertFalse(result["reset_user_settings"])
        self.assertTrue(result["requires_external_identity_backup"])
        self.assertTrue(result["requires_external_user_backup"])
        self.assertEqual(result["factory_nand_policy"], "always-preserve")
        self.assertFalse(result["can_apply"])

    def test_clean_install_only_resets_user_data_not_serial_or_factory(self) -> None:
        result = plan(TARGET, "clean-install")
        self.assertTrue(result["preserve_device_identity"])
        self.assertFalse(result["preserve_user_settings"])
        self.assertTrue(result["reset_user_settings"])
        self.assertTrue(result["requires_external_identity_backup"])
        self.assertFalse(result["requires_external_user_backup"])
        self.assertEqual(result["protected_before_offset"], 18874368)
        self.assertFalse(result["can_apply"])

    def test_factory_reset_must_not_rewrite_firmware(self) -> None:
        result = plan(TARGET, "factory-reset")
        self.assertFalse(result["writes_firmware"])
        self.assertTrue(result["preserve_device_identity"])
        self.assertTrue(result["reset_user_settings"])
        self.assertFalse(result["requires_external_identity_backup"])
        self.assertFalse(result["can_apply"])

    def test_fails_closed_on_no_backup_or_rollback(self) -> None:
        for mode in ("system-update", "clean-install"):
            result = plan(TARGET, mode)
            self.assertIn("unimplemented-verified-off-device-backup-restore", result["blockers"])
            self.assertIn("unvalidated-firmware-rollback", result["blockers"])
            self.assertIn("unique-device-serial-source-not-verified", result["blockers"])

    def test_fails_closed_if_someone_claims_unverified_persistence(self) -> None:
        p = load_policy(TARGET)
        for field in ("safe_apply_enabled", "external_backup_restore_implemented",
                      "whole_ubi_replacement_preserves_rootfs_state",
                      "hardware_rollback_validated"):
            altered = deepcopy(p)
            altered["update_capability"][field] = True
            with self.assertRaisesRegex(PersistenceError, "Unverified"):
                validate_policy(TARGET, altered)

    def test_factory_partition_and_identity_cannot_be_reclassified(self) -> None:
        p = load_policy(TARGET)
        p["factory"]["protected_mtd_names"] = ["reserved"]
        with self.assertRaisesRegex(PersistenceError, "Factory"):
            validate_policy(TARGET, p)
        p = load_policy(TARGET)
        p["identity"]["preserve_on_clean_install"] = False
        with self.assertRaisesRegex(PersistenceError, "preserve identity"):
            validate_policy(TARGET, p)

    def test_sensitive_path_inventory_rejects_overlap_traversal(self) -> None:
        p = load_policy(TARGET)
        p["identity"]["paths"].append("/etc/../passwd")
        with self.assertRaisesRegex(PersistenceError, "Invalid persistent path"):
            validate_policy(TARGET, p)
        p = load_policy(TARGET)
        p["user_settings"]["paths"].append("/etc/ssh")
        with self.assertRaisesRegex(PersistenceError, "overlap"):
            validate_policy(TARGET, p)

    def test_unrecognized_mode_is_rejected(self) -> None:
        with self.assertRaisesRegex(PersistenceError, "Unsupported"):
            plan(TARGET, "wipe-everything")


if __name__ == "__main__":
    unittest.main()
