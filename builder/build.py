#!/usr/bin/env python3
"""Source-oriented Alpine firmware build and local packaging. Never flashes NAND."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from builder.profile import ProfileError, artifact_fits, load_target  # noqa: E402
from hal.manifest import CapabilityError, compile_manifest, write_manifest  # noqa: E402
from firmware.updates.persistence import plan as persistence_plan  # noqa: E402
from builder.storage import (  # noqa: E402
    StoragePlanError, plan_storage, audit_immutable_rootfs,
)
from builder.kernel_config import (  # noqa: E402
    KernelConfigurationError, desired_symbols, write_config_overlay,
    assert_options_match,
)

SOURCES = json.loads((ROOT / "firmware/alpine/sources.json").read_text(encoding="utf-8"))


class BuildError(RuntimeError):
    pass


def checked(command: list[str], *, cwd: Path | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verified_fetch(entry: dict, dest: Path) -> Path:
    url = entry["url"]
    expected = entry["sha256"]
    if not url.startswith("https://") or len(expected) != 64:
        raise BuildError("Untrusted source entry")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and hash_file(dest) == expected:
        return dest
    if dest.exists():
        raise BuildError("Cached source hash mismatch: " + str(dest))
    tmp = dest.with_suffix(dest.suffix + ".partial")
    if tmp.exists():
        raise BuildError("Remove incomplete download after inspecting it: " + str(tmp))
    try:
        with urllib.request.urlopen(url, timeout=60) as response, tmp.open("wb") as out:
            shutil.copyfileobj(response, out)
        if hash_file(tmp) != expected:
            raise BuildError("Downloaded source SHA256 mismatch: " + url)
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def fetch_kernel(t: dict, work: Path) -> Path:
    src = work / "kernel-src"
    expected = t["kernel"]["revision"]
    if src.exists():
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
        if actual != expected:
            raise BuildError("Existing kernel checkout has wrong commit")
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=src):
            raise BuildError("Kernel checkout has local modifications")
        return src
    src.parent.mkdir(parents=True, exist_ok=True)
    checked(["git", "init", "-q", str(src)])
    checked(["git", "remote", "add", "origin", t["kernel"]["source"]], cwd=src)
    # Fetch the exact commit, never trust mutable branch HEAD.
    checked(["git", "-c", "core.sparseCheckout=false", "fetch", "--depth=1",
             "--filter=blob:none", "origin", expected], cwd=src)
    checked(["git", "checkout", "--detach", "FETCH_HEAD"], cwd=src)
    actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=src, text=True).strip()
    if actual != expected:
        raise BuildError("Kernel git revision mismatch")
    return src


def kernel_build(t: dict, work: Path, jobs: int) -> None:
    if not shutil.which("aarch64-linux-gnu-gcc"):
        raise BuildError("Missing aarch64-linux-gnu-gcc cross compiler")
    src = fetch_kernel(t, work)
    output = work / "kernel-out"
    image = output / "arch/arm64/boot/Image"
    dtb = output / "arch/arm64/boot/dts" / t["kernel"]["dtb"]
    base = ["make", "-C", str(src), "O=" + str(output), "ARCH=arm64",
            "CROSS_COMPILE=aarch64-linux-gnu-"]
    checked(base + [t["kernel"]["defconfig"]])
    config = output / ".config"
    selected_options = desired_symbols(t)
    write_config_overlay(config, selected_options)
    checked(base + ["olddefconfig"])
    assert_options_match(config, selected_options)
    checked(base + ["-j", str(jobs), "Image", "dtbs", "modules"])
    if not image.is_file() or image.stat().st_size < 1024 * 1024 or not dtb.is_file():
        raise BuildError("Kernel Image or target DTB missing")
    artifacts = work / "images"
    artifacts.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(image, artifacts / "Image")
    shutil.copyfile(dtb, artifacts / "board.dtb")
    print("KERNEL_BUILT", image.stat().st_size, dtb.stat().st_size)


def checked_tar_extract(archive: Path, rootfs: Path) -> None:
    # Only Alpine HTTPS tarball with pinned SHA is accepted before extraction.
    with tarfile.open(archive, "r:gz") as tf:
        for member in tf.getmembers():
            name = member.name
            if name.startswith("/") or ".." in Path(name).parts or member.isdev():
                raise BuildError("Unsafe Alpine archive member")
        allowed_absolute_links = {"/bin/busybox", "/etc/ssl/certs", "/etc/ssl/cert.pem"}
        for member in tf.getmembers():
            if member.issym() and member.linkname.startswith("/"):
                if member.linkname not in allowed_absolute_links:
                    raise BuildError("Unexpected absolute symlink in pinned Alpine tarball")
    # Alpine minirootfs intentionally includes absolute BusyBox links. Python's
    # restrictive data filter rejects them. Use tar only after SHA256 pin and
    # member/path allowlist validation, preserving numeric ownership as root.
    checked(["tar", "--numeric-owner", "-xzf", str(archive), "-C", str(rootfs)])


def selected_components(t: dict) -> list[dict]:
    source = ROOT / "firmware/alpine/components.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    if data.get("schema") != 1:
        raise BuildError("Unknown firmware component manifest schema")
    catalog = data["components"]
    requested = t["firmware"]["components"]
    unknown = set(requested) - set(catalog)
    if unknown:
        raise BuildError("Unknown firmware components: " + ", ".join(sorted(unknown)))
    return [catalog[name] for name in requested]


def apk_packages(t: dict) -> list[str]:
    names: set[str] = set()
    for component in selected_components(t):
        for package in component["packages"]:
            if not package or not package.replace("-", "").replace("_", "").isalnum():
                raise BuildError("Invalid Alpine package name")
            names.add(package)
    return sorted(names)


def enabled_services(t: dict) -> dict[str, list[str]]:
    services: dict[str, set[str]] = {}
    for component in selected_components(t):
        for level, names in component.get("services", {}).items():
            if level not in ("sysinit", "boot", "default"):
                raise BuildError("Unsupported OpenRC runlevel")
            services.setdefault(level, set()).update(names)
    return {level: sorted(names) for level, names in services.items()}


def stage_rootfs(t: dict, work: Path, authorized_key: Path | None) -> None:
    if os.geteuid() != 0:
        raise BuildError("Root privileges are required to preserve ownership and package files")
    cache = work / "downloads"
    mini = verified_fetch(SOURCES["minirootfs"], cache / "alpine-minirootfs.tar.gz")
    apk = verified_fetch(SOURCES["host_apk_static"], cache / "apk.static")
    apk.chmod(0o755)
    rootfs = work / "rootfs"
    if rootfs.exists():
        raise BuildError("Rootfs already exists; refusing implicit overwrite")
    rootfs.mkdir(parents=True)
    checked_tar_extract(mini, rootfs)
    if not (rootfs / "etc/apk/keys").is_dir():
        raise BuildError("Alpine trusted signing keys absent")
    repos = SOURCES["apk_repositories"]
    (rootfs / "etc/apk/repositories").write_text("\n".join(repos) + "\n")
    # apk.static executes natively on x86_64, but installs aarch64 packages.
    # No foreign-architecture post-install script is executed during staging.
    checked([str(apk), "--root", str(rootfs), "--arch", t["architecture"],
             "--no-scripts", "--update-cache", "add", *apk_packages(t)])
    apply_overlay(t, rootfs, authorized_key)
    print("HAL_DESCRIPTOR_STAGED", write_manifest(t, rootfs))
    print("ROOTFS_STAGED", rootfs)


def apply_overlay(t: dict, rootfs: Path, authorized_key: Path | None) -> None:
    # Shared overlay first, per-device deltas second (OpenIPC-style).
    for overlay in (ROOT / "firmware/alpine/overlay",
                    ROOT / "builder" / "devices" / t["id"] / "overlay"):
        if not overlay.is_dir():
            continue
        for path in sorted(overlay.rglob("*")):
            rel = path.relative_to(overlay)
            dest = rootfs / rel
            if path.is_dir():
                dest.mkdir(parents=True, exist_ok=True)
            elif path.is_file():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, dest)
                if str(rel).startswith("etc/init.d/"):
                    dest.chmod(0o755)
    inittab = rootfs / "etc/inittab"
    if inittab.is_file():
        data = inittab.read_text(encoding="utf-8")
        line = "ttyGS0::respawn:/sbin/getty -L 115200 ttyGS0 vt100"
        if line not in data:
            inittab.write_text(data.rstrip() + "\n" + line + "\n")
    if authorized_key is not None:
        content = authorized_key.read_text(encoding="utf-8").strip()
        if not content.startswith(("ssh-ed25519 ", "ssh-rsa ", "ecdsa-sha2-")):
            raise BuildError("Invalid SSH authorized public key")
        ssh = rootfs / "root/.ssh"
        ssh.mkdir(mode=0o700, parents=True, exist_ok=True)
        (ssh / "authorized_keys").write_text(content + "\n")
        (ssh / "authorized_keys").chmod(0o600)
    # Enable only services that are installed and required for early access.
    enabled = enabled_services(t)
    for level, names in enabled.items():
        for service in names:
            definition = rootfs / "etc/init.d" / service
            if not definition.is_file():
                raise BuildError("Selected service not installed: " + service)
            runlevel = rootfs / "etc/runlevels" / level
            runlevel.mkdir(parents=True, exist_ok=True)
            link = runlevel / service
            if not link.exists() and not link.is_symlink():
                link.symlink_to("../../init.d/" + service)


def stage_driver_firmware(t: dict, kernel_source: Path, rootfs: Path) -> None:
    active_features = {cap["id"] for cap in compile_manifest(t)["capabilities"]}
    for feature, names in t["kernel"].get("runtime_firmware", {}).items():
        if feature not in active_features:
            continue
        for filename in names:
            if filename.startswith("/") or ".." in Path(filename).parts:
                raise BuildError("Unsafe runtime firmware filename")
            source = kernel_source / "firmware" / filename
            if not source.is_file():
                raise BuildError("Missing selected device firmware: " + filename)
            target = rootfs / "lib/firmware" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)


def pack_images(t: dict, work: Path) -> None:
    if not shutil.which("mkfs.ubifs") or not shutil.which("ubinize"):
        raise BuildError("mtd-utils: mkfs.ubifs and ubinize are required")
    rootfs = work / "rootfs"
    if not rootfs.is_dir():
        raise BuildError("Rootfs stage missing")
    if os.geteuid() != 0:
        raise BuildError("Root required to package rootfs with correct ownership")
    src = work / "kernel-src"
    out = work / "kernel-out"
    if not (src / "Makefile").is_file() or not out.is_dir():
        raise BuildError("Built kernel is needed to install matching modules")
    if not (rootfs / "root/.ssh/authorized_keys").is_file():
        raise BuildError("Refusing unreachable rootfs: provision a PUBLIC SSH key at rootfs stage")
    # Device selects driver firmware per enabled component. Never vendor
    # calibration/key blobs or enable disabled peripherals implicitly.
    stage_driver_firmware(t, src, rootfs)
    checked(["make", "-C", str(src), "O=" + str(out), "ARCH=arm64",
             "CROSS_COMPILE=aarch64-linux-gnu-", "INSTALL_MOD_PATH=" + str(rootfs),
             "modules_install"])
    geometry = t["nand"]
    outdir = work / "images"
    outdir.mkdir(parents=True, exist_ok=True)
    ubifs = outdir / "rootfs.ubifs"
    ubi = outdir / "rootfs.ubi"
    checked(["mkfs.ubifs", "-r", str(rootfs), "-o", str(ubifs), "-m",
             str(geometry["page_bytes"]), "-e", str(geometry["ubi_leb_bytes"]),
             "-c", str(geometry["rootfs_max_lebs"]), "-F"])
    config = work / "ubinize.ini"
    config.write_text("[rootfs]\nmode=ubi\nimage=" + str(ubifs) +
                      "\nvol_id=0\nvol_type=dynamic\nvol_name=rootfs\nvol_flags=autoresize\n")
    checked(["ubinize", "-o", str(ubi), "-m", str(geometry["page_bytes"]),
             "-p", str(geometry["erase_block_bytes"]), "-s",
             str(geometry["subpage_bytes"]), str(config)])
    package_manifest(t, work)


def package_manifest(t: dict, work: Path) -> None:
    artifacts = work / "images"
    files = [("Image","Image"), ("board.dtb","dtb"), ("rootfs.ubi","ubi")]
    hal_descriptor = compile_manifest(t)
    output: dict = {"schema": 1, "target": t["id"], "status": "NOT_HARDWARE_VALIDATED",
                    "application_included": False, "bootloader": "retain-vendor",
                    "kernel_revision": t["kernel"]["revision"],
                    "hal_abi_major": hal_descriptor["version"],
                    "capabilities_declared": [
                        c["id"] for c in hal_descriptor["capabilities"]
                    ],
                    "runtime_hal_verified": False,
                    "update_persistence": {
                        "system_update": {
                            "can_apply": persistence_plan(t, "system-update")["can_apply"],
                            "requires_external_identity_backup": True,
                            "requires_external_user_backup": True
                        },
                        "clean_install": {
                            "can_apply": persistence_plan(t, "clean-install")["can_apply"],
                            "requires_external_identity_backup": True
                        }
                    },
                    "artifacts": {}}
    for filename, slot in files:
        f = artifacts / filename
        if not f.is_file() or not artifact_fits(t, slot, f.stat().st_size):
            raise BuildError("Artifact missing or too large: " + filename)
        if filename == "Image":
            with f.open("rb") as src:
                header = src.read(64)
            if len(header) < 64 or header[56:60] != b"ARM\x64":
                raise BuildError("Kernel ARM64 Image header invalid")
        if filename == "board.dtb":
            with f.open("rb") as src:
                if src.read(4) != bytes.fromhex("d00dfeed"):
                    raise BuildError("FDT DTB magic invalid")
        if filename == "rootfs.ubi":
            with f.open("rb") as src:
                if src.read(4) != b"UBI#":
                    raise BuildError("UBI header invalid")
        output["artifacts"][filename] = {"bytes": f.stat().st_size,
                                        "sha256": hash_file(f),
                                        "slot": slot}
    (artifacts / "manifest.json").write_text(json.dumps(output, indent=2) + "\n")
    print("LOCAL_IMAGE_ASSEMBLED_NOT_FLASH_APPROVED")


def plan(t: dict, work: Path) -> None:
    packages = apk_packages(t)
    descriptor = compile_manifest(t)
    storage = plan_storage(t)
    summary = {"id": t["id"], "soc": t["soc"], "kernel_sha": t["kernel"]["revision"],
               "alpine": t["os"]["release"], "packages": len(packages),
               "components": t["firmware"]["components"],
               "hal_abi": descriptor["version"],
               "capabilities_declared": len(descriptor["capabilities"]),
               "protected_nand": [0, t["nand"]["protected_until"]],
               "rootfs": "Alpine minirootfs + signed APK packages + overlay",
               "application_included": False, "bootloader_rebuild": False,
               "status": "source-build-recipe-only",
               "storage_layout_active": t["storage"]["active_layout"],
               "storage_candidate": storage.status,
               "storage_candidate_installable": storage.may_install}
    print(json.dumps(summary, indent=2))


def main() -> int:
    p = argparse.ArgumentParser(description="Build source-based Audio Module images; no flash actions")
    p.add_argument("phase", choices=("plan", "storage-plan", "storage-audit",
                                     "fetch-kernel",
                                     "kernel", "rootfs", "image", "all"))
    p.add_argument("--target", default="capsula-mini-native")
    p.add_argument("--work", type=Path, default=ROOT / ".work" / "capsula-mini-native")
    p.add_argument("--jobs", type=int, default=min(os.cpu_count() or 2, 8))
    p.add_argument("--authorized-key-file", type=Path,
                   help="Optional local PUBLIC SSH key (never tracked)")
    args = p.parse_args()
    try:
        if args.jobs < 1 or args.jobs > 64:
            raise BuildError("Invalid jobs count")
        t = load_target(args.target)
        work = args.work.expanduser().resolve()
        if work == ROOT or ROOT in work.parents and not (ROOT / ".work") in work.parents:
            raise BuildError("Work directory must not overwrite repository sources")
        if args.phase == "plan":
            plan(t, work)
        elif args.phase == "storage-plan":
            print(json.dumps(plan_storage(t).to_dict(), indent=2))
        elif args.phase == "storage-audit":
            result = audit_immutable_rootfs(work / "rootfs")
            print(json.dumps(result, indent=2))
            if not result["safe_to_package_as_immutable_lower"]:
                raise BuildError("Rootfs contains device-specific mutable state; not suitable for immutable lower")
        elif args.phase == "fetch-kernel":
            fetch_kernel(t, work)
        elif args.phase == "kernel":
            kernel_build(t, work, args.jobs)
        elif args.phase == "rootfs":
            stage_rootfs(t, work, args.authorized_key_file)
        elif args.phase == "image":
            pack_images(t, work)
        else:
            kernel_build(t, work, args.jobs)
            stage_rootfs(t, work, args.authorized_key_file)
            pack_images(t, work)
        return 0
    except (BuildError, ProfileError, StoragePlanError,
            CapabilityError, KernelConfigurationError,
            OSError, subprocess.CalledProcessError,
            ValueError, KeyError) as exc:
        print("BUILD_FAILED:", exc, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
