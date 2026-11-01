# Koba Audio Module — Hardware

Source-based Linux/Alpine firmware assembly and hardware enablement for
the Koba Audio Module family. One repository for now; internals can
later be separated into OpenIPC-style kernel, U-Boot, firmware, builder
and flasher projects without changing target contracts.

**Current first target:** Capsula Mini native, Amlogic A113X.
**Application:** not implemented or bundled yet.

## Source layout

- kernel/ — pinned SoC Linux sources and a 246-path author driver/provenance catalog
- uboot/ — explicit bootloader policy (retain vendor on current board)
- firmware/alpine/ — common Alpine source pins, optional component packages/services, reusable OpenRC configuration
- builder/ — build engine; devices/ holds each physical model's profile and overlay
- tools/ — transport, flashing, backup and recovery contracts
- builder/build.py — source-based kernel/rootfs/UBI image build driver
- docs/ARCHITECTURE.md — boundaries, provenance and future repository split

Builder selects a device configuration from builder/devices; shared SoC inputs
come from kernel/platforms. No device definition lives at repository root.
A target is declared as data, not a long-running Git branch.
Common fixes flow to all devices. Source revisions are pinned; target
profiles contain the physical flash geometry and protected areas.

## Local build workflow (Linux host)

Prerequisites for the full build: Python 3.11+, git, make, an AArch64
cross compiler plus build dependencies of upstream Linux, and
mtd-utils (mkfs.ubifs / ubinize). The rootfs step must run as root
to preserve package UID/GID and file capabilities.

The builder downloads Alpine 3.24.1 minirootfs and host apk.static by
SHA256. Signed target packages are obtained from Alpine v3.24
repositories; package versions are NOT fully frozen yet.

Commands from the repository root:

    python3 -m builder.build plan --target capsula-mini-native
    python3 -m builder.build fetch-kernel --target capsula-mini-native
    python3 -m builder.build kernel --target capsula-mini-native
    sudo python3 -m builder.build rootfs --target capsula-mini-native --authorized-key-file /path/to/your.pub
    sudo python3 -m builder.build image --target capsula-mini-native

The rootfs stage is intentionally one-shot: it refuses to overwrite an
existing rootfs directory, which may contain an SSH provisioning key.
The user-supplied path is to a PUBLIC key only, never a private key.
Images stay under .work/capsula-mini-native/images/ and are untracked.

**No actual flash/erase/restore command is invoked by these build steps.**
The generated manifest is explicitly marked NOT_HARDWARE_VALIDATED.
Do not overwrite the current working firmware until recovery, audio,
USB gadget and rootfs functionality are tested on the physical board.

For source-only checks run:

    sh scripts/verify.sh

Enable pre-push hook on a new checkout:

    git config core.hooksPath .githooks

## Licensing and attribution

Original Capsula Mini kernel board-support and config is from
https://github.com/comp18man/vk-capsula-mini-a113x-linux and remains
a pinned external build dependency. Linux kernel source is GPL-2.0-only
with separately licensed components. Alpine packages, kernel modules,
closed vendor calibration data and Wi-Fi firmware retain their own terms.

No author's prebuilt kernel/UBI, proprietary Amlogic flasher, stock
backup, unique device credentials or user NAND dumps are committed.

## Status

Architecture and build recipe are initialized. Local tests verify source
pins, NAND boundaries, overlay resolution and image metadata. This is
not a production-ready or independently hardware-booted image.

See docs/ARCHITECTURE.md for future modularization and safety.

## Source ownership and attribution

The upstream kernel's A113X-specific patches, drivers, DTS, configs and
Wi-Fi source are tracked in kernel/provenance/comp18man-a113x-delta.json.
The entire kernel source is fetched by immutable revision rather than
copied into consumer device profiles.

The original vendor userspace diagnostics and helper binaries are still
being classified. Hardware-specific clock/display/LED/touch test wrappers
belong to Builder, generic Wi-Fi provisioning belongs to Firmware, generic
USB/NAND transport belongs to Tools. Unlicensed executables and personal
NAND backups are not redistributed.

For a file-by-file audit of the original author's kernel drivers,
userland helpers and unavailable binary sources, see
[Author source ownership](docs/AUTHOR_SOURCE_MAPPING.md).
