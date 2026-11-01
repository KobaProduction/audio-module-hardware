"""Read-only NAND/UBI layout planner. It never creates volumes or writes flash.

The active Capsula Mini image is the legacy single writable UBIFS volume.
The new OpenIPC-inspired split is only a capacity-checked DESIGN candidate.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
TRUE_FLAGS = ("boot_pivot_verified", "initial_provisioning_implemented",
              "volume_migration_implemented", "update_rootfs_only_implemented",
              "recovery_validated")


class StoragePlanError(ValueError):
    pass


@dataclass(frozen=True)
class VolumePlan:
    name: str
    volume_id: int
    role: str
    filesystem: str
    lebs: int
    capacity_bytes: int
    read_only: bool
    preserve_on_update: bool
    preserve_on_clean: bool


@dataclass(frozen=True)
class StoragePlan:
    device: str
    mode: str
    current_boot_root: str
    candidate_boot_root: str
    lower_filesystem: str
    overlay_filesystem: str
    data_filesystem: str
    current_rootfs_lebs: int
    budget_lebs: int
    allocated_lebs: int
    unallocated_lebs: int
    leb_bytes: int
    volumes: tuple[VolumePlan, ...]
    may_install: bool
    may_switch_boot: bool
    alternative_squashfs_status: str
    blockers: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)


def load_storage_layout(target: dict) -> dict:
    device = target["id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", device):
        raise StoragePlanError("Invalid device path")
    path = ROOT / "builder" / "devices" / device / "storage.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    return document


def plan_storage(target: dict, *, document: dict | None = None) -> StoragePlan:
    data = load_storage_layout(target) if document is None else document
    if not isinstance(data, dict) or data.get("schema") != 1:
        raise StoragePlanError("Unsupported storage layout schema")
    if data.get("device") != target["id"] or data.get("state") != "design-only":
        raise StoragePlanError("Incorrect target or unsupported activation")
    legacy = data["current"]
    budget = target["nand"]["rootfs_max_lebs"]
    if (legacy.get("layout") != "single-ubifs"
            or legacy.get("root_volume") != "rootfs"
            or legacy.get("volume_id") != 0
            or legacy.get("allocated_lebs") != budget
            or legacy.get("boot_root") != "ubi0:rootfs"
            or legacy.get("writable_root") is not True):
        raise StoragePlanError("Current NAND facts mismatch actual layout")
    new = data["candidate"]
    if (new.get("layout") != "ubi-root-overlay"
            or new.get("kernel_boot_root") != legacy["boot_root"]
            or new.get("base_filesystem") != "ubifs"
            or new.get("data_filesystem") != "ubifs"
            or new.get("overlay_filesystem") != "overlayfs"):
        raise StoragePlanError("Unverified storage backend or boot root")
    mounts = new["mounts"]
    required = {"lower": "/rom", "merged": "/", "data": "/overlay",
                "upper": "/overlay/upper", "work": "/overlay/work",
                "identity": "/identity"}
    if mounts != required:
        raise StoragePlanError("Overlay mount paths must stay isolated")
    if any(new.get(flag) is not False for flag in TRUE_FLAGS):
        raise StoragePlanError("Boot/migration/recovery acceptance cannot be asserted")
    if (new.get("bootloader_root_parameter_unchanged") is not True
            or new.get("early_init_implemented") is not False
            or new.get("required_kernel_symbols") !=
            ["CONFIG_OVERLAY_FS=y", "CONFIG_UBIFS_FS=y", "CONFIG_MTD_UBI=y"]):
        raise StoragePlanError("Required OverlayFS early boot/kernel gate missing")
    vols = new["volumes"]
    if not isinstance(vols, list) or len(vols) != 3:
        raise StoragePlanError("Expected exactly rootfs, rootfs_data and identity")
    required_vols = (
        ("rootfs", 0, "immutable-system", True, False, False),
        ("rootfs_data", 1, "user-overlay", False, True, False),
        ("identity", 2, "device-identity", True, True, True),
    )
    lebs = target["nand"]["ubi_leb_bytes"]
    if type(lebs) is not int or lebs <= 0:
        raise StoragePlanError("Invalid target LEB geometry")
    selected: list[VolumePlan] = []
    for vol, required_vol in zip(vols, required_vols):
        name, vol_id, role, is_ro, on_update, on_clean = required_vol
        if not isinstance(vol, dict) or (
            vol.get("name"), vol.get("id"), vol.get("role"),
            vol.get("read_only_at_runtime"), vol.get("preserve_during_system_update"),
            vol.get("preserve_during_clean_install"),
        ) != (name, vol_id, role, is_ro, on_update, on_clean):
            raise StoragePlanError("UBI volume identity or retention mismatch")
        if not NAME.fullmatch(name) or vol.get("filesystem") != "ubifs":
            raise StoragePlanError("Unsupported UBI filesystem")
        size = vol.get("max_lebs")
        if type(size) is not int or size <= 0:
            raise StoragePlanError("Invalid UBI volume size")
        selected.append(VolumePlan(
            name, vol_id, role, "ubifs", size, size * lebs,
            is_ro, on_update, on_clean,
        ))
    spare = new.get("safety_unallocated_lebs")
    if type(spare) is not int or spare < 32:
        raise StoragePlanError("Insufficient unallocated future growth budget")
    allocated = sum(v.lebs for v in selected)
    if allocated + spare > budget:
        raise StoragePlanError("Proposed UBI volumes overcommit verified budget")
    alt = data["alternative"]
    if (alt.get("layout") != "squashfs-on-ubiblock"
            or alt.get("status") != "research-only"
            or alt.get("requires_new_root_boot_contract") is not True):
        raise StoragePlanError("SquashFS alternative not boot-validated")
    blockers = (
        "current-rootfs-data-migration-not-implemented",
        "early-overlay-pivot-and-linux-config-not-hardware-tested",
        "identity-provisioning-not-validated",
        "ubi-volume-init-and-per-volume-update-not-implemented",
        "recovery-power-loss-rollback-not-validated",
        "current-whole-ubi-image-would-destroy-all-proposed-volumes",
    )
    return StoragePlan(
        device=target["id"], mode="design-only",
        current_boot_root=legacy["boot_root"],
        candidate_boot_root=new["kernel_boot_root"],
        lower_filesystem="ubifs", overlay_filesystem="overlayfs",
        data_filesystem="ubifs", current_rootfs_lebs=budget,
        budget_lebs=budget, allocated_lebs=allocated,
        unallocated_lebs=budget - allocated, leb_bytes=lebs,
        volumes=tuple(selected), may_install=False, may_switch_boot=False,
        alternative_squashfs_status="research-only",
        blockers=blockers,
    )


def audit_immutable_rootfs(rootfs: Path) -> dict:
    """Read-only structural guard against embedding per-device state.

    Returns paths, never file contents. This check is necessary but not
    sufficient for sanitizing generic lower-root images: credentials could
    still be stored in unexpected locations.
    """
    if not rootfs.is_dir() or rootfs.is_symlink():
        raise StoragePlanError("Staged rootfs is missing or a symlink")
    blocked_patterns = (
        "root/.ssh/authorized_keys",
        "etc/ssh/ssh_host_*",
        "etc/machine-id",
        "etc/conf.d/usbgadget",
        "etc/iwd/*.psk",
        "etc/iwd/*.8021x",
        "etc/iwd/*.open",
        "var/lib/iwd/*",
        "var/lib/bluetooth/*",
        "var/lib/audio-module/identity/*",
        "var/lib/audio-module/settings/*",
    )
    found: set[str] = set()
    for pattern in blocked_patterns:
        for path in rootfs.glob(pattern):
            if path.is_file() or path.is_symlink():
                # Never inspect or log private values. Paths are enough.
                if path.name == "machine-id" and not path.is_symlink() and path.stat().st_size == 0:
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
