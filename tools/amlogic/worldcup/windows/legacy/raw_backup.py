"""Read-only full physical NAND backup, 2048+64 bytes/page, 131072 pages.

Based on the original author's flasher.sh full_raw_dump() routine.
Writes ONLY the local PC backup files; U-Boot NAND commands are read-only.
"""
if __name__ == "__main__":
    raise SystemExit("LEGACY REFERENCE DISABLED: requires profile-driven port and recovery validation.")

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
UPDATE = ROOT / "update.exe"
EXPECTED_UPDATE_SHA = "F1DE686CF4FF770EE9DF0ACC2721E6A8195C81B556CA8894C04EB3BAC7CB2CAA"
TARGET_DIR = ROOT / "backups" / "capsula-a113x" / "20261101-095750"
RAW_PAGE = 2048 + 64
RAW_PAGES_PER_CHUNK = 4096
MAIN_NAND_BYTES = 0x10000000
EXPECTED_TOTAL_BYTES = (MAIN_NAND_BYTES // 2048) * RAW_PAGE
CHUNK_BYTES = RAW_PAGE * RAW_PAGES_PER_CHUNK
CHUNK_COUNT = MAIN_NAND_BYTES // (2048 * RAW_PAGES_PER_CHUNK)
RAM_ADDR = 0x01080000


def run_update(*args: str, timeout: int = 60) -> tuple[str, int]:
    proc = subprocess.run(
        [str(UPDATE), *args],
        stdin=subprocess.DEVNULL, capture_output=True,
        timeout=timeout, check=False,
    )
    text = (proc.stdout + b"\n" + proc.stderr).decode("utf-8", errors="replace")
    return text, proc.returncode


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for buf in iter(lambda: src.read(1024 * 1024), b""):
            digest.update(buf)
    return digest.hexdigest().upper()


def main() -> int:
    if not UPDATE.is_file() or hash_file(UPDATE) != EXPECTED_UPDATE_SHA:
        raise RuntimeError("Unverified or missing Windows update.exe")
    if not TARGET_DIR.is_dir() or not (TARGET_DIR / "manifest.json").is_file():
        raise RuntimeError("Existing partition backup missing")
    if shutil.disk_usage(TARGET_DIR).free < EXPECTED_TOTAL_BYTES + 200 * 1024 * 1024:
        raise RuntimeError("Not enough free space for full RAW NAND/OOB image")
    ident, _ = run_update("identify", "7")
    if "firmware version" not in ident.lower() or "err:" in ident.lower():
        raise RuntimeError("Live WorldCup bootloader is not identified")
    print("WorldCup available. RAW physical NAND read-only dump commencing.", flush=True)

    final = TARGET_DIR / "nand-full.raw.bin"
    partial = TARGET_DIR / "nand-full.raw.partial"
    result = TARGET_DIR / "nand-full.raw.json"
    for file in (final, partial, result):
        if file.exists():
            raise RuntimeError(f"Will not overwrite existing data: {file}")

    # Use ASCII-only path for the old vendor program; final file lives on Desktop.
    scratch = Path(tempfile.gettempdir()) / "capsula_raw_chunk_current.bin"
    if scratch.exists():
        raise RuntimeError(f"Scratch path already exists: {scratch}")
    completed = 0
    started = datetime.now(timezone.utc).isoformat()
    try:
        with partial.open("wb") as target:
            for index in range(CHUNK_COUNT):
                address = index * RAW_PAGES_PER_CHUNK * 2048
                command = f"echo; nand read.raw {hex(RAM_ADDR)} {hex(address)} {hex(RAW_PAGES_PER_CHUNK)}"
                if len(command.encode("ascii")) > 63:
                    raise RuntimeError(f"Unsafe bulkcmd length at {index}")
                output, code = run_update("bulkcmd", command, timeout=45)
                if "bulkinreply success" not in output.lower() or "err:" in output.lower():
                    raise RuntimeError(f"RAW NAND read failed at index {index}: {output[-300:]}")
                output, code = run_update(
                    "mread", "mem", hex(RAM_ADDR), "normal",
                    hex(CHUNK_BYTES), str(scratch), timeout=100,
                )
                if not scratch.is_file() or scratch.stat().st_size != CHUNK_BYTES:
                    raise RuntimeError(
                        f"USB transfer failed at index {index}: "
                        f"bytes={scratch.stat().st_size if scratch.exists() else 0}, "
                        f"output={output[-300:]}"
                    )
                with scratch.open("rb") as src:
                    shutil.copyfileobj(src, target)
                scratch.unlink()
                completed += 1
                print(f"RAW_PROGRESS {completed}/{CHUNK_COUNT} [{completed*100//CHUNK_COUNT}%] offset={address:#x}", flush=True)
            target.flush()
            os.fsync(target.fileno())

        if partial.stat().st_size != EXPECTED_TOTAL_BYTES:
            raise RuntimeError(f"Unexpected final file size {partial.stat().st_size}")
        checksum = hash_file(partial)
        partial.replace(final)
        metadata = {
            "kind": "full-physical-nand-with-oob",
            "date_utc": started,
            "source": "VK Mini A113X read.raw via Windows Amlogic update.exe",
            "bytes": EXPECTED_TOTAL_BYTES,
            "page_data_bytes": 2048,
            "page_oob_bytes": 64,
            "pages": MAIN_NAND_BYTES // 2048,
            "chunks": CHUNK_COUNT,
            "sha256": checksum,
            "validation": "transfer length and local SHA256 only; not restore-tested",
        }
        result.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"RAW_BACKUP_SAVED {final}", flush=True)
        print(f"RAW_BACKUP_SHA256 {checksum}", flush=True)
        return 0
    except Exception as exc:
        print(f"RAW_BACKUP_INCOMPLETE chunks={completed}: {exc}", file=sys.stderr, flush=True)
        return 2
    finally:
        scratch.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
