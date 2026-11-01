"""Plan-only storage model tests, never mount, format or flash a live device."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import unittest

from builder.profile import ProfileError, load_target, validate_target
from builder.storage import (
    StoragePlanError, load_storage_layout, plan_storage, audit_immutable_rootfs,
)


class StorageLayoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = load_target("capsula-mini-native")
        self.storage = load_storage_layout(self.target)

    def test_current_root_remains_legacy_and_candidate_never_activates(self) -> None:
        s = plan_storage(self.target)
        self.assertEqual(s.current_boot_root, "ubi0:rootfs")
        self.assertEqual(s.candidate_boot_root, "ubi0:rootfs")
        self.assertEqual(s.mode, "design-only")
        self.assertFalse(s.may_install)
        self.assertFalse(s.may_switch_boot)
        self.assertEqual(self.target["storage"]["active_layout"], "legacy-single-ubifs")

    def test_three_volumes_fit_legacy_ubi_capacity(self) -> None:
        p = plan_storage(self.target)
        self.assertEqual(p.budget_lebs, 1652)
        self.assertEqual(p.allocated_lebs, 1552)
        self.assertEqual(p.unallocated_lebs, 100)
        self.assertEqual([v.name for v in p.volumes], ["rootfs", "rootfs_data", "identity"])
        self.assertEqual([v.lebs for v in p.volumes], [1024, 512, 16])
        self.assertTrue(all(v.filesystem == "ubifs" for v in p.volumes))
        self.assertEqual(p.leb_bytes, 126976)

    def test_only_system_root_is_replaced_by_normal_upgrade(self) -> None:
        p = plan_storage(self.target)
        rootfs, data, ident = p.volumes
        self.assertFalse(rootfs.preserve_on_update)
        self.assertTrue(rootfs.read_only)
        self.assertTrue(data.preserve_on_update)
        self.assertFalse(data.preserve_on_clean)
        self.assertTrue(ident.preserve_on_update)
        self.assertTrue(ident.preserve_on_clean)
        self.assertTrue(ident.read_only)

    def test_overlay_upper_and_work_have_same_ubi_backing(self) -> None:
        c = self.storage["candidate"]
        self.assertEqual(c["mounts"]["upper"], "/overlay/upper")
        self.assertEqual(c["mounts"]["work"], "/overlay/work")
        self.assertEqual(c["mounts"]["lower"], "/rom")
        self.assertEqual(c["mounts"]["merged"], "/")
        self.assertEqual(c["mounts"]["identity"], "/identity")

    def test_reject_storage_geometry_overcommit(self) -> None:
        d = deepcopy(self.storage)
        d["candidate"]["volumes"][0]["max_lebs"] = 1500
        with self.assertRaisesRegex(StoragePlanError, "overcommit"):
            plan_storage(self.target, document=d)

    def test_reject_zero_reserved_growth_space(self) -> None:
        d = deepcopy(self.storage)
        d["candidate"]["safety_unallocated_lebs"] = 0
        with self.assertRaisesRegex(StoragePlanError, "Insufficient"):
            plan_storage(self.target, document=d)

    def test_reject_different_root_volume_or_id(self) -> None:
        for field, value in [("name", "rootfs_data"), ("id", 3),
                             ("filesystem", "squashfs"), ("role", "resettable")]:
            d = deepcopy(self.storage)
            d["candidate"]["volumes"][0][field] = value
            with self.assertRaises(StoragePlanError):
                plan_storage(self.target, document=d)

    def test_reject_identity_becoming_resettable(self) -> None:
        d = deepcopy(self.storage)
        d["candidate"]["volumes"][2]["preserve_during_clean_install"] = False
        with self.assertRaisesRegex(StoragePlanError, "retention"):
            plan_storage(self.target, document=d)

    def test_reject_activation_without_hardware_acceptance(self) -> None:
        p = deepcopy(self.target)
        p["storage"]["candidate_activated"] = True
        with self.assertRaisesRegex(ProfileError, "migration"):
            validate_target(p)
        d = deepcopy(self.storage)
        d["state"] = "ready"
        with self.assertRaisesRegex(StoragePlanError, "activation"):
            plan_storage(self.target, document=d)

    def test_squashfs_is_research_only_and_cannot_replace_ubi_root(self) -> None:
        self.assertEqual(plan_storage(self.target).alternative_squashfs_status, "research-only")
        d = deepcopy(self.storage)
        d["candidate"]["base_filesystem"] = "squashfs"
        with self.assertRaisesRegex(StoragePlanError, "Unverified storage backend"):
            plan_storage(self.target, document=d)
        d = deepcopy(self.storage)
        d["alternative"]["status"] = "hardware-ready"
        with self.assertRaisesRegex(StoragePlanError, "not boot-validated"):
            plan_storage(self.target, document=d)

    def test_reject_claims_of_early_boot_support_without_test(self) -> None:
        for key in ("boot_pivot_verified", "early_init_implemented",
                    "initial_provisioning_implemented", "update_rootfs_only_implemented"):
            d = deepcopy(self.storage)
            d["candidate"][key] = True
            with self.assertRaises(StoragePlanError):
                plan_storage(self.target, document=d)

    def test_immutable_rootfs_audit_rejects_personal_ssh_and_wifi_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "rootfs"
            private = root / "root/.ssh/authorized_keys"
            secret = root / "etc/iwd/home.psk"
            for path in (private, secret):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("dummy-private-fixture")
            result = audit_immutable_rootfs(root)
            self.assertFalse(result["safe_to_package_as_immutable_lower"])
            self.assertFalse(result["may_install"])
            self.assertEqual(
                set(result["private_state_paths"]),
                {"root/.ssh/authorized_keys", "etc/iwd/home.psk"},
            )
            self.assertNotIn("dummy-private-fixture", str(result))

    def test_empty_candidate_lower_audit_does_not_imply_install_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "etc").mkdir()
            (root / "etc/machine-id").write_text("")
            result = audit_immutable_rootfs(root)
            self.assertTrue(result["safe_to_package_as_immutable_lower"])
            self.assertFalse(result["may_install"])

    def test_rootfs_audit_cannot_be_run_on_missing_or_symlink_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(StoragePlanError):
                audit_immutable_rootfs(root / "missing")
            (root / "files").mkdir()
            (root / "link").symlink_to(root / "files", target_is_directory=True)
            with self.assertRaises(StoragePlanError):
                audit_immutable_rootfs(root / "link")

    def test_storage_audit_is_read_only_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            user = work / "rootfs/root/.ssh/authorized_keys"
            user.parent.mkdir(parents=True, exist_ok=True)
            user.write_text("dummy-private-fixture")
            run = subprocess.run(
                [sys.executable, "-m", "builder.build", "storage-audit",
                 "--target", "capsula-mini-native", "--work", str(work)],
                capture_output=True, text=True, timeout=10, check=False,
            )
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(user.read_text(), "dummy-private-fixture")
            self.assertNotIn("dummy-private-fixture", run.stdout + run.stderr)

    def test_candidate_has_nonwriting_json_cli(self) -> None:
        output = subprocess.run(
            [sys.executable, "-m", "builder.build", "storage-plan",
             "--target", "capsula-mini-native"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        doc = json.loads(output.stdout)
        self.assertFalse(doc["may_install"])
        self.assertFalse(doc["may_switch_boot"])
        self.assertEqual(doc["volumes"][1]["name"], "rootfs_data")
        self.assertGreater(len(doc["blockers"]), 3)


if __name__ == "__main__":
    unittest.main()
