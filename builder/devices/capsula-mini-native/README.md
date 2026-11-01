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

## Board-specific DTS and defconfig names

The pinned upstream A113X kernel still contains its historical
`meson-axg-s420-marusia-mini.dts` and `marusia_mini_defconfig` filenames.
The Builder applies a small, source-controlled kernel patch that **renames
only the files and Makefile target** to `meson-axg-capsula-mini.dts` and
`capsula_mini_defconfig`. The Device Tree properties remain byte-for-byte
unchanged, including `model = "VK Capsula Mini (Amlogic A113X)"` and
`compatible = "vk,capsula-mini", "amlogic,a113d", "amlogic,meson-axg"`.

`meson`/`axg` identify the Amlogic Linux SoC family and correctly remain in
the source filenames; `s420` comes from an upstream reference board and is
not part of our Capsula Mini board name. The final release still exposes
`board.dtb` to the image/boot contract. The patch is applied after verifying
the pinned upstream archive and its resulting source tree is attested.
