"""Strict target profile validation; never infer NAND geometry or layout."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVICES = ROOT / "builder" / "devices"
PLATFORMS = ROOT / "kernel" / "platforms"
HEX_SHA = re.compile(r"^[0-9a-f]{40}$")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class ProfileError(ValueError):
    pass


def load_target(name: str) -> dict:
    if not NAME.fullmatch(name):
        raise ProfileError("Invalid target name")
    path = DEVICES / name / "profile.json"
    if not path.is_file():
        raise ProfileError("Unknown builder device: " + name)
    target = json.loads(path.read_text(encoding="utf-8"))
    if target.get("id") != name:
        raise ProfileError("Device directory and profile ID mismatch")
    soc = target.get("soc", "")
    if not NAME.fullmatch(soc):
        raise ProfileError("Invalid SoC identifier")
    soc_file = PLATFORMS / (soc + ".json")
    if not soc_file.is_file():
        raise ProfileError("Unsupported SoC: " + soc)
    platform = json.loads(soc_file.read_text(encoding="utf-8"))
    if platform.get("schema") != 1 or platform.get("soc") != soc:
        raise ProfileError("SoC platform manifest mismatch")
    if target.get("architecture") != platform.get("architecture"):
        raise ProfileError("Device/SoC architecture mismatch")
    base_kernel = platform.get("kernel", {})
    device_kernel = target.get("kernel", {})
    if set(base_kernel) & set(device_kernel):
        raise ProfileError("Device may not override SoC kernel source or revision")
    target["kernel"] = {**base_kernel, **device_kernel}
    validate_target(target)
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
    for component, files in t["kernel"].get("runtime_firmware", {}).items():
        if not re.fullmatch(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+", component):
            raise ProfileError("Invalid capability firmware binding: " + component)
        if not isinstance(files, list):
            raise ProfileError("Driver firmware list must be a list")
        for filename in files:
            if (not isinstance(filename, str)
                    or filename.startswith("/")
                    or ".." in filename.split("/")
                    or not re.fullmatch(r"[a-zA-Z0-9_./-]+", filename)):
                raise ProfileError("Unsafe runtime firmware filename")
    if t["application"]["enabled"]:
        raise ProfileError("Application integration has not been implemented")
    components = t.get("firmware", {}).get("components")
    if not isinstance(components, list) or "base" not in components:
        raise ProfileError("Every device must select the base firmware component")
    if any(not isinstance(x, str) or not NAME.fullmatch(x) for x in components):
        raise ProfileError("Invalid firmware component name")
    if len(set(components)) != len(components):
        raise ProfileError("Duplicate selected firmware component")


def artifact_fits(t: dict, component: str, size: int) -> bool:
    n = t["nand"]
    boundaries = {
        "Image": (n["kernel_offset"], n["dtb_offset"]),
        "dtb": (n["dtb_offset"], n["ubi_offset"]),
        "ubi": (n["ubi_offset"], n["end_offset"]),
    }
    start, end = boundaries[component]
    return size > 0 and size <= end - start
