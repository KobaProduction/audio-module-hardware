"""Read-only CRC and identifier-consistency audit of backed-up U-Boot env.

Reports presence/consistency only. Never prints identifier values, keys,
calibration or U-Boot commands. Does not touch MTD unless explicitly
given a local readable file. No environment write path exists.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import zlib

DEFAULT_SLOT_SIZE = 65536
DEFAULT_STRIDE = 131072
KEYS = ("serial", "ethaddr")


class EnvironmentAuditError(ValueError):
    pass


def audit_environment(raw: bytes, *, slot_size: int = DEFAULT_SLOT_SIZE,
                      stride: int = DEFAULT_STRIDE) -> dict:
    if (slot_size != DEFAULT_SLOT_SIZE or stride != DEFAULT_STRIDE
            or len(raw) < slot_size or len(raw) > 16 * 1024 * 1024):
        raise EnvironmentAuditError("Unsupported env block size or input length")
    valid: list[tuple[int, dict[str, bytes]]] = []
    for offset in range(0, len(raw) - slot_size + 1, stride):
        block = raw[offset:offset + slot_size]
        if int.from_bytes(block[:4], "little") != zlib.crc32(block[4:]) & 0xffffffff:
            continue
        values: dict[str, bytes] = {}
        for entry in block[4:].split(b"\0"):
            if b"=" not in entry:
                continue
            key, value = entry.split(b"=", 1)
            if re.fullmatch(rb"[A-Za-z][A-Za-z0-9_.-]{1,47}", key):
                values[key.decode("ascii")] = value
        valid.append((offset, values))
    checks: dict[str, dict] = {}
    for key in KEYS:
        present = [v[key] for _, v in valid if key in v and v[key]]
        checks[key] = {
            "copies_with_nonempty_key": len(present),
            "distinct_copy_values_agree": bool(present) and len(set(present)) == 1,
            "authoritative_active_copy_proven": False,
        }
    return {
        "schema": 1,
        "scope": "offline-read-only-uboot-env",
        "crc_valid_block_count": len(valid),
        "crc_valid_offsets_bytes": [offset for offset, _ in valid],
        "identifier_checks": checks,
        "identifiers_exposed": False,
        "firmware_modifications": False,
        "note": "CRC does not establish which copy U-Boot currently selects",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit saved U-Boot environment without disclosing values")
    parser.add_argument("--file", type=Path, required=True,
                        help="Offline private reserved/env backup file")
    args = parser.parse_args()
    try:
        size = args.file.stat().st_size
        if size > 16 * 1024 * 1024:
            raise EnvironmentAuditError("Refusing unbounded source file")
        report = audit_environment(args.file.read_bytes())
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["crc_valid_block_count"] else 2
    except (EnvironmentAuditError, OSError) as error:
        print("UBOOT_ENV_AUDIT_FAILED:", error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
