"""Strict target profile validation; never infer NAND geometry or layout."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "targets"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class ProfileError(ValueError):
    pass


def load_target(name: str) -> dict:
    if not NAME.fullmatch(name):
        raise ProfileError("Invalid target name")
    path = TARGETS / (name + ".json")
    if not path.is_file():
        raise ProfileError("Unknown target: " + name)
    target = json.loads(path.read_text(encoding="utf-8"))
    validate_target(target)
    if target["id"] != name:
        raise ProfileError("Filename and target ID mismatch")
    return target


def validate_target(t: dict) -> None:
    if t.get("schema") != 1:
        raise ProfileError("Unsupported target schema")
    for key in ("id", "soc", "board", "variant"):
        if not NAME.fullmatch(t.get(key, "")):
            raise ProfileError("Invalid " + key)
    if t.get("architecture") != "aarch64":
        raise ProfileError("Unsupported architecture")
    kernel = t["kernel"]
    if not HEX_SHA.fullmatch(kernel["revision"]):
        raise ProfileError("Kernel must be pinned to a full SHA")
    if not kernel["source"].startswith("https://github.com/"):
        raise ProfileError("Kernel source must be a GitHub HTTPS repository")
    if "/" in kernel["defconfig"] or kernel["defconfig"].startswith("."):
        raise ProfileError("Unsafe kernel defconfig")
    if not re.fullmatch(r"[a-z0-9_/-]+\.dtb", kernel["dtb"]):
        raise ProfileError("Invalid DTB path")
    n = t["nand"]
    p = n["page_bytes"]
    e = n["erase_block_bytes"]
    if p != 2048 or e != 131072 or n["subpage_bytes"] != p:
        raise ProfileError("Unsupported NAND geometry; add validated backend first")
    if n["ubi_leb_bytes"] != e - 2 * p:
        raise ProfileError("UBI LEB/PEB mismatch")
    fields = ("protected_until", "kernel_offset", "dtb_offset", "ubi_offset", "end_offset")
    vals = [n[k] for k in fields]
    if not (0 < vals[0] == vals[1] < vals[2] < vals[3] < vals[4] == n["total_bytes"]):
        raise ProfileError("Invalid or unsafe NAND flash regions")
    if any(v % e for v in vals):
        raise ProfileError("NAND partitions must be eraseblock aligned")
    if (n["rootfs_max_lebs"] * n["ubi_leb_bytes"]) > (vals[4] - vals[3]):
        raise ProfileError("UBIFS logical volume exceeds physical partition")
    if t["bootloader"]["mode"] != "retain-vendor":
        raise ProfileError("Unverified bootloader replacement is forbidden")
    if t["application"]["enabled"]:
        raise ProfileError("Application integration has not been implemented")


def artifact_fits(t: dict, component: str, size: int) -> bool:
    n = t["nand"]
    boundaries = {
        "Image": (n["kernel_offset"], n["dtb_offset"]),
        "dtb": (n["dtb_offset"], n["ubi_offset"]),
        "ubi": (n["ubi_offset"], n["end_offset"]),
    }
    start, end = boundaries[component]
    return size > 0 and size <= end - start
