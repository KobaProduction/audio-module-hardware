# Audio Module hardware abstraction — contract draft v1

## General rule

The hardware abstraction layer normalizes capabilities of different audio
modules. It does not replace Linux drivers, duplicate ALSA, or require
model-specific executable blobs. Reuse Linux APIs and expose a versioned,
typed semantic contract to Application and optional CLI diagnostics.

**A device profile is a declaration, not proof of operability.**
Builder outputs a static descriptor. Runtime validates selected functions
against actual devices and exposes states: available, unavailable, unknown,
error; optionally an error detail. No capability means absent, not an error.
Missing driver/runtime binding must not be advertised as available.

## Stable IDs and providers

IDs are semantic and stable per device (audio.capture.pdm,
audio.playback.speaker, audio.playback.jack, display.front,
input.touch, sensor.ambient). Applications must not assume Linux input
device index, ALSA card number, IIO index, GPIO number, or sysfs LED name.

| Area | Linux subsystem | Interface |
| --- | --- | --- |
| Microphones | ALSA PCM capture | Physical microphone count, capture channel count, sample rates/formats/gain as independent fields; null is unknown |
| Playback | ALSA PCM/mixer | Physical speaker count, PCM channels, logical speaker outputs and route availability |
| Wired audio | ALSA controls/jack | Headphone, line-out, line-in, AUX and S/PDIF are distinct; optional |
| Buttons | evdev/input | Capacitive, physical, rotary, GPIO-backed map to semantic events and key codes |
| Segment clocks | line-display/LED class | Character cells, colon, glyphs, brightness; not a framebuffer |
| Pixel displays | DRM/KMS or validated pixel backend | Width/height, format, rotation and pixel operations; optional |
| LEDs | LED class/GPIO/controller adapter | Mono, RGB, addressable and effects; never presume ringled support |
| Sensors | IIO/hwmon/evdev | Typed physical units, scale, sample interval; optional |
| Wi-Fi/Bluetooth | iwd/BlueZ D-Bus | Scan/connect/status, no secrets in target profile |
| Power | power_supply/hwmon | Supply/charging/voltage/battery; optional |

Runtime must discover persistent logical endpoints and handle hot-plug.
Only a reviewed board profile may map a logical function to a physical
controller or ALSA path.

## Build-time descriptor

A Builder device stores its capabilities.json beside its profile and overlay.
The HAL build-host compiler combines those declared capabilities with the
selected firmware.components to emit, into the image:

    /usr/share/audio-module/capabilities-v1.json

Fields:
- schema/version: contract and compatibility negotiation.
- device/soc: selected build identity.
- origin=builder-declared and runtime_verified=false: NOT a live probe.
- capabilities: declared entries whose required firmware component is
  selected. Planned functions are excluded.

No Bluetooth package => no Bluetooth HAL entry. No screen => no display
capability. No AUX => no AUX output capability.

Distinguish physical microphone counts from PCM capture channels, and
physical speakers from PCM playback channels. Unknown counts are null;
not zero, and not invented from an ALSA stereo PCM descriptor.

## Proposed runtime interaction (NOT implemented)

Versioned local HAL methods should eventually include:
- capabilities.list / capabilities.get with live status;
- device.read / device.set / device.subscribe with strict typed payloads
  and nonblocking event delivery for buttons, sensors and jack insertion;
- audio.enumerate / audio.route / audio.open_stream via ALSA or a proper
  audio engine (do not stream PCM via a JSON command socket);
- health.inspect / diagnostics.run, only on explicitly selected tools.

Do not implement arbitrary shell execution as a HAL operation.
Mutating GPIO/sysfs requires local permissions. The local transport,
whether native C ABI, Unix socket or D-Bus, must have its own version
and must never expose unauthenticated network write access.

## Test matrix

Build-host tests validate schema, compatibility, optional-feature pruning,
counts and planned features. Runtime providers and physical topology must
still be verified by hardware tests.

Future fixtures should cover:
- mono output + one physical mic + physical buttons, no display;
- segmented display + capacitive keys + multichannel microphone array;
- pixel display + AUX/S/PDIF and optional addressable LEDs.

Diagnostics under tools are clients of HAL, not custom GPIO drivers.
Unselected diagnostic tools must never be required for normal operation.

## Kconfig and source footprint

For supported SoCs, kernel/platforms/<soc>.json describes optional
driver Kconfig symbols. Builder selects known HAL functions explicitly
and a kernel .config override enables only mapped optional drivers.
The kernel build must resolve its Kconfig and reject incompatible
changes. Package and blob selection must also follow the same
capability set. This supports minimal device images; it is not yet
a verified size optimization on physical hardware.


## Ring LED is intentionally excluded from Capsula Mini

The Capsula Mini native Builder capabilities.json contains no ring LED
declaration, including no planned entry. A historical private diagnostic
binary is not installed, called or used as an HAL provider. Future
addressable-light support requires an independently verified source-based
driver/provider and explicit device-profile enablement.
