# Generic filesystem composition and device-owned partitioning

Future Audio Module: protected boot chain -> identity MTD partition ->
kernel and DTB -> terminal UBI partition.

Inside UBI: immutable UBIFS rootfs (image-sized) and writable UBIFS
rootfs_data (autoresize to ALL remaining UBI-available volume capacity).
No artificial fixed trailing reserve. UBI still manages its necessary
bad-block and wear-levelling reserves.

Firmware owns the generic OverlayFS lower/upper contract. Builder owns
NAND offsets and UBI capacity policy. Identity is NOT a third UBI volume;
its physical format, read-only access/provider and provisioning must be
validated separately, as it lies before the kernel MTD partition.

A safe early init must expose the rootfs lower at /rom, data UBIFS at
/overlay, merged / via OverlayFS and identity at /identity once its
provider is implemented. It must boot without silent formatting on
data mount errors and never generate fake unique identity.

The current Capsula boots one writable UBIFS rootfs. The proposed
partition scheme relocates kernel/DTB and needs real U-Boot validation.
Neither init/pivot nor per-volume firmware updating is implemented;
existing legacy image creation and all NAND write gates remain unchanged.

An autoresize data volume owns the free volume capacity after initial
provisioning. A future larger rootfs cannot grow without safe data-volume
migration/recreation. UBI reserves for wear and bad blocks are NOT free
space that an updater may consume. See docs/STORAGE_LAYOUT.md.
