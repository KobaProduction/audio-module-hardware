"""Read-only OpenWrt source/port readiness; never builds or flashes images."""
from __future__ import annotations

import json
from pathlib import Path
import re

from builder.storage import plan_storage

ROOT = Path(__file__).resolve().parents[1]
SOURCE_MANIFEST = ROOT / "firmware/openwrt/sources.json"
PORT_FILE = "openwrt-port.json"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
TAG = re.compile(r"v[0-9]+\.[0-9]+\.[0-9]+\Z")
NAME = re.compile(r"[a-z][a-z0-9-]*\Z")


class OpenWrtPortError(ValueError):
    pass


def validate_source_pins(sources: dict) -> None:
    if sources.get("schema") != 1 or sources.get("status") != "source-baseline-only":
        raise OpenWrtPortError("Unrecognized OpenWrt source manifest")
    upstream = sources.get("upstream", {})
    if (upstream.get("repository") != "https://github.com/openwrt/openwrt.git"
            or not TAG.fullmatch(upstream.get("tag", ""))
            or not SHA40.fullmatch(upstream.get("commit", ""))
            or not SHA40.fullmatch(upstream.get("feeds_manifest_git_blob", ""))):
        raise OpenWrtPortError("OpenWrt source/tag/feeds manifest must be pinned")
    feeds = sources.get("feeds")
    if not isinstance(feeds, list) or not feeds:
        raise OpenWrtPortError("Missing pinned OpenWrt feeds")
    names: set[str] = set()
    for feed in feeds:
        name = feed.get("name", "")
        url = feed.get("repository", "")
        if (not isinstance(name, str) or not NAME.fullmatch(name)
                or name in names or not isinstance(url, str)
                or not url.startswith(("https://git.openwrt.org/", "https://github.com/openwrt/"))
                or not SHA40.fullmatch(feed.get("commit", ""))):
            raise OpenWrtPortError("Invalid or unpinned OpenWrt feed")
        names.add(name)


def plan_openwrt(target: dict) -> dict:
    """Return source/port facts, with every build/install permission denied."""
    sources = json.loads(SOURCE_MANIFEST.read_text(encoding="utf-8"))
    validate_source_pins(sources)
    path = ROOT / "builder/devices" / target["id"] / PORT_FILE
    port = json.loads(path.read_text(encoding="utf-8"))
    if (port.get("schema") != 1 or port.get("device") != target["id"]
            or port.get("status") != "research-only"):
        raise OpenWrtPortError("Missing or invalid research-only OpenWrt device port")
    expected_false = (
        "upstream_family_present_in_pinned_release", "native_target_port_implemented",
        "kernel_dts_driver_port_verified", "feeds_and_packages_resolved",
        "toolchain_build_verified", "image_recipe_implemented",
        "ubi_artifact_verified", "hardware_boot_and_recovery_verified",
        "replace_active_alpine_rootfs", "allow_nand_writes", "allow_sysupgrade",
    )
    if any(port.get(key) is not False for key in expected_false):
        raise OpenWrtPortError("OpenWrt port cannot be enabled without a verified port contract")
    if (port.get("preserve_existing_vendor_boot_chain") is not True
            or port.get("preserve_existing_factory_partitions") is not True
            or target["bootloader"]["mode"] != "retain-vendor"):
        raise OpenWrtPortError("Factory boot chain protection must remain enabled")
    storage = plan_storage(target)
    if storage.may_install:
        raise OpenWrtPortError("Unexpected storage install authorization")
    return {
        "schema": 1,
        "device": target["id"],
        "soc": target["soc"],
        "status": "RESEARCH_ONLY_NOT_BUILDABLE",
        "source": sources["upstream"],
        "feed_commits": {feed["name"]: feed["commit"] for feed in sources["feeds"]},
        "proposed_target": port["proposed_target_family"] + "/" + port["proposed_subtarget"],
        "existing_os_unchanged": target["os"]["distribution"],
        "existing_kernel_revision": target["kernel"]["revision"],
        "physical_nand_layout_unchanged": True,
        "may_build_openwrt_image": False,
        "may_install": False,
        "may_sysupgrade": False,
        "blockers": [
            "No upstream A113X target or verified target/linux port",
            "No 6.12-to-A113X kernel/DTS/driver integration or package mapping",
            "No OpenWrt image/rootfs/UBI or hardware boot/recovery acceptance",
        ],
    }
