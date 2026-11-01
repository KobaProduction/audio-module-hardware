# OpenWrt-inspired rootfs/OverlayFS contract

Preserve the current factory physical NAND partition map, including
the protected bootloader/reserved/TPL/misc regions and their actual
U-Boot Environment, factory calibration and keys.

Within the final UBI MTD: use two logical volumes:
- immutable UBIFS rootfs, image-sized, lower /rom;
- persistent UBIFS rootfs_data, autoresize to remaining available UBI
  volume space, upper/work for the merged OverlayFS /.

U-Boot Environment and factory source are not a third data volume.
Expose identifiers through a future read-only restricted identity API.
The live redundant env copies have conflicting ethaddr values; never
write them or select an unverified MAC automatically.

OpenWrt sysupgrade normally saves selected config state, not
necessarily every overlay file; a larger system image may require
rebuilding the data volume. Rootfs Data consuming available UBI
capacity does not eliminate the need for verified external backup.
UBI reserves for NAND bad blocks remain mandatory.

No early-init migration, OverlayFS boot, full source image,
sysupgrade port or NAND write operation is approved yet. Keep
legacy Alpine rootfs active until full hardware acceptance.
