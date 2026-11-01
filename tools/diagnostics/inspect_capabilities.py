#!/usr/bin/env python3
"""Host/development read-only HAL probe. NOT an on-device runtime package."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from hal.probe import inspect  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Read declared HAL and inspect limited Linux identities")
    ap.add_argument("--manifest", required=True, type=Path)
    ap.add_argument("--sys-root", type=Path, default=Path("/sys"))
    args = ap.parse_args()
    try:
        if args.manifest.stat().st_size > 65536:
            raise ValueError("HAL manifest too large")
        data = json.loads(args.manifest.read_text(encoding="utf-8"))
        print(json.dumps(inspect(data, args.sys_root), indent=2, sort_keys=True))
    except (OSError, ValueError, TypeError, KeyError) as e:
        print("HAL_INSPECT_FAILED:", e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
