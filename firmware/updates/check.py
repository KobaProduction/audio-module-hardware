"""Offline, signature-verified release compatibility check.

This is a host-side reference checker. No on-device Python, fetching,
automatic scheduler, NAND writer, or upgrade application is installed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit

from builder.profile import artifact_fits, load_target

MAX_MANIFEST_BYTES = 65536
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SEMVER = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class ReleaseCheckError(ValueError):
    pass


def parse_version(version: str) -> tuple[int, int, int]:
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        raise ReleaseCheckError("Version must be numeric MAJOR.MINOR.PATCH")
    return tuple(int(p) for p in version.split("."))


def verify_ed25519(manifest: Path, signature: Path, trusted_public_key: Path) -> None:
    if not all(x.is_file() for x in (manifest, signature, trusted_public_key)):
        raise ReleaseCheckError("Manifest/signature/trusted public key missing")
    if manifest.stat().st_size < 10 or manifest.stat().st_size > MAX_MANIFEST_BYTES:
        raise ReleaseCheckError("Manifest length invalid")
    if signature.stat().st_size != 64:
        raise ReleaseCheckError("Expected a raw Ed25519 signature")
    try:
        result = subprocess.run(
            ["openssl", "pkeyutl", "-verify", "-rawin", "-pubin",
             "-inkey", str(trusted_public_key), "-sigfile", str(signature),
             "-in", str(manifest)],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise ReleaseCheckError("Signature verifier unavailable") from exc
    if result.returncode != 0:
        raise ReleaseCheckError("Invalid signature or untrusted release")


def check_release(
    target: dict,
    installed_version: str,
    manifest_path: Path,
    signature_path: Path,
    public_key_path: Path,
) -> dict:
    """Validate signed metadata only, never download payloads or touch NAND."""
    verify_ed25519(manifest_path, signature_path, public_key_path)
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ReleaseCheckError("Invalid signed release JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ReleaseCheckError("Unsupported signed release manifest")
    if manifest.get("target") != target["id"] or manifest.get("soc") != target["soc"]:
        raise ReleaseCheckError("Release is for another hardware target or SoC")
    if manifest.get("hal_abi_major") != 1:
        raise ReleaseCheckError("Incompatible HAL interface")
    if manifest.get("bootloader") != "retain-vendor":
        raise ReleaseCheckError("Bootloader replacement is not allowed")
    if manifest.get("hardware_approved") is not True:
        raise ReleaseCheckError("Release lacks hardware acceptance")
    if manifest.get("kernel_revision") != target["kernel"]["revision"]:
        raise ReleaseCheckError("Unreviewed kernel revision change")
    installed = parse_version(installed_version)
    offered = parse_version(manifest.get("version"))
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"Image", "board.dtb", "rootfs.ubi"}:
        raise ReleaseCheckError("Incomplete or unexpected artifact set")
    for name, artifact in artifacts.items():
        slot = {"Image": "Image", "board.dtb": "dtb", "rootfs.ubi": "ubi"}[name]
        if not isinstance(artifact, dict):
            raise ReleaseCheckError("Invalid artifact metadata")
        length, digest, url = artifact.get("bytes"), artifact.get("sha256"), artifact.get("url")
        if type(length) is not int or not artifact_fits(target, slot, length):
            raise ReleaseCheckError("Artifact too large or invalid for NAND slot: " + name)
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ReleaseCheckError("Invalid artifact SHA-256")
        if not isinstance(url, str):
            raise ReleaseCheckError("Invalid artifact URL")
        parts = urlsplit(url)
        if (parts.scheme != "https" or not parts.hostname or parts.username is not None
                or parts.password is not None or parts.fragment):
            raise ReleaseCheckError("Artifact requires an HTTPS URL without credentials")
    if offered < installed:
        raise ReleaseCheckError("Downgrade rejected")
    return {
        "target": target["id"],
        "installed_version": installed_version,
        "available_version": manifest["version"],
        "status": "upgrade-available" if offered > installed else "up-to-date",
        "signature": "ed25519-verified",
        "artifact_digests_checked": False,
        "may_flash": False,
        "note": "No download, apply, rollback or NAND write implementation",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check an offline signed release; no firmware writes",
    )
    parser.add_argument("--target", required=True)
    parser.add_argument("--installed", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--signature", type=Path, required=True)
    parser.add_argument("--trusted-public-key", type=Path, required=True)
    args = parser.parse_args()
    try:
        outcome = check_release(
            load_target(args.target), args.installed,
            args.manifest, args.signature, args.trusted_public_key,
        )
    except (ReleaseCheckError, OSError, ValueError) as exc:
        print("UPDATE_CHECK_FAILED:", exc, file=sys.stderr)
        return 2
    print(json.dumps(outcome, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
