# Audio Module hardware architecture

## Scope and ownership

This repository is the initial integrated hardware delivery system, not
a VK-specific firmware fork. The shared main branch owns reusable components;
concrete device profiles are owned exclusively by builder/devices. A release
is selected by builder device ID, not by changing to
a permanently divergent device branch.

| Component | Responsibility | Future extraction |
| --- | --- | --- |
| kernel/ | SoC source pins, kernel support, patches, DT | separate kernel repository |
| uboot/ | Boot chain and validated bootloader builds | separate U-Boot repository |
| firmware/ | Alpine rootfs and UBI integration | separate firmware repository |
| builder/ | Resolve device and assemble images | separate builder repository |
| builder/devices/ | Board models, variants and minimal overlays | builder device profiles |
| tools/ | USB transport, backup and recovery | separate utilities if needed |

The current GitHub layout has **two** Audio Module repositories: Hardware and
[Application](https://github.com/KobaProduction/audio-module-application).
Kernel/U-Boot/Firmware/Builder/Tools stay *within Hardware* for now; an extra
Builder or Firmware repository is not planned. See the
[repository ownership and handoff map](REPOSITORIES.md).

Application exists as a separate repository but is not implemented; the
first device image must boot without it. Centralized voice agents and
home automation remain outside this hardware repository.

## Target model

1. SoC determines CPU architecture, baseline support, toolchain and boot chain.
   Initial platform: Amlogic A113X.
2. The Builder device profile determines NAND geometry, wiring, DTS and modules.
   Initial board: Capsula Mini.
3. Variant captures modifications (future SPDIF pinmux, other LEDs, etc.)
   without duplicating kernel or Alpine sources.
4. Builder consumes SoC source pins, builds kernel/modules, configures rootfs,
   assembles UBIFS/UBI and emits checksummed artifacts.

A SPDIF variant must not be declared supported until its DTS/DTBO and
hardware interactions are validated. The initial only profile is native.

## Safety and recovery

The first Capsula Mini target retains factory U-Boot, TPL and reserved
NAND areas. Source-built replacement and recovery are not yet validated.
The NAND region below 0x01200000 remains protected.

UBI geometry is measured from the physical unit: min I/O 2048 bytes,
PEB 131072 bytes and LEB 126976 bytes, with two bad blocks currently
reported. Never apply these values to another board without measurement.

Firmware output is NOT automatically flash-approved. Hardware acceptance
requires kernel/DT/module validation, boot test, audio/USB, persistence,
and a proven recovery path. Existing private factory backups stay offline.

## Upstream and source provenance

Original Capsula Mini board enablement:
https://github.com/comp18man/vk-capsula-mini-a113x-linux
The source commit is pinned in the target manifest. The Linux kernel is
GPL-2.0-only plus separately licensed components. We use source and
configuration, not the author's opaque prebuilt full firmware image.
Third-party binary Wi-Fi and Bluetooth firmware require provenance and
redistribution review. Alpine components retain upstream licenses.

Do not consume moving Git branch HEAD in a release. New source commits
must pass compatibility and hardware acceptance.

## Future OpenIPC-style split

As devices, contributors and independent release cycles increase, extract
kernel, U-Boot, firmware, builder and optional tools into separate repos.
Keep interfaces stable and dependencies pinned first so the split is
mechanical. Builder device profiles remain structured data rather than long-lived
branches, so generic fixes apply to all supported speakers.

Reference: https://github.com/OpenIPC/builder

## Validation boundary

The source-based firmware recipe is a new engineering implementation.
It is NOT yet a hardware-tested replacement for the author's current
working Alpine 3.24.1 image.

## OpenIPC boundary verified

The real OpenIPC Builder stores device definitions in its own devices/
subtree, and overlays a common firmware repository during assembly. We
follow the same ownership inside this initially combined repository:
firmware and kernel components never reference concrete consumer models;
the Builder alone resolves a selected device and applies its differences.

Before adding another device, reuse the same SoC platform pin when possible.
Do not copy kernel source commits or Alpine rootfs recipes between device
profiles. A future repository split can take builder/ (including devices/)
without migrating the hardware profiles out of firmware internals.

## Firmware optionality contract

Firmware owns a manifest of reusable Alpine components and services
(firmware/alpine/components.json). Builder device profiles select
components and carry only actual board overrides. Missing components
are not installed or enabled. Firmware must never hard-code consumer
model GPIO, display interfaces, gadget MAC addresses or NAND offsets.

Original author source classification is documented in
docs/AUTHOR_SOURCE_MAPPING.md; avoid importing binary executables or
private factory backups into source Git.

## HAL, diagnostics, updates: stable responsibility boundaries

- kernel/platforms records SoC source and optional Linux Kconfig driver
  features. Missing HAL capabilities must disable corresponding optional
  drivers, not merely remove their user-space wrappers.
- firmware/alpine supplies reusable packages and OpenRC services and stages
  the HAL declaration. No Python runtime is added by HAL compilation.
- builder/devices selects each hardware function explicitly, describes
  true device wiring, and chooses packages, kernel driver modules and blobs.
- hal/ is the shared language-neutral descriptor definition and build-host
  validator. Runtime Linux providers are not yet implemented.
- tools/diagnostics are optional consumers. The original ringled binary
  must not be required; it may only be used as private behavior evidence.
- firmware/updates contains a signed *offline compatibility checker*.
  Update delivery/application/rollback are separate privileged future
  services and remain disabled until physical recovery has been proven.

See docs/HAL_CONTRACT.md and docs/UPDATES.md for explicit acceptance gates.


## Persistence across system update vs clean install

See docs/PERSISTENCE.md. Current Capsula Mini uses one 200 MiB
writable UBI rootfs volume with zero available LEBs. Protecting the
18 MiB factory boot chain does NOT protect SSH identity, Wi-Fi pairing
or user config held inside rootfs. A device profile declares identity,
user, system and factory data ownership. Firmware/updates/persistence.py
proposes update/reset modes but blocks all write paths until verified
off-device backup/restore and hardware recovery exist.

Capsula Mini Ring LED is not a declared/planned device capability.


## Future NAND storage layer (design-only, no flash changes)

A device storage.json under Builder describes a prospective read-only
UBIFS system root and persistent UBIFS rootfs_data. Firmware owns the
generic OverlayFS/early-boot contract. Device-specific volume limits,
retention and identity-volume policy remain Builder data.

Builder/storage.py is a read-only capacity validator; the existing
single writable rootfs.ubi image is still the only build target.
SquashFS-on-ubiblock is NOT the current Capsula boot layout.
See docs/STORAGE_LAYOUT.md and firmware/storage/README.md.

## External architecture references (not OS migration)

OpenWrt is used only as a reference for structuring SoC support,
per-device profiles, optional firmware components, deterministic image
composition and safe update boundaries. The platform continues building
Linux/Alpine and retains its existing U-Boot/NAND contract; no OpenWrt
port, feeds, ImageBuilder or userspace migration is planned.
See docs/ARCHITECTURE_REFERENCES.md for the explicit ownership mapping.
