"""Fail-closed persistence plan. This does NOT backup, restore or flash devices."""
from __future__ import annotations

import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MODES = ("system-update", "clean-install", "factory-reset")
PATH_PATTERN = re.compile(r"^/(?:[A-Za-z0-9._*+-]+/)*[A-Za-z0-9._*+-]+$")


class PersistenceError(ValueError):
    pass


def _paths(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise PersistenceError("Missing " + label + " paths")
    if any(not isinstance(x, str) or not PATH_PATTERN.fullmatch(x)
           or ".." in x.split("/") or x == "/" for x in value):
        raise PersistenceError("Invalid persistent path in " + label)
    if len(set(value)) != len(value):
        raise PersistenceError("Duplicate persistent path in " + label)
    return value


def validate_policy(target: dict, policy: dict) -> None:
    if not isinstance(policy, dict) or policy.get("schema") != 1 or policy.get("device") != target["id"]:
        raise PersistenceError("Persistence schema/device mismatch")
    layout = policy["current_storage"]
    if (layout.get("ubi_mtd") != "ubi"
            or layout.get("rootfs_volume") != "rootfs"
            or layout.get("rootfs_volume_lebs") != target["nand"]["rootfs_max_lebs"]
            or layout.get("available_ubi_lebs") != 0
            or layout.get("independent_data_volume") is not False):
        raise PersistenceError("Unverified UBI storage layout")
    factory = policy["factory"]
    if (factory.get("protected_before_offset") != target["nand"]["protected_until"]
            or factory.get("protected_mtd_names") != ["bootloader", "reserved", "tpl", "misc"]
            or factory.get("unique_serial_storage_verified") is not False):
        raise PersistenceError("Factory identity/protected-region assumptions invalid")
    if policy["identity"].get("preserve_on_clean_install") is not True:
        raise PersistenceError("Clean install must preserve identity")
    if (policy["user_settings"].get("preserve_on_system_update") is not True
            or policy["user_settings"].get("reset_on_clean_install") is not True):
        raise PersistenceError("Update mode retention contract invalid")
    ids = _paths(policy["identity"].get("paths"), "identity")
    user = _paths(policy["user_settings"].get("paths"), "user")
    for a in ids:
        for b in user:
            if a == b or a.startswith(b.rstrip("*") + "/") or b.startswith(a.rstrip("*") + "/"):
                raise PersistenceError("Identity/user path inventories overlap")
    flags = policy["update_capability"]
    for key in ("whole_ubi_replacement_preserves_rootfs_state",
                "external_backup_restore_implemented",
                "hardware_rollback_validated", "safe_apply_enabled"):
        if flags.get(key) is not False:
            raise PersistenceError("Unverified flash/preservation capability enabled")


def load_policy(target: dict) -> dict:
    device = target["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]+", device):
        raise PersistenceError("Invalid device identity")
    file = ROOT / "builder/devices" / device / "persistence.json"
    policy = json.loads(file.read_text(encoding="utf-8"))
    validate_policy(target, policy)
    return policy


def plan(target: dict, mode: str, policy: dict | None = None) -> dict:
    if mode not in MODES:
        raise PersistenceError("Unsupported installation mode")
    p = load_policy(target) if policy is None else policy
    validate_policy(target, p)
    replacement = mode != "factory-reset"
    blockers = ["no-separate-persistent-ubi-volume",
                "unique-device-serial-source-not-verified"]
    if replacement:
        blockers += ["unimplemented-verified-off-device-backup-restore",
                     "unvalidated-firmware-rollback"]
    else:
        blockers.append("unimplemented-user-settings-reset")
    return {
        "schema": 1, "device": target["id"], "mode": mode,
        "writes_firmware": replacement,
        "factory_nand_policy": "always-preserve",
        "protected_before_offset": p["factory"]["protected_before_offset"],
        "preserve_device_identity": True,
        "preserve_user_settings": mode == "system-update",
        "reset_user_settings": mode != "system-update",
        "requires_external_identity_backup": replacement,
        "requires_external_user_backup": mode == "system-update",
        "identity_paths": p["identity"]["paths"],
        "user_settings_paths": p["user_settings"]["paths"],
        "backup_restore_verified": False, "can_apply": False,
        "blockers": blockers,
    }
