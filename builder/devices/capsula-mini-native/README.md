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
- future board-specific clock display, touch, light and ring LED clients

The author's shell helpers clockdisp, lightmon and touch-keys have only
been inspected, not reimplemented here. No closed binary ringled source
has been found. A future SPDIF modification is a separate variant profile,
not an incompatible modification of this native profile.

See docs/AUTHOR_SOURCE_MAPPING.md.


## Candidate immutable root + user overlay

storage.json is an uninstalled capacity-checked proposal: rootfs (UBIFS
read-only), rootfs_data (UBIFS writable OverlayFS), identity (physical protected MTD before kernel), with rootfs_data autoresized to all remaining UBI space. The currently running
Capsula has only one writable 200 MiB rootfs and no dedicated overlay.
Do not treat the candidate as a tested production partition map.
