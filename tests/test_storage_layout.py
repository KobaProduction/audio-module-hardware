"""Storage plan tests: only validation of a never-flashed candidate."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from builder.profile import ProfileError, load_target, validate_target
from builder.storage import StoragePlanError, audit_immutable_rootfs, load_storage_layout, plan_storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.target = load_target("capsula-mini-native")
        self.doc = load_storage_layout(self.target)

    def test_legacy_unchanged(self):
        plan = plan_storage(self.target)
        self.assertEqual(plan.current_layout, "single-ubifs")
        self.assertEqual(plan.current_boot_root, "ubi0:rootfs")
        self.assertFalse(plan.may_install)
        self.assertFalse(plan.may_switch_boot)

    def test_physical_order_and_contiguity(self):
        p = plan_storage(self.target).physical_partitions
        self.assertEqual([x.name for x in p], ["bootloader","reserved","tpl","misc","kernel","dtb","ubi"])
        self.assertEqual(p[0].offset_bytes, 0)
        self.assertEqual(p[-1].offset_bytes+p[-1].size_bytes, self.target["nand"]["total_bytes"])
        self.assertEqual(p[-1].size_bytes, 212*1024*1024)
        for a,b in zip(p,p[1:]):
            self.assertEqual(a.offset_bytes+a.size_bytes,b.offset_bytes)

    def test_protected_vendor_reserved_already_contains_identity(self):
        p = plan_storage(self.target)
        self.assertTrue(all(x.preserve_always for x in p.physical_partitions[:4]))
        self.assertEqual(p.physical_partitions[1].name,"reserved")
        self.assertEqual(p.physical_partitions[4].offset_bytes,18*1024*1024)
        self.assertEqual(p.physical_partitions[5].offset_bytes,43*1024*1024)
        self.assertEqual(p.physical_partitions[6].offset_bytes,44*1024*1024)
        self.assertEqual(p.identity_source,"existing-protected-uboot-env-with-mac-copy-conflict")
        self.assertNotIn("identity",[x.name for x in p.physical_partitions])
        self.assertNotIn("identity",[x.name for x in p.ubi_volumes])
        identity = self.doc["candidate"]["identity_source"]
        self.assertFalse(identity["allow_uboot_environment_writes"])
        self.assertFalse(identity["active_copy_selected_by_bootloader_verified"])
        self.assertTrue(identity["ethaddr_copy_values_disagree"])

    def test_data_autoresizes_without_fixed_tail_reserve(self):
        p = plan_storage(self.target)
        self.assertEqual(p.ubi_volumes[0].allocation,"image-sized")
        self.assertEqual(p.ubi_volumes[0].max_lebs,1024)
        self.assertEqual(p.ubi_volumes[1].allocation,"autoresize-remainder")
        self.assertIsNone(p.ubi_volumes[1].max_lebs)
        self.assertIsNone(p.rootfs_data_exact_lebs)
        self.assertEqual(p.fixed_unused_tail_lebs,0)
        self.assertEqual(p.nominal_ubi_pebs,1696)
        self.assertTrue(p.ubi_volumes[1].preserve_on_update)
        self.assertFalse(p.ubi_volumes[1].preserve_on_clean)

    def test_reject_reordering_overlaps_and_unsafe_identity(self):
        mutations = [
            lambda d: d["candidate"]["physical_partitions"].reverse(),
            lambda d: d["candidate"]["physical_partitions"][4].update(offset=0),
            lambda d: d["candidate"]["physical_partitions"][4].update(bytes=131071),
            lambda d: d["candidate"]["identity_source"].update(allow_uboot_environment_writes=True),
            lambda d: d["candidate"]["physical_partitions"][1].update(preserve_always=False),
            lambda d: d["candidate"]["physical_partitions"][-1].update(bytes=1024),
        ]
        for mutate in mutations:
            d=deepcopy(self.doc)
            mutate(d)
            with self.subTest(mutation=mutate):
                with self.assertRaises(StoragePlanError):
                    plan_storage(self.target,document=d)

    def test_reject_fixed_data_limit_reserves_and_overcommit(self):
        def fixed(d): d["candidate"]["ubi"]["volumes"][1]["max_lebs"]=512
        def reserve(d): d["candidate"]["ubi"]["additional_fixed_tail_reserve_lebs"]=100
        def over(d): d["candidate"]["ubi"]["volumes"][0]["max_lebs"]=1670
        def reorder(d): d["candidate"]["ubi"]["volumes"].reverse()
        for mutate in (fixed,reserve,over,reorder):
            d=deepcopy(self.doc)
            mutate(d)
            with self.assertRaises(StoragePlanError):
                plan_storage(self.target,document=d)

    def test_fail_closed_on_unverified_activation_and_squashfs(self):
        for field in ("factory_identity_source_validated_for_runtime",
                      "early_init_implemented", "volume_migration_implemented",
                      "recovery_validated"):
            d=deepcopy(self.doc)
            d["candidate"][field]=True
            with self.assertRaises(StoragePlanError):
                plan_storage(self.target,document=d)
        d=deepcopy(self.doc)
        d["alternative"]["status"]="ready"
        with self.assertRaises(StoragePlanError):
            plan_storage(self.target,document=d)
        t=deepcopy(self.target)
        t["storage"]["candidate_activated"]=True
        with self.assertRaises(ProfileError):
            validate_target(t)

    def test_json_cli_displays_physical_and_logical_separately(self):
        proc=subprocess.run([sys.executable,"-m","builder.build","storage-plan","--target",
                             "capsula-mini-native"],capture_output=True,text=True,check=True,timeout=10)
        d=json.loads(proc.stdout)
        self.assertFalse(d["may_install"])
        self.assertEqual(d["physical_partitions"][1]["name"],"reserved")
        self.assertEqual(d["ubi_volumes"][1]["allocation"],"autoresize-remainder")

    def test_read_only_secret_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"rootfs"
            ssh=root/"root/.ssh/authorized_keys"
            wifi=root/"etc/iwd/home.psk"
            for x in (ssh,wifi):
                x.parent.mkdir(parents=True,exist_ok=True)
                x.write_text("private-test-marker")
            s=audit_immutable_rootfs(root)
            self.assertFalse(s["safe_to_package_as_immutable_lower"])
            self.assertFalse(s["may_install"])
            self.assertNotIn("private-test-marker",str(s))
            proc=subprocess.run([sys.executable,"-m","builder.build","storage-audit",
                "--target","capsula-mini-native","--work",d],
                capture_output=True,text=True,timeout=10)
            self.assertNotEqual(proc.returncode,0)
            self.assertEqual(ssh.read_text(),"private-test-marker")

    def test_empty_audit_still_does_not_approve_install(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            (p/"etc").mkdir()
            (p/"etc/machine-id").write_text("")
            s=audit_immutable_rootfs(p)
            self.assertTrue(s["safe_to_package_as_immutable_lower"])
            self.assertFalse(s["may_install"])


if __name__ == "__main__":
    unittest.main()
