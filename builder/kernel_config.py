"""Target-driven optional kernel driver selection.

Keeps SoC-specific Kconfig symbol knowledge in kernel/platforms and
consumer-device selection under builder/devices. The base defconfig still
owns all required platform boot/storage/audio-core symbols.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

from hal.manifest import compile_manifest

ROOT = Path(__file__).resolve().parents[1]
CONFIG_NAME = re.compile(r"^CONFIG_[A-Z0-9_]+$")


class KernelConfigurationError(ValueError):
    pass


def desired_symbols(profile: dict) -> dict[str, str]:
    platform = json.loads(
        (ROOT / "kernel/platforms" / (profile["soc"] + ".json")).read_text()
    )
    if platform.get("schema") != 1 or platform.get("soc") != profile["soc"]:
        raise KernelConfigurationError("SoC manifest invalid")
    features = platform["kernel"].get("config_features", {})
    active = {c["id"] for c in compile_manifest(profile)["capabilities"]}
    symbols: dict[str, str] = {}
    for name, entry in features.items():
        if name != entry.get("capability"):
            raise KernelConfigurationError("Feature name/capability mismatch")
        enabled = entry["capability"] in active
        for symbol, value in entry["symbols"].items():
            if not CONFIG_NAME.fullmatch(symbol):
                raise KernelConfigurationError("Invalid SoC driver Kconfig symbol")
            if isinstance(value, dict):
                # Kconfig string-valued firmware inclusion; never shell eval.
                if set(value) != {"enabled", "disabled"} or any(
                    not isinstance(v, str) or not re.fullmatch(r'"[a-zA-Z0-9_.,/-]*"', v)
                    for v in value.values()
                ):
                    raise KernelConfigurationError("Invalid Kconfig string choice")
                setting = value["enabled"] if enabled else value["disabled"]
            else:
                if value not in ("y", "m"):
                    raise KernelConfigurationError("Invalid SoC driver Kconfig value")
                setting = value if enabled else "n"
            if symbol in symbols and symbols[symbol] != setting:
                raise KernelConfigurationError("Conflicting Kconfig symbol")
            symbols[symbol] = setting
    return symbols


def write_config_overlay(config_path: Path, desired: dict[str, str]) -> None:
    """Modify a built .config, not original upstream defconfig.

    olddefconfig must be run immediately afterwards and the resulting state
    rechecked. Disabling a feature is NOT equivalent to removing its dependency.
    """
    source = config_path.read_text(encoding="utf-8")
    lines = source.splitlines()
    seen: set[str] = set()
    out = []
    for line in lines:
        match = re.fullmatch(r"(CONFIG_[A-Z0-9_]+)=.*", line)
        off = re.fullmatch(r"# (CONFIG_[A-Z0-9_]+) is not set", line)
        symbol = match.group(1) if match else off.group(1) if off else None
        if symbol and symbol in desired:
            if symbol in seen:
                raise KernelConfigurationError("Duplicate config symbol")
            out.append(f"{symbol}={desired[symbol]}" if desired[symbol] != "n"
                       else f"# {symbol} is not set")
            seen.add(symbol)
        else:
            out.append(line)
    for symbol in sorted(set(desired) - seen):
        value = desired[symbol]
        out.append(f"{symbol}={value}" if value != "n" else f"# {symbol} is not set")
    config_path.write_text("\n".join(out) + "\n", encoding="utf-8")


def assert_options_match(config_path: Path, expected: dict[str, str]) -> None:
    actual: dict[str, str] = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r'(CONFIG_[A-Z0-9_]+)=(y|m|"[a-zA-Z0-9_.,/-]*")', line)
        off = re.fullmatch(r"# (CONFIG_[A-Z0-9_]+) is not set", line)
        if match:
            actual[match.group(1)] = match.group(2)
        elif off:
            actual[off.group(1)] = "n"
    for symbol, value in expected.items():
        if actual.get(symbol) != value:
            raise KernelConfigurationError(
                f"Resolved Kconfig violates selected feature: {symbol} "
                f"(expected {value}, got {actual.get(symbol)})"
            )
