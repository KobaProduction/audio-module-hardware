"""Read-only Linux identity probe for selected HAL capabilities.

No device files are opened for input capture or written to. Unknown is the
correct state when no validated endpoint match is available.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _names_at(root: Path, pattern: str) -> list[str]:
    if not root.is_dir():
        return []
    result: list[str] = []
    for name_file in root.glob(pattern):
        try:
            if name_file.is_file():
                value = name_file.read_text(encoding="utf-8", errors="replace").strip()
                result.append(value)
        except OSError:
            continue
    return result


def _status(item: dict, sys_root: Path) -> dict:
    kind = item["kind"]
    match = item["properties"].get("linux_match", {})
    if kind == "input.keys" and match.get("name_equals"):
        names = _names_at(sys_root / "class/input", "input*/name")
        if match["name_equals"] in names:
            return {"state": "available", "evidence": "linux-input-name"}
    elif kind.startswith("sensor.") and match.get("name_equals"):
        names = _names_at(sys_root / "bus/iio/devices", "iio:device*/name")
        if match["name_equals"] in names:
            return {"state": "available", "evidence": "linux-iio-name"}
    # Presence of a soundcard or /sys/class/leds is NOT proof that any
    # particular speaker/jack/ring LED is controllable.
    return {"state": "unknown", "evidence": "runtime-adapter-not-validated"}


def inspect(compiled: dict[str, Any], sys_root: Path = Path("/sys")) -> dict:
    if (compiled.get("schema") != "koba.audio-module.capabilities"
            or compiled.get("version") != 1
            or compiled.get("runtime_verified") is not False):
        raise ValueError("Unsupported or misleading HAL descriptor")
    result: list[dict] = []
    for cap in compiled["capabilities"]:
        entry = _status(cap, sys_root)
        result.append({"id": cap["id"], **entry})
    return {
        "schema": "koba.audio-module.capability-status",
        "version": 1,
        "device": compiled["device"],
        "scope": "read-only-linux-identity-probe",
        "capabilities": result,
        "all_hardware_verified": False,
    }
