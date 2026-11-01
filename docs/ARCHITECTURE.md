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

Audio Module Application is a separate repo. It has not been implemented, so
the first device image must boot without it. Centralized voice agents and
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
