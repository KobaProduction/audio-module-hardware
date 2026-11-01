"""Native Windows flasher for VK Capsula Mini A113X, based on author's flasher.sh.
Reads back each written NAND chunk. Never writes vendor NAND below 0x01200000.
"""
if __name__ == "__main__":
    raise SystemExit("LEGACY REFERENCE DISABLED: requires profile-driven port and recovery validation.")

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from tempfile import TemporaryDirectory

DIR = Path(__file__).resolve().parent
ORIGINAL = DIR.parent
BACKUP = DIR / "backups" / "capsula-a113x" / "20261101-095750"
UPDATE = DIR / "update.exe"
IMAGE = ORIGINAL / "fw_alpine" / "Image"
DTB = ORIGINAL / "fw_alpine" / "vk-mini-a113x.dtb"
UBI = ORIGINAL / "fw_alpine" / "alpine3.24.1_rootfs.ubi"
LOG = DIR / "alpine_flash_log.jsonl"

KERNEL_OFF, DTB_OFF, UBI_OFF, FLASH_END = 0x01200000, 0x02B00000, 0x02C00000, 0x10000000
KERNEL_RAM, DTB_RAM = 0x01080000, 0x01000000
ENV_RAM, ENV_SIZE = 0x02000000, 0x10000
ERASE_BLOCK, PAGE, CHUNK, BOOTDELAY = 0x20000, 2048, 8 * 1024 * 1024, 1
WINTOOL_SHA = "F1DE686CF4FF770EE9DF0ACC2721E6A8195C81B556CA8894C04EB3BAC7CB2CAA"


class FlashError(Exception):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as reader:
        for block in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def aligned(n: int, unit: int) -> int:
    return ((n + unit - 1) // unit) * unit


def note(stage: str, **data: object) -> None:
    record = {"timestamp": datetime.now(timezone.utc).isoformat(), "stage": stage, **data}
    with LOG.open("a", encoding="utf-8") as writer:
        writer.write(json.dumps(record, ensure_ascii=False) + "\n")
        writer.flush()
    print("STAGE", stage, flush=True)


def preflight() -> dict[str, object]:
    if not UPDATE.is_file() or sha256(UPDATE) != WINTOOL_SHA:
        raise FlashError("Windows update.exe has unexpected SHA256")
    for source in (IMAGE, DTB, UBI):
        if not source.is_file():
            raise FlashError(f"Missing firmware image: {source}")
    manifestfile = BACKUP / "manifest.json"
    rawmeta = BACKUP / "nand-full.raw.json"
    rawfile = BACKUP / "nand-full.raw.bin"
    if not manifestfile.is_file() or not rawmeta.is_file() or not rawfile.is_file():
        raise FlashError("Device-specific backup missing: do NOT erase NAND")
    manifest = json.loads(manifestfile.read_text(encoding="utf-8"))
    entries = manifest["files"]
    expected_names = {
        "bootloader", "tpl", "misc", "boot_a", "boot_b",
        "system_a", "system_b", "data",
        "rsv-bbt", "rsv-env", "rsv-keys", "rsv-dtbrsv", "rsv-ddr",
    }
    if {entry["name"] for entry in entries} != expected_names:
        raise FlashError("Device backup partition set differs from expected 13 files")
    for entry in entries:
        f = BACKUP / (entry["name"] + ".bin")
        if not f.is_file() or f.stat().st_size != entry["actual_bytes"]:
            raise FlashError(f"Saved partition missing/size changed: {f}")
        if sha256(f) != entry["sha256"].upper():
            raise FlashError(f"Saved partition SHA256 changed: {f}")
        if entry["name"] == "data":
            if entry["status"] != "short-bad-blocks-unverified":
                raise FlashError("Unexpected data backup condition")
            if entry["expected_bytes"] - entry["actual_bytes"] != 262144:
                raise FlashError("Unexpected data partition shortage")
            if entry["sha256"].upper() != "0C263474C86C5337BC5E7AB764D0CA770DB4353A7FC941BA78B68FC825AE716E":
                raise FlashError("Data checksum differs from independent read")
        elif entry["status"] != "ok":
            raise FlashError(f"Saved {entry['name']} incomplete")
    meta = json.loads(rawmeta.read_text(encoding="utf-8"))
    if meta["bytes"] != 276824064 or rawfile.stat().st_size != 276824064:
        raise FlashError("Physical RAW NAND backup has wrong size")
    if sha256(rawfile) != meta["sha256"].upper():
        raise FlashError("Physical RAW NAND backup SHA256 changed")

    with IMAGE.open("rb") as reader:
        hdr = reader.read(64)
    if len(hdr) != 64 or hdr[56:60] != b"ARM\x64" or struct.unpack("<Q", hdr[8:16])[0] == 0:
        raise FlashError("Invalid adapted ARM64 kernel header")
    with DTB.open("rb") as reader:
        hdr = reader.read(40)
    if hdr[:4] != bytes.fromhex("d00dfeed") or not 40 <= struct.unpack(">I", hdr[4:8])[0] <= DTB.stat().st_size:
        raise FlashError("Invalid DTB header")
    with UBI.open("rb") as reader:
        if reader.read(4) != b"UBI#":
            raise FlashError("Invalid UBI header")
    k, d, u = IMAGE.stat().st_size, DTB.stat().st_size, UBI.stat().st_size
    if not (0 < k <= DTB_OFF - KERNEL_OFF and 0 < d <= UBI_OFF - DTB_OFF and 0 < u <= FLASH_END - UBI_OFF):
        raise FlashError("Firmware image exceeds assigned NAND slot")
    if any(x % ERASE_BLOCK for x in (KERNEL_OFF, DTB_OFF, UBI_OFF, FLASH_END)):
        raise FlashError("Unaligned NAND layout")
    if shutil.disk_usage(DIR).free < 100 * 1024 * 1024:
        raise FlashError("Insufficient scratch disk space")
    return {
        "kernel_bytes": k, "dtb_bytes": d, "ubi_bytes": u,
        "erase_from": hex(KERNEL_OFF),
        "erase_bytes": FLASH_END - KERNEL_OFF,
        "protected_vendor_end": hex(KERNEL_OFF),
        "bootdelay_seconds": BOOTDELAY,
        "kernel_sha256": sha256(IMAGE), "dtb_sha256": sha256(DTB), "ubi_sha256": sha256(UBI),
        "backup_warning": "stock data 256KiB short, repeated match; RAW NAND first chunk differs by 2 bits",
    }


def vendor(*arguments: str, timeout: int = 180) -> tuple[str, int]:
    proc = subprocess.run([str(UPDATE), *map(str, arguments)], capture_output=True,
                          stdin=subprocess.DEVNULL, timeout=timeout, check=False)
    output = (proc.stdout + b"\n" + proc.stderr).decode("utf-8", errors="replace")
    if "err:" in output.lower() or "[info]failed" in output.lower():
        raise FlashError(f"Vendor command failed: {arguments[0]} {output[-750:]}")
    return output, proc.returncode


def bulk(command: str) -> None:
    payload = "echo; " + command
    if len(payload.encode("ascii")) > 63:
        raise FlashError(f"Bulk command exceeds 63-byte limit: {payload}")
    output, code = vendor("bulkcmd", payload, timeout=90)
    if "bulkinreply success" not in output.lower():
        raise FlashError(f"No USB bulk success: {output[-400:]}")


def probe_identity() -> None:
    output, code = vendor("identify", "7", timeout=15)
    if "this firmware version is 0-7-0-16-0-0-0" not in output.lower():
        raise FlashError("Amlogic bootloader unavailable or its identity has changed")


def ram_write(file: Path, address: int) -> None:
    output, code = vendor("mwrite", str(file), "mem", hex(address), "normal", timeout=200)
    if "mwrite success" not in output.lower():
        raise FlashError(f"USB RAM write failed: {output[-350:]}")


def ram_read(address: int, length: int, path: Path) -> bytes:
    if path.exists():
        raise FlashError(f"Refusing to overwrite readback: {path}")
    output, code = vendor("mread", "mem", hex(address), "normal", hex(length), str(path), timeout=180)
    if "bulkinreply success" not in output.lower() or not path.is_file():
        raise FlashError(f"USB RAM read failed: {output[-400:]}")
    result = path.read_bytes()
    if len(result) != length:
        raise FlashError(f"Expected {length} RAM bytes; got {len(result)}")
    return result


def ram_proof(scratch: Path) -> None:
    sample = bytes(range(256)) * 16
    inp = scratch / "ram_test.bin"
    out = scratch / "ram_result.bin"
    inp.write_bytes(sample)
    ram_write(inp, 0x02040000)
    if ram_read(0x02040000, len(sample), out) != sample:
        raise FlashError("RAM round-trip mismatch")
    note("ram_roundtrip_verified", bytes=len(sample))


def read_environment(scratch: Path, basename: str) -> str:
    bulk("mw.b 0x02000000 0 0x10000")
    bulk("env export -t 0x02000000")
    contents = ram_read(ENV_RAM, ENV_SIZE, scratch / basename)
    text = contents.split(b"\0", 1)[0].decode("utf-8", errors="replace")
    if not re.search(r"(?m)^bootcmd=", text):
        raise FlashError("Exported boot environment missing bootcmd")
    return text


def env_expected(ksize: int, dsize: int) -> dict[str, str]:
    return {
        "ba": "ubi.mtd=ubi root=ubi0:rootfs rootfstype=ubifs rootwait rw "
              "console=ttyAML0,115200n8 console=ttyGS0,115200 loglevel=8",
        "ka": "setenv bootargs $" + "{ba}",
        "kb": f"nand read {hex(DTB_RAM)} {hex(DTB_OFF)} {hex(aligned(dsize, ERASE_BLOCK))}",
        "kc": f"nand read {hex(KERNEL_RAM)} {hex(KERNEL_OFF)} {hex(aligned(ksize, ERASE_BLOCK))}",
        "kd": f"booti {hex(KERNEL_RAM)} - {hex(DTB_RAM)}",
        "bootcmd": "run ka kb kc kd",
        "bootdelay": str(BOOTDELAY),
    }


def set_long_environment(key: str, value: str) -> None:
    acc = ""
    prefix = f"setenv {key} "
    for word in value.split():
        candidate = (acc + " " + word).strip()
        if len(("echo; " + prefix + candidate).encode("ascii")) <= 63:
            acc = candidate
            continue
        if not acc:
            raise FlashError(f"Variable token exceeds bulkcmd capacity: {word}")
        bulk(prefix + acc)
        prefix = f"setenv {key} $" + "{" + key + "} "
        acc = word
        if len(("echo; " + prefix + acc).encode("ascii")) > 63:
            raise FlashError(f"Variable token exceeds continuation capacity: {word}")
    if acc:
        bulk(prefix + acc)


def flash_image(file: Path, start: int, limit: int, ram: int,
                name: str, scratch: Path) -> None:
    total, pos = file.stat().st_size, 0
    with file.open("rb") as src:
        while pos < total:
            chunk = src.read(CHUNK)
            padded = chunk + bytes(aligned(len(chunk), PAGE) - len(chunk))
            address = start + pos
            if address < KERNEL_OFF or address + len(padded) > limit:
                raise FlashError(f"{name} NAND address outside permitted slot: {hex(address)}")
            outgoing = scratch / "chunk_out.bin"
            incoming = scratch / "chunk_in.bin"
            incoming.unlink(missing_ok=True)
            outgoing.write_bytes(padded)
            ram_write(outgoing, ram)
            bulk(f"nand write {hex(ram)} {hex(address)} {hex(len(padded))}")
            bulk(f"nand read {hex(ram)} {hex(address)} {hex(len(padded))}")
            readback = ram_read(ram, len(padded), incoming)
            if readback != padded:
                first = next((i for i, pair in enumerate(zip(readback, padded)) if pair[0] != pair[1]), None)
                raise FlashError(f"NAND verify mismatch {name} at {hex(address)} + {first}")
            outgoing.unlink()
            incoming.unlink()
            pos += len(chunk)
            note("nand_chunk_verified", component=name, address=hex(address),
                 bytes=len(padded), progress=f"{pos}/{total}")


def program() -> None:
    info = preflight()
    note("all_backup_and_image_checks_passed", **info)
    probe_identity()
    note("target_loader_identified")
    with TemporaryDirectory(prefix="capsula_flash_") as temp:
        scratch = Path(temp)
        ram_proof(scratch)
        previous = read_environment(scratch, "before.bin")
        (BACKUP / "uboot_env_before_flash.txt").write_text(previous, encoding="utf-8")
        note("original_uboot_env_preserved")
        # All preceding operations are non-destructive.
        note("NAND_ERASE_BEGIN", start=hex(KERNEL_OFF), end=hex(FLASH_END))
        bulk(f"nand erase {hex(KERNEL_OFF)} {hex(FLASH_END - KERNEL_OFF)}")
        note("NAND_ERASE_COMMANDED")
        flash_image(IMAGE, KERNEL_OFF, DTB_OFF, KERNEL_RAM, "kernel", scratch)
        flash_image(DTB, DTB_OFF, UBI_OFF, DTB_RAM, "dtb", scratch)
        flash_image(UBI, UBI_OFF, FLASH_END, KERNEL_RAM, "ubi", scratch)
        note("all_flash_regions_verified")
        settings = env_expected(IMAGE.stat().st_size, DTB.stat().st_size)
        for key in ("ka", "kb", "kc", "kd"):
            bulk(f"setenv {key} '{settings[key]}'")
        bulk(f"setenv bootcmd '{settings['bootcmd']}'")
        bulk(f"setenv bootdelay {BOOTDELAY}")
        set_long_environment("ba", settings["ba"])
        note("boot_variables_issued")
        bulk("saveenv")
        note("saveenv_issued")
        actual = read_environment(scratch, "after.bin")
        (BACKUP / "uboot_env_after_flash.txt").write_text(actual, encoding="utf-8")
        mismatched = [key for key, value in settings.items()
                      if not re.search(r"(?m)^" + re.escape(key + "=" + value) + r"\r?$", actual)]
        if mismatched:
            raise FlashError(f"Boot environment verification failed: {mismatched}")
        note("bootenv_verified", bootdelay=BOOTDELAY)


def main() -> int:
    parser = argparse.ArgumentParser(description="Native Windows Alpine NAND flasher for VK Mini A113X")
    parser.add_argument("--plan", action="store_true", help="Read-only image & recovery checks")
    parser.add_argument("--flash", action="store_true", help="ERASE NAND range and install Alpine Linux")
    parser.add_argument("--reboot", action="store_true", help="Reset board after complete verification")
    args = parser.parse_args()
    if args.plan == args.flash or (args.reboot and not args.flash):
        parser.error("Choose exactly one of --plan/--flash, and --reboot requires --flash")
    try:
        if args.plan:
            print(json.dumps(preflight(), ensure_ascii=False, indent=2), flush=True)
            print("PREFLIGHT_OK READ_ONLY", flush=True)
            return 0
        program()
        if args.reboot:
            note("board_reset_requested")
            try:
                bulk("reset")
            except (FlashError, subprocess.TimeoutExpired) as exc:
                print("USB reset can disconnect the transport; checking Linux boot is required.", flush=True)
            print("RESET_ISSUED; verify Alpine Linux USB gadget/SSH", flush=True)
        return 0
    except (FlashError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        note("FLASH_ABORTED", reason=str(exc))
        print(f"FLASH_ERROR: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
