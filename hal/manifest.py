"""Compile a device capability declaration without pretending it was probed.

This module is for the BUILD HOST. The application may consume its JSON
output as hints; the runtime HAL must independently enumerate actual Linux
devices. No Python daemon or model-specific runtime dependency is installed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "koba.audio-module.capabilities"
VERSION = 1
CAPABILITY_ID = re.compile(r"^[a-z][a-z0-9]*(?:[.-][a-z0-9]+)+$")
KNOWN_KINDS = frozenset({
    "audio.capture", "audio.playback", "audio.connector",
    "display.segment", "display.pixel", "display.matrix",
    "input.keys", "input.rotary", "sensor.ambient", "sensor.proximity",
    "sensor.motion", "light.single", "light.rgb", "light.addressable",
    "network.wifi", "network.bluetooth", "power.supply", "power.battery",
})
LINUX_PROVIDERS = frozenset({
    "alsa", "evdev", "iio", "led-class", "line-display", "drm",
    "gpio", "v4l2", "iwd", "bluez", "hwmon", "power-supply",
})
ALLOWED_ACTIONS = frozenset({
    "read", "events", "stream", "volume", "mute", "brightness",
    "text", "pixels", "color", "pattern", "scan", "connect",
})
# A provider cannot claim operations it has no semantic meaning for.
KIND_PROVIDER = {
    "audio.capture": {"alsa"}, "audio.playback": {"alsa"},
    "audio.connector": {"alsa", "evdev"},
    "display.segment": {"line-display", "led-class"},
    "display.pixel": {"drm"}, "display.matrix": {"drm", "led-class"},
    "input.keys": {"evdev", "gpio"}, "input.rotary": {"evdev"},
    "sensor.ambient": {"iio", "hwmon"},
    "sensor.proximity": {"iio", "evdev"},
    "sensor.motion": {"iio", "evdev"},
    "light.single": {"led-class", "gpio"},
    "light.rgb": {"led-class"},
    "light.addressable": {"led-class"},
    "network.wifi": {"iwd"}, "network.bluetooth": {"bluez"},
    "power.supply": {"power-supply", "hwmon"},
    "power.battery": {"power-supply", "hwmon"},
}
KIND_ACTIONS = {
    "audio.capture": {"stream", "read"},
    "audio.playback": {"stream", "volume", "mute"},
    "audio.connector": {"read", "events"},
    "display.segment": {"text", "brightness"},
    "display.pixel": {"pixels", "brightness"},
    "display.matrix": {"pixels", "brightness"},
    "input.keys": {"events"}, "input.rotary": {"events"},
    "sensor.ambient": {"read", "events"},
    "sensor.proximity": {"read", "events"},
    "sensor.motion": {"read", "events"},
    "light.single": {"brightness", "pattern"},
    "light.rgb": {"brightness", "color", "pattern"},
    "light.addressable": {"brightness", "color", "pattern"},
    "network.wifi": {"read", "events", "scan", "connect"},
    "network.bluetooth": {"read", "events", "scan", "connect"},
    "power.supply": {"read", "events"},
    "power.battery": {"read", "events"},
}

REQUIRED_KEYS = frozenset({
    "id", "kind", "component", "support", "provider", "actions", "properties",
})


class CapabilityError(ValueError):
    """A board has an invalid or unsupported capability declaration."""


def _positive_or_unknown(value: Any, name: str, *, allow_zero: bool = False) -> None:
    if value is None:  # explicit unknown != zero and != absent
        return
    if type(value) is not int or value < (0 if allow_zero else 1):
        raise CapabilityError(f"{name} must be a positive integer or null")


def validate_declarations(
    data: dict[str, Any], target_id: str, known_components: set[str],
) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or data.get("schema") != VERSION or data.get("device") != target_id:
        raise CapabilityError("Device capability schema/identity mismatch")
    records = data.get("capabilities")
    if not isinstance(records, list):
        raise CapabilityError("capabilities must be a list")
    unique: set[str] = set()
    for item in records:
        if not isinstance(item, dict) or not REQUIRED_KEYS <= item.keys():
            raise CapabilityError("Missing capability fields")
        name = item["id"]
        if not isinstance(name, str) or not CAPABILITY_ID.fullmatch(name):
            raise CapabilityError("Invalid stable capability ID")
        if name in unique:
            raise CapabilityError("Duplicate capability ID: " + name)
        unique.add(name)
        kind = item["kind"]
        if not isinstance(kind, str) or kind not in KNOWN_KINDS:
            raise CapabilityError("Unsupported capability kind: " + str(kind))
        if not isinstance(item["component"], str) or item["component"] not in known_components:
            raise CapabilityError("Unknown firmware component in capability")
        if item["support"] not in ("declared", "planned"):
            raise CapabilityError("Invalid support level")
        provider = item["provider"]
        if not isinstance(provider, str):
            raise CapabilityError("Provider must be a string")
        if item["support"] == "declared" and provider not in LINUX_PROVIDERS:
            raise CapabilityError("Active hardware requires a Linux provider")
        if item["support"] == "declared" and provider not in KIND_PROVIDER[kind]:
            raise CapabilityError("Provider is incompatible with capability kind")
        if item["support"] == "planned" and provider not in LINUX_PROVIDERS | {"unresolved"}:
            raise CapabilityError("Invalid planned Linux provider")
        actions = item["actions"]
        if (not isinstance(actions, list)
                or any(not isinstance(a, str) for a in actions)
                or len(set(actions)) != len(actions)):
            raise CapabilityError("Duplicate/invalid capability action list")
        if not set(actions) <= ALLOWED_ACTIONS:
            raise CapabilityError("Unknown capability action")
        if not set(actions) <= KIND_ACTIONS[kind]:
            raise CapabilityError("Action is incompatible with capability kind")
        props = item["properties"]
        if not isinstance(props, dict):
            raise CapabilityError("properties must be an object")
        match = props.get("linux_match", {})
        if (not isinstance(match, dict)
                or any(k not in {"name_equals"} for k in match)
                or (match and (not isinstance(match.get("name_equals"), str)
                               or len(match["name_equals"]) > 128))):
            raise CapabilityError("Invalid Linux identity selector")
        if kind in ("audio.capture", "audio.playback"):
            for key in ("physical_microphones", "capture_channels",
                        "physical_speakers", "playback_channels"):
                if key in props:
                    _positive_or_unknown(props[key], key)
        if kind == "display.segment":
            _positive_or_unknown(props.get("digits"), "digits")
        if kind == "display.pixel":
            _positive_or_unknown(props.get("width"), "width")
            _positive_or_unknown(props.get("height"), "height")
        if kind == "input.keys":
            _positive_or_unknown(props.get("keys"), "keys")
    return records


def compile_manifest(
    profile: dict[str, Any],
    device_path: Path | None = None,
) -> dict[str, Any]:
    """Emit only selected *declared* features. Planned never claims availability.

    Missing firmware components do not turn on hidden peripherals; the Builder
    must explicitly select the component in the device profile.
    """
    selected = set(profile["firmware"]["components"])
    catalog = json.loads((ROOT / "firmware/alpine/components.json").read_text(encoding="utf-8"))
    known_components = set(catalog["components"])
    if not selected <= known_components:
        raise CapabilityError("Selected unknown firmware components")
    path = (device_path or ROOT / "builder/devices" / profile["id"]) / "capabilities.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    all_items = validate_declarations(raw, profile["id"], known_components)
    selected_ids = profile.get("hal", {}).get("enabled_capabilities")
    if not isinstance(selected_ids, list) or any(not isinstance(x, str) for x in selected_ids):
        raise CapabilityError("Builder must explicitly select HAL capabilities")
    if len(set(selected_ids)) != len(selected_ids):
        raise CapabilityError("Duplicate HAL selection")
    declared = {item["id"] for item in all_items if item["support"] == "declared"}
    if not set(selected_ids) <= declared:
        raise CapabilityError("Unknown or unimplemented HAL capability selected")
    enabled = sorted(
        (item for item in all_items
         if item["support"] == "declared"
         and item["id"] in selected_ids and item["component"] in selected),
        key=lambda item: item["id"],
    )
    return {
        "schema": SCHEMA,
        "version": VERSION,
        "origin": "builder-declared",
        "runtime_verified": False,
        "device": profile["id"],
        "soc": profile["soc"],
        "capabilities": enabled,
    }


def write_manifest(profile: dict[str, Any], rootfs: Path) -> Path:
    target = rootfs / "usr/share/audio-module/capabilities-v1.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(compile_manifest(profile), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return target
