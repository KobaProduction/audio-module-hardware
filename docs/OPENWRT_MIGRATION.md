# OpenWrt build architecture: adoption and porting gates

## Decision

Adopt OpenWrt's SoC/target/package/image/upgrade boundaries without
claiming that Capsula Mini already runs OpenWrt or can boot its images.

The official OpenWrt source tree, target/linux, inspected 2026-11-01
has no amlogic or meson target. Third-party Amlogic builds for other
SoCs do not prove upstream A113X board support.

## OpenWrt concept to Audio Module owner

| OpenWrt | Audio Module Hardware |
| --- | --- |
| target/linux/<family>, kernel patches and DTS | kernel/platforms |
| target/linux/<family>/image, Device definitions | builder/devices and image recipes |
| feeds, package metadata, dependency resolution | firmware packages/providers |
| ImageBuilder PROFILE, PACKAGES, FILES, DISABLED_SERVICES | builder profile, components, overlays |
| immutable rootfs + rootfs_data/OverlayFS | firmware/storage, builder/storage |
| factory/ART/U-Boot environment MAC/calibration | uboot read-only provider, protected reserved MTD |
| sysupgrade/firstboot/config retention | firmware/updates with explicit preservation manifest |

ImageBuilder uses packages with explicit inclusion/exclusion and a
profile that selects device-specific kernel and drivers. This matches
our separation but does not prove full compatibility with our Alpine
rootfs or patches.

OpenWrt is a system including procd, UCI, ubus, netifd and a distro
package ecosystem, while Alpine currently uses OpenRC, iwd and apk.
Changing the operating system means porting those interfaces and
building a matching target/toolchain, not merely replacing a rootfs.

OpenWrt sysupgrade restores selected backed-up configs, not necessarily
the entire writable overlay. On NAND it may recreate rootfs_data to
fit larger firmware and requires RAM/external backup and recovery.
A rootfs_data volume that consumes remaining UBI capacity does not
eliminate the need for backups on future upgrades.

## Current evidence and boundaries

- Kernel: pinned source branch containing A113X peripheral drivers.
- Boot chain: protected vendor bootloader/TPL and factory reserved.
- CRC-valid U-Boot env found in reserved with serial and ethaddr keys;
  the two copies of ethaddr conflict. Active-copy selection is unknown.
- Rootfs: current working Alpine 3.24.1 on a single writable UBIFS root.
- Builder: source-based plans, selected packages, HAL, safe update
  metadata, prospective read-only rootfs/OverlayFS design.
- There is no official, built or tested OpenWrt Capsula Mini image.
  Do not use OpenWrt native sysupgrade against the existing Alpine image.

## Migration tasks

1. Preserve original private U-Boot environment and factory backup.
2. Select OpenWrt platform/target base and pin exact branch, toolchain,
   feeds, kernels and patches; port actual A113X/Capsula DTS and drivers.
3. Model board-specific image recipes and optional package dependencies.
4. Build an image separately and inspect kernel, DTB, rootfs and UBI
   artifacts without changing working factory boot chain.
5. Boot/verify on recoverable hardware, including audio, sensors, LEDs,
   network, power loss and fallback.
6. Implement safe NAND sysupgrade/firstboot for this verified target,
   with config backup/restore and protected factory data.
7. Compare actual OpenWrt runtime resource footprint and services
   with Alpine before deciding the permanent OS provider.

OpenWrt-inspired design is adopted now; an actual distro switch remains
unproven until a complete source build and physical acceptance.

## Sources

https://git.openwrt.org/openwrt/openwrt/tree/?path=target/linux
https://github.com/openwrt/openwrt/blob/main/include/image.mk
https://openwrt.org/docs/guide-user/additional-software/imagebuilder
https://openwrt.org/docs/techref/flash.layout
https://openwrt.org/docs/guide-user/installation/generic.sysupgrade
https://openwrt.org/docs/guide-developer/mac.address
