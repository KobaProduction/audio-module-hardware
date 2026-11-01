# Capsula Mini native device profile

This is the only consumer-device-specific ownership boundary.

The Amlogic A113X kernel source/revision is owned by kernel/platforms,
and generic Wi-Fi/SSH/USB/Bluetooth/ALSA components are owned by Firmware.
This device selects only their needed sets and provides:
- defconfig and DTS reference to the upstream Linux kernel tree
- NAND partition geometry, UBI/UBIFS and preserved factory U-Boot policy
- per-board USB gadget identity, static USB network addresses and hostname
- W1 Wi-Fi SAE workaround until the kernel driver issue is resolved
- optional Alpine component selection via profile.json
- future board-specific clock display, touch and light clients

The author's shell helpers clockdisp, lightmon and touch-keys have only
been inspected, not reimplemented here. No closed binary ringled source
has been found. A future SPDIF modification is a separate variant profile,
not an incompatible modification of this native profile.

See docs/AUTHOR_SOURCE_MAPPING.md.


## Candidate immutable root + user overlay

storage.json is an uninstalled capacity-checked proposal: rootfs (UBIFS
read-only), rootfs_data (UBIFS writable OverlayFS), identity (existing protected U-Boot Environment in reserved NAND), with rootfs_data autoresized to all remaining UBI space. The currently running
Capsula has only one writable 200 MiB rootfs and no dedicated overlay.
Do not treat the candidate as a tested production partition map.

## Original kernel Device Tree name

The pinned upstream A113X repository calls its source DTS
`meson-axg-s420-marusia-mini.dts` and its DTB accordingly. That historical
*filename* is not our public device identity: the DTS itself declares
`model = "VK Capsula Mini (Amlogic A113X)"` and
`compatible = "vk,capsula-mini", "amlogic,a113d", "amlogic,meson-axg"`.
Our Builder selects that exact upstream DTB without rewriting kernel sources
and emits the image artifact as `board.dtb`. A future reviewed in-tree
DTS rename can use `meson-axg-capsula-mini.dts` (without altering the
actual U-Boot-compatible DT layout), but renaming the existing upstream
file or `compatible` now would need additional hardware acceptance.
