"""Host-side firmware input attestation; no device access or flash operations.

Checks declared public build sources and Alpine package resolution across the
rootfs/image split. This is provenance, NOT a fully reproducible package lock.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import stat

ROOT = Path(__file__).resolve().parents[1]
STAMP_NAME = "build-inputs.json"
PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9+_.-]*\Z")


class InputAttestationError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_paths(target: dict, root: Path) -> list[Path]:
    device = target["id"]
    soc = target["soc"]
    files = [root / item for item in (
        "builder/build.py",
        "builder/input_attestation.py",
        "builder/kernel_config.py",
        "builder/kernel_source.py",
        "builder/profile.py",
        "hal/manifest.py",
        "firmware/updates/persistence.py",
        "firmware/alpine/sources.json",
        "firmware/alpine/components.json",
        f"kernel/platforms/{soc}.json",
        f"builder/devices/{device}/profile.json",
        f"builder/devices/{device}/capabilities.json",
        f"builder/devices/{device}/persistence.json",
    )]
    for patch in target["kernel"].get("patches", []):
        files.append(root / patch)
    for overlay in (
        root / "firmware/alpine/overlay",
        root / "builder/devices" / device / "overlay",
    ):
        if overlay.is_symlink():
            raise InputAttestationError("Overlay root must not be a symlink")
        if not overlay.is_dir():
            raise InputAttestationError("Expected firmware/device overlay directory missing")
        for path in sorted(overlay.rglob("*")):
            if path.is_symlink():
                raise InputAttestationError("Overlay contains a symlink: " + path.relative_to(root).as_posix())
            if path.is_file():
                files.append(path)
            elif not path.is_dir():
                raise InputAttestationError("Unsupported overlay entry")
    return sorted(files)


def build_inputs(target: dict, *, root: Path = ROOT) -> dict:
    """Fingerprint tracked composition inputs, not a personal SSH provisioning key."""
    records = []
    for path in _source_paths(target, root):
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
            raise InputAttestationError("Build input must be a regular file")
        data = path.read_bytes()
        records.append((path.relative_to(root).as_posix(),
                        stat.S_IMODE(path.stat().st_mode), _sha256(data)))
    fingerprint = _sha256(json.dumps(records, separators=(",", ":"),
                                     ensure_ascii=True).encode("utf-8"))
    return {"sha256": fingerprint, "file_count": len(records)}


def _package_db(rootfs: Path) -> Path:
    path = rootfs / "lib/apk/db/installed"
    if not path.is_file() or path.is_symlink():
        raise InputAttestationError("Alpine installed package database is missing")
    return path


def installed_packages(rootfs: Path) -> list[dict[str, str]]:
    """Parse apk installed-db P/V fields without reading package config/secrets."""
    data = _package_db(rootfs).read_text(encoding="utf-8")
    packages: dict[str, str] = {}
    for stanza in data.split("\n\n"):
        if not stanza.strip():
            continue
        fields: dict[str, str] = {}
        for line in stanza.splitlines():
            if line.startswith(("P:", "V:")):
                if line[:1] in fields:
                    raise InputAttestationError("Duplicate Alpine package field")
                fields[line[:1]] = line[2:]
        name, version = fields.get("P", ""), fields.get("V", "")
        if (not PACKAGE_NAME.fullmatch(name) or not version or
                any(ord(char) < 33 or ord(char) > 126 for char in version) or
                name in packages):
            raise InputAttestationError("Malformed or duplicated Alpine package entry")
        packages[name] = version
    if not packages:
        raise InputAttestationError("Alpine installed package database is empty")
    return [{"name": name, "version": version}
            for name, version in sorted(packages.items())]


def capture_stage(target: dict, work: Path, rootfs: Path, *, root: Path = ROOT) -> dict:
    """Store nonsecret provenance only after successful Alpine rootfs staging."""
    stamp = work / STAMP_NAME
    if stamp.exists() or stamp.is_symlink():
        raise InputAttestationError("Existing input attestation; refusing implicit overwrite")
    inventory = installed_packages(rootfs)
    record = {"schema": 1, "target": target["id"],
              "kernel_revision": target["kernel"]["revision"],
              "source_inputs": build_inputs(target, root=root),
              "apk_database_sha256": _sha256(_package_db(rootfs).read_bytes()),
              "alpine_package_versions_locked": False,
              "resolved_packages": inventory}
    stamp.write_text(json.dumps(record, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return record


def verify_stage(target: dict, work: Path, rootfs: Path, *, root: Path = ROOT) -> dict:
    """Reject image packaging if source profiles/overlays or apk-db drifted."""
    stamp = work / STAMP_NAME
    if not stamp.is_file() or stamp.is_symlink():
        raise InputAttestationError("No successful rootfs stage input attestation")
    record = json.loads(stamp.read_text(encoding="utf-8"))
    if (record.get("schema") != 1 or record.get("target") != target["id"]
            or record.get("kernel_revision") != target["kernel"]["revision"]
            or record.get("alpine_package_versions_locked") is not False):
        raise InputAttestationError("Staged input attestation does not match selected target")
    if record.get("source_inputs") != build_inputs(target, root=root):
        raise InputAttestationError("Build inputs changed since rootfs stage; rebuild from clean rootfs")
    if (record.get("apk_database_sha256") != _sha256(_package_db(rootfs).read_bytes())
            or record.get("resolved_packages") != installed_packages(rootfs)):
        raise InputAttestationError("Alpine installed package set changed since rootfs stage")
    return record
