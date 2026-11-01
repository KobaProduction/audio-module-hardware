"""Read-only Windows preparation/backup utility for VK Capsula Mini A113X.

Original Linux flasher.sh remains authoritative for recovery and NAND writes.
No NAND erase, write or boot-environment modification is implemented here.
"""
import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent.parent
WINDOWS_DIR = Path(__file__).resolve().parent
DEFAULT_BACKEND = WINDOWS_DIR / "update.exe"
BACKUP_ROOT = WINDOWS_DIR / "backups"
KERNEL_ADDR = 0x01080000
ERASE_BLOCK = 0x20000
TRANSFER_CHUNK = 8 * 1024 * 1024

# The stock partition map comes from flasher.sh lines 48-58.
STOCK_PARTS = (
    ("bootloader", 0x00200000),
    ("tpl",        0x00800000),
    ("misc",       0x00200000),
    ("boot_a",     0x01000000),
    ("boot_b",     0x01000000),
    ("system_a",   0x04000000),
    ("system_b",   0x04000000),
    ("data",       0x04E00000),
)
# Preserve device-specific BBT, keys, U-Boot environment and vendor DTB.
RESERVED = (
    ("bbt",    0x00280000, 0x00080000),
    ("env",    0x00300000, 0x00100000),
    ("keys",   0x00400000, 0x00100000),
    ("dtbrsv", 0x00500000, 0x00080000),
    ("ddr",    0x00580000, 0x00040000),
)


class FlashToolError(Exception):
    """A precondition or backend operation failed; never proceed silently."""


@dataclass
class DumpResult:
    name: str
    expected_bytes: int
    actual_bytes: int
    sha256: str | None
    status: str
    detail: str = ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_image(image: Path | None = None) -> tuple[bool, str]:
    image = image if image is not None else ROOT / "fw_alpine" / "Image"
    if not image.is_file():
        return False, f"Missing {image}"
    with image.open("rb") as source:
        header = source.read(64)
    if len(header) != 64 or header[56:60] != b"ARM\x64":
        return False, "Linux Image ARM64 signature missing"
    if struct.unpack("<Q", header[8:16])[0] == 0:
        return False, "Linux Image text_offset is zero; incompatible with vendor booti"
    return True, "ARM64 image and nonzero text_offset verified"


def doctor(backend: Path) -> bool:
    print(f"Originals: {ROOT}")
    ok = True
    for path in (
        ROOT / "flasher.sh",
        ROOT / "howto.txt",
        ROOT / "update",
        ROOT / "fw_alpine" / "Image",
        ROOT / "fw_alpine" / "vk-mini-a113x.dtb",
        ROOT / "fw_alpine" / "alpine3.24.1_rootfs.ubi",
    ):
        found = path.is_file() and path.stat().st_size > 0
        print(f"{'OK' if found else 'MISSING'} {path.name} ({path.stat().st_size if found else 0} bytes)")
        ok &= found
    image_ok, message = validate_image()
    print(("OK " if image_ok else "ERROR ") + message)
    ok &= image_ok

    if backend.is_file():
        magic = backend.open("rb").read(2)
        if magic == b"MZ":
            print(f"Windows backend found: {backend}")
        else:
            print(f"ERROR: {backend} is not a Windows PE executable")
            ok = False
    else:
        print(f"BLOCKED: Windows Amlogic update.exe not found at {backend}")
        print("The existing 'update' in the original folder is Linux-only.")
        ok = False
    return bool(ok)


def usb_response_is_identified(output: str) -> bool:
    return "firmware version" in output.casefold() and not usb_response_is_error(output)


def usb_response_is_error(output: str) -> bool:
    lower = output.casefold()
    return "err:" in lower or "[info]failed" in lower


def bulk_payload(command: str) -> str:
    # The original script prefixes "echo; " for lost-byte workaround.
    payload = "echo; " + command
    if len(payload.encode("ascii")) > 63:
        raise FlashToolError("U-Boot bulkcmd exceeds 63-byte safe limit")
    return payload


class WindowsUpdateBackend:
    def __init__(self, executable: Path):
        if not executable.is_file():
            raise FlashToolError(f"Windows update.exe missing: {executable}")
        with executable.open("rb") as source:
            signature = source.read(2)
        if signature != b"MZ":
            raise FlashToolError(
                f"Windows update.exe missing or invalid: {executable}; do not use Linux 'update'"
            )
        self.executable = executable.resolve()

    def run(self, *args: str, timeout: int = 40) -> tuple[str, int]:
        try:
            proc = subprocess.run(
                [str(self.executable), *map(str, args)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise FlashToolError(f"update.exe {' '.join(args[:2])}: {exc}") from exc
        return proc.stdout + "\n" + proc.stderr, proc.returncode

    def find_device(self, seconds: float = 120) -> None:
        print("Searching for VK Mini USB bootloader. Connect/power-cycle when prompted.")
        end = time.monotonic() + seconds
        attempt = 0
        while time.monotonic() < end:
            attempt += 1
            reply, _ = self.run("identify", "7", timeout=5)
            if usb_response_is_identified(reply):
                print(f"Device detected (attempt {attempt}).")
                return
            if attempt % 10 == 0:
                print(f"Waiting for bootloader... ({int(end - time.monotonic())}s left)")
            # update.exe already takes ~0.3s per scan; no additional idle delay.
            # Retain serial (not overlapping) USB accesses.
        raise FlashToolError("No Amlogic bootloader identified; do not write anything.")

    def command(self, command: str) -> None:
        response, _ = self.run("bulkcmd", bulk_payload(command), timeout=40)
        if usb_response_is_error(response):
            raise FlashToolError(f"bulkcmd failed: {command}: {response[-350:]}")

    def read_partition(self, name: str, length: int, output: Path) -> None:
        response, _ = self.run(
            "mread", "store", name, "normal", hex(length), str(output),
            timeout=max(90, length // (1024 * 1024) * 12),
        )
        # Vendor update may return non-zero even after a valid partial NAND read.
        if usb_response_is_error(response) and not output.is_file():
            raise FlashToolError(f"mread partition {name}: {response[-350:]}")

    def read_flash_region(self, address: int, length: int, output: Path) -> None:
        with output.open("wb") as target:
            pos = 0
            while pos < length:
                step = min(TRANSFER_CHUNK, length - pos)
                self.command(f"nand read {hex(KERNEL_ADDR)} {hex(address + pos)} {hex(step)}")
                piece = output.with_suffix(".piece")
                try:
                    response, _ = self.run(
                        "mread", "mem", hex(KERNEL_ADDR), "normal", hex(step),
                        str(piece), timeout=120,
                    )
                    if not piece.is_file() or piece.stat().st_size != step:
                        raise FlashToolError(
                            f"Reserved NAND at {hex(address + pos)}: expected {step} bytes; "
                            f"got {piece.stat().st_size if piece.exists() else 0}. "
                            f"Backend: {response[-150:]}"
                        )
                    with piece.open("rb") as source:
                        shutil.copyfileobj(source, target)
                finally:
                    piece.unlink(missing_ok=True)
                pos += step


def result_for_dump(name: str, expected: int, file: Path, detail: str = "") -> DumpResult:
    got = file.stat().st_size if file.exists() else 0
    if got == expected:
        status = "ok"
    elif got == 0:
        status = "missing"
    elif got < expected and (expected - got) % ERASE_BLOCK == 0:
        status = "short-bad-blocks-unverified"
    else:
        status = "incomplete"
    return DumpResult(
        name, expected, got, sha256_file(file) if got else None,
        status, detail,
    )


def backup(backend: WindowsUpdateBackend, board: str, seconds: float) -> Path:
    if not board or not all(c.isascii() and (c.isalnum() or c in "-_") for c in board):
        raise FlashToolError("Board name may only contain ASCII letters, digits, - and _")
    target = BACKUP_ROOT / board / datetime.now().strftime("%Y%m%d-%H%M%S")
    if target.exists():
        raise FlashToolError(f"Backup destination exists: {target}")
    needed = sum(size for _, size in STOCK_PARTS) + sum(size for _, _, size in RESERVED)
    available = shutil.disk_usage(BACKUP_ROOT.parent).free
    if available < needed + 80 * 1024 * 1024:
        raise FlashToolError(f"Insufficient free space: need at least {needed // 1048576 + 80} MiB")
    backend.find_device(seconds=seconds)
    target.mkdir(parents=True)
    print(f"Sensitive device backup destination: {target}")
    results: list[DumpResult] = []
    try:
        for name, size in STOCK_PARTS:
            print(f"READ {name} ({size // 1048576} MiB)")
            temp = target / f"{name}.part"
            dest = target / f"{name}.bin"
            detail = ""
            try:
                backend.read_partition(name, size, temp)
            except FlashToolError as exc:
                detail = str(exc)
            result = result_for_dump(name, size, temp, detail)
            if temp.exists():
                temp.replace(dest)
            results.append(result)
            print(f"  {result.status}: {result.actual_bytes} / {size} bytes")
        for name, address, size in RESERVED:
            print(f"READ reserved/{name} ({size // 1024} KiB)")
            temp = target / f"rsv-{name}.part"
            dest = target / f"rsv-{name}.bin"
            detail = ""
            try:
                backend.read_flash_region(address, size, temp)
            except FlashToolError as exc:
                detail = str(exc)
            result = result_for_dump("rsv-" + name, size, temp, detail)
            if temp.exists():
                temp.replace(dest)
            results.append(result)
            print(f"  {result.status}: {result.actual_bytes} / {size} bytes")
    finally:
        manifest = {
            "schema_version": 1,
            "device": "VK Capsula Mini A113X (USB identity still requires physical verification)",
            "source": "native Windows read-only port; flasher.sh stock partitions",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "status": "complete-sizes-only" if all(x.status == "ok" for x in results) else "INCOMPLETE",
            "files": [asdict(x) for x in results],
            "warning": "Contains sensitive factory keys, network settings and tokens. Keep private.",
        }
        (target / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    print("Backup complete-size check:", manifest["status"])
    if manifest["status"] != "complete-sizes-only":
        print("WARNING: some segments were short/missing; do not flash yet.")
    print("Backup has NOT been tested for restore compatibility.")
    return target


def verify_backup(folder: Path) -> bool:
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise FlashToolError(f"Missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    good = True
    for entry in manifest["files"]:
        p = folder / (entry["name"] + ".bin")
        if not p.exists() or p.stat().st_size != entry["actual_bytes"]:
            print("BAD size/missing:", p.name)
            good = False
        elif entry["sha256"] != sha256_file(p):
            print("BAD SHA256:", p.name)
            good = False
        else:
            print("OK:", p.name, entry["actual_bytes"])
        good &= entry["status"] == "ok"
    print("Verified files and manifest" if good else "Backup incomplete or corrupted")
    print("This does not prove the backup can be restored or booted.")
    return good


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="VK Mini A113X: Windows USB detection and read-only backup. NO FLASHING."
    )
    parser.add_argument(
        "--update", type=Path, default=DEFAULT_BACKEND,
        help="Path to compatible Amlogic Windows update.exe (not Linux 'update')",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="Check firmware files and Windows USB backend")
    detect = sub.add_parser("detect", help="Identify USB bootloader without writing NAND")
    detect.add_argument("--timeout", type=float, default=120)
    save = sub.add_parser("backup", help="Read stock partitions and reserved areas")
    save.add_argument("--board", default="board-1")
    save.add_argument("--timeout", type=float, default=120)
    check = sub.add_parser("verify", help="Verify saved backup file sizes and SHA256")
    check.add_argument("folder", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return 0 if doctor(args.update) else 2
        if args.command == "verify":
            return 0 if verify_backup(args.folder) else 2
        backend = WindowsUpdateBackend(args.update)
        if args.command == "detect":
            backend.find_device(seconds=args.timeout)
        elif args.command == "backup":
            backup_folder = backup(backend, args.board, args.timeout)
            saved = json.loads((backup_folder / "manifest.json").read_text(encoding="utf-8"))
            return 0 if saved["status"] == "complete-sizes-only" else 2
        return 0
    except (FlashToolError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
