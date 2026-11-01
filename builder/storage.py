"""Read-only physical NAND and logical UBI layout planner.

Physical MTD partitions have fixed, ordered offsets. UBI volumes are logical
and wear-levelled: their IDs do NOT denote physical offsets or ordering.
Nothing here formats partitions, creates UBI volumes, or updates bootargs.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FLAG_KEYS = (
    "factory_identity_source_validated_for_runtime", "early_init_implemented",
    "boot_pivot_verified", "volume_migration_implemented",
    "update_rootfs_only_implemented", "recovery_validated",
)
BOOT_CHAIN = ("bootloader", "reserved", "tpl", "misc")
ORDER = BOOT_CHAIN + ("kernel", "dtb", "ubi")
ROLES = (
    "boot-chain", "factory-reserved", "boot-chain", "boot-chain",
    "kernel", "kernel-description", "system-and-data",
)


class StoragePlanError(ValueError):
    pass


@dataclass(frozen=True)
class PhysicalPartition:
    name: str
    offset_bytes: int
    size_bytes: int
    role: str
    preserve_always: bool


@dataclass(frozen=True)
class UBIVolume:
    name: str
    volume_id: int
    role: str
    filesystem: str
    allocation: str
    max_lebs: int | None
    min_lebs: int | None
    preserve_on_update: bool
    preserve_on_clean: bool


@dataclass(frozen=True)
class StoragePlan:
    device: str
    status: str
    current_layout: str
    current_boot_root: str
    candidate_boot_root: str
    physical_partitions: tuple[PhysicalPartition, ...]
    ubi_partition_bytes: int
    nominal_ubi_pebs: int
    ubi_volumes: tuple[UBIVolume, ...]
    rootfs_max_lebs: int
    rootfs_data_autoresize_to_end: bool
    rootfs_data_exact_lebs: None
    fixed_unused_tail_lebs: int
    identity_source: str
    overlay_filesystem: str
    alternative_squashfs_status: str
    may_install: bool
    may_switch_boot: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def load_storage_layout(target: dict) -> dict:
    device = target["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", device):
        raise StoragePlanError("Invalid device path")
    path = ROOT / "builder" / "devices" / device / "storage.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_physical_partitions(target: dict, proposal: dict) -> tuple[PhysicalPartition, ...]:
    parts = proposal.get("physical_partitions")
    if (proposal.get("physical_partition_policy") != "explicit-mtd"
            or not isinstance(parts, list) or len(parts) != len(ORDER)
            or [p.get("name") for p in parts if isinstance(p, dict)] != list(ORDER)):
        raise StoragePlanError("Physical NAND order must keep original boot, kernel, dtb, ubi")
    nand = target["nand"]
    erase = nand["erase_block_bytes"]
    previous_end = 0
    mapped: list[PhysicalPartition] = []
    for part, name, role in zip(parts, ORDER, ROLES):
        if not isinstance(part, dict):
            raise StoragePlanError("Invalid physical partition")
        offset, size = part.get("offset"), part.get("bytes")
        if (type(offset) is not int or type(size) is not int
                or offset != previous_end or size <= 0 or offset % erase or size % erase):
            raise StoragePlanError("MTD ranges must be contiguous and eraseblock-aligned")
        preserved = name in BOOT_CHAIN
        if part.get("role") != role or part.get("preserve_always") is not preserved:
            raise StoragePlanError("Factory/firmware write policy mismatch")
        if name in BOOT_CHAIN:
            expected_sizes = {
                "bootloader": 2097152, "reserved": 6291456,
                "tpl": 8388608, "misc": 2097152,
            }
            if size != expected_sizes[name]:
                raise StoragePlanError("Protected original boot-chain partition changed")
        if name == "kernel" and size != nand["dtb_offset"] - nand["kernel_offset"]:
            raise StoragePlanError("Proposed kernel slot size changed")
        if name == "dtb" and size != nand["ubi_offset"] - nand["dtb_offset"]:
            raise StoragePlanError("Proposed DTB slot size changed")
        previous_end = offset + size
        mapped.append(PhysicalPartition(name, offset, size, role, preserved))
    if previous_end != nand["total_bytes"]:
        raise StoragePlanError("Final UBI partition must extend to physical NAND end")
    if mapped[-1].offset_bytes != nand["ubi_offset"]:
        raise StoragePlanError("Existing UBI start must remain unchanged")
    return tuple(mapped)


def _validate_ubi(proposal: dict, target: dict, partition: PhysicalPartition) -> tuple[UBIVolume, ...]:
    ubi = proposal.get("ubi")
    if not isinstance(ubi, dict) or ubi.get("mtd_partition") != partition.name:
        raise StoragePlanError("RootFS and RootFS Data must live in the final UBI partition")
    volumes = ubi.get("volumes")
    if not isinstance(volumes, list) or len(volumes) != 2:
        raise StoragePlanError("Only rootfs and rootfs_data UBI volumes are supported")
    lower, data = volumes
    if not all(isinstance(v, dict) for v in volumes):
        raise StoragePlanError("Invalid UBI volume specification")
    if (
        lower.get("name"), lower.get("id"), lower.get("role"),
        lower.get("filesystem"), lower.get("allocation"),
        lower.get("read_only_at_runtime"), lower.get("preserve_during_system_update"),
        lower.get("preserve_during_clean_install")
    ) != ("rootfs", 0, "immutable-system", "ubifs", "image-sized", True, False, False):
        raise StoragePlanError("Invalid immutable system volume")
    if (
        data.get("name"), data.get("id"), data.get("role"),
        data.get("filesystem"), data.get("allocation"),
        data.get("read_only_at_runtime"), data.get("preserve_during_system_update"),
        data.get("preserve_during_clean_install")
    ) != ("rootfs_data", 1, "user-overlay", "ubifs", "autoresize-remainder", False, True, False):
        raise StoragePlanError("RootFS Data must autoresize to the UBI remainder")
    root_limit, data_min = lower.get("max_lebs"), data.get("min_lebs")
    if (type(root_limit) is not int or type(data_min) is not int
            or root_limit <= 0 or data_min < 32):
        raise StoragePlanError("Invalid proposed root/data LEB bounds")
    if data.get("max_lebs") is not None or lower.get("min_lebs") is not None:
        raise StoragePlanError("RootFS Data must NOT have a fixed maximum")
    if (ubi.get("additional_fixed_tail_reserve_lebs") != 0
            or ubi.get("ubi_internal_bad_block_reserves") != "managed-by-ubi"):
        raise StoragePlanError("No artificial fixed tail reserve; leave UBI internal reserves intact")
    nominal_pebs = partition.size_bytes // target["nand"]["erase_block_bytes"]
    if root_limit + data_min + 2 >= nominal_pebs:
        raise StoragePlanError("Volume bounds overcommit physical UBI partition")
    # Exact usable UBI LEB capacity is device-specific (bad PEBs, EC/VID,
    # UBI reserves). We intentionally do NOT fabricate remaining data LEBs.
    return (
        UBIVolume("rootfs", 0, "immutable-system", "ubifs", "image-sized",
                  root_limit, None, False, False),
        UBIVolume("rootfs_data", 1, "user-overlay", "ubifs",
                  "autoresize-remainder", None, data_min, True, False),
    )


def plan_storage(target: dict, *, document: dict | None = None) -> StoragePlan:
    d = load_storage_layout(target) if document is None else document
    if (not isinstance(d, dict) or d.get("schema") != 3
            or d.get("device") != target["id"] or d.get("state") != "design-only"):
        raise StoragePlanError("Unsupported or activated storage design")
    original = d["current"]
    n = target["nand"]
    if (original.get("layout") != "single-ubifs"
            or original.get("mtd_layout") != list(BOOT_CHAIN + ("kernel", "dtb", "ubi"))
            or original.get("root_volume") != "rootfs"
            or original.get("volume_id") != 0
            or original.get("allocated_lebs") != n["rootfs_max_lebs"]
            or original.get("boot_root") != "ubi0:rootfs"
            or original.get("writable_root") is not True):
        raise StoragePlanError("Current NAND evidence does not match legacy root")
    proposed = d["candidate"]
    if (proposed.get("layout") != "protected-factory-kernel-ubi-overlay"
            or proposed.get("kernel_boot_root") != original["boot_root"]
            or proposed.get("base_filesystem") != "ubifs"
            or proposed.get("overlay_filesystem") != "overlayfs"
            or proposed.get("data_filesystem") != "ubifs"):
        raise StoragePlanError("Unsupported overlay backend or boot contract")
    if any(proposed.get(k) is not False for k in FLAG_KEYS):
        raise StoragePlanError("Bootloader, image migration or recovery is not hardware-validated")
    if proposed.get("required_kernel_symbols") != [
        "CONFIG_OVERLAY_FS=y", "CONFIG_UBIFS_FS=y", "CONFIG_MTD_UBI=y"
    ]:
        raise StoragePlanError("OverlayFS kernel requirements not set")
    mounts = proposed.get("mounts")
    if mounts != {
        "lower": "/rom", "merged": "/", "data": "/overlay",
        "upper": "/overlay/upper", "work": "/overlay/work",
    }:
        raise StoragePlanError("Incorrect OverlayFS mount boundaries")
    physical = _validate_physical_partitions(target, proposed)
    ident = proposed.get("identity_source")
    if (not isinstance(ident, dict)
            or ident.get("kind") != "read-only-uboot-environment-and-factory"
            or ident.get("existing_partition") != "reserved"
            or ident.get("uboot_environment_offsets_in_reserved") != [1048576,1179648]
            or ident.get("environment_block_bytes") != 65536
            or ident.get("crc32_valid_copies_observed") != 2
            or ident.get("identifier_key_names") != ["serial","ethaddr"]
            or ident.get("serial_present_in_one_verified_copy") is not True
            or ident.get("ethaddr_copy_values_disagree") is not True
            or ident.get("postflash_environment_matches_one_mac_copy") is not True
            or ident.get("active_copy_selected_by_bootloader_verified") is not False
            or ident.get("factory_keys_calibration_preserved_in_place") is not True
            or ident.get("allow_uboot_environment_writes") is not False
            or ident.get("dedicated_identity_partition_required") is not False
            or ident.get("identity_values_in_repository") is not False):
        raise StoragePlanError("U-Boot environment identity evidence or safety policy mismatch")
    volumes = _validate_ubi(proposed, target, physical[-1])
    alt = d["alternative"]
    if (alt.get("layout") != "squashfs-on-ubiblock"
            or alt.get("status") != "research-only"
            or alt.get("requires_new_root_boot_contract") is not True):
        raise StoragePlanError("SquashFS backend is not boot-validated")
    return StoragePlan(
        device=target["id"], status="design-only",
        current_layout="single-ubifs", current_boot_root=original["boot_root"],
        candidate_boot_root=proposed["kernel_boot_root"],
        physical_partitions=physical,
        ubi_partition_bytes=physical[-1].size_bytes,
        nominal_ubi_pebs=physical[-1].size_bytes // n["erase_block_bytes"],
        ubi_volumes=volumes,
        rootfs_max_lebs=volumes[0].max_lebs,
        rootfs_data_autoresize_to_end=True,
        rootfs_data_exact_lebs=None,
        fixed_unused_tail_lebs=0,
        identity_source="existing-protected-uboot-env-with-mac-copy-conflict",
        overlay_filesystem="overlayfs",
        alternative_squashfs_status="research-only",
        may_install=False, may_switch_boot=False,
        blockers=(
            "redundant-uboot-ethaddr-values-conflict",
            "uboot-active-environment-copy-not-verified",
            "factory-identity-readonly-provider-not-implemented",
            "rootfs-data-exact-capacity-requires-ubi-attach-and-actual-image",
            "early-overlay-init-and-pivot-unimplemented",
            "offline-backup-migration-and-recovery-unvalidated",
            "whole-ubi-replacement-would-destroy-persistent-data",
        ),
    )


def audit_immutable_rootfs(rootfs: Path) -> dict:
    """Read-only guard for obvious personalized files. Does not read values."""
    if not rootfs.is_dir() or rootfs.is_symlink():
        raise StoragePlanError("Staged rootfs is missing or a symlink")
    blocked_patterns = (
        "root/.ssh/authorized_keys", "etc/ssh/ssh_host_*", "etc/machine-id",
        "etc/conf.d/usbgadget", "etc/iwd/*.psk", "etc/iwd/*.8021x",
        "etc/iwd/*.open", "var/lib/iwd/*", "var/lib/bluetooth/*",
        "var/lib/audio-module/identity/*", "var/lib/audio-module/settings/*",
    )
    found: set[str] = set()
    for pattern in blocked_patterns:
        for path in rootfs.glob(pattern):
            if path.is_file() or path.is_symlink():
                if (path.name == "machine-id" and not path.is_symlink()
                        and path.stat().st_size == 0):
                    continue
                found.add(path.relative_to(rootfs).as_posix())
            elif path.is_dir() and pattern.endswith("*"):
                found.add(path.relative_to(rootfs).as_posix() + "/")
    return {
        "audit": "immutable-rootfs-source-only",
        "rootfs_path": str(rootfs),
        "safe_to_package_as_immutable_lower": not bool(found),
        "private_state_paths": sorted(found),
        "note": "No files read or copied; unknown custom secret paths require owner inventory",
        "may_install": False,
    }
