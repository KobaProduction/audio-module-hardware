# Physical NAND and logical UBI storage architecture

## Requested physical order

Future new-install layout:

    U-Boot / boot-chain (existing bootloader, reserved, tpl, misc)
    Identity (separate protected MTD partition)
    Kernel and its separate DTB slot
    UBI partition to physical NAND end:
      rootfs       (read-only UBIFS, image-sized)
      rootfs_data  (writable UBIFS OverlayFS, autoresize remainder)

The UBI rootfs and rootfs_data are LOGICAL wear-levelled volumes, not
contiguous fixed physical offsets. Rootfs Data "fills to the end"
by claiming all remaining UBI-available volume blocks at initialization.
No additional fixed tail reserve is allocated. UBI itself retains
bad-block/wear-levelling reserves, which must not be disabled.

Identity is a protected PHYSICAL MTD partition between the boot chain
and Kernel, not a third UBI volume after rootfs_data. Its storage format
and provisioned serial source are still UNKNOWN. Until decided, an MTD
partition is not automatically mountable under /identity.

## Actual physical state (256 MiB NAND, do NOT reflash)

| MTD | Start MiB | Size MiB |
| --- | ---: | ---: |
| bootloader | 0 | 2 |
| reserved | 2 | 6 |
| tpl | 8 | 8 |
| misc | 16 | 2 |
| kernel | 18 | 25 |
| dtb | 43 | 1 |
| ubi | 44 | 212 |

Actual UBI contains only one writable UBIFS rootfs, 1652 LEB of 126976
bytes each, no free volume LEBs and two known bad physical eraseblocks.
Boot chain and factory protected regions (first 18 MiB) must not be
changed without independent recovery validation.

## Proposed MTD candidate (NOT HARDWARE VERIFIED)

| MTD | Start MiB | Size MiB | Policy |
| --- | ---: | ---: | --- |
| bootloader | 0 | 2 | Preserve |
| reserved | 2 | 6 | Preserve |
| tpl | 8 | 8 | Preserve |
| misc | 16 | 2 | Preserve |
| identity | 18 | 2 tentative | Preserve even during clean install |
| kernel | 20 | 25 | New kernel location |
| dtb | 45 | 1 | New DTB location |
| ubi | 46 | 210 | Last partition, to physical end (256 MiB) |

Inside the final 210 MiB UBI MTD:
- rootfs (volume ID 0): immutable UBIFS base, sized to produced image
  with initial engineering cap 1024 LEB (~124 MiB).
- rootfs_data (volume ID 1): UBIFS with autoresize-remainder, assigned
  ALL capacity available after rootfs and required UBI internal reserves.
- There is NO UBI identity volume and no fixed 100-LEB unallocated
  reserve. UBI capacity for rootfs_data cannot be calculated precisely
  before the actual image, NAND bad blocks and UBI overhead are known.

Identity 2 MiB is also a proposal; no redundancy, ECC handling or
provisioning format has been validated. The existing factory reserved
partition is preserved separately and is not assumed to be expendable.

**Critical boot blocker:** kernel moves from 18 to 20 MiB and DTB moves
from 43 to 45 MiB. Current U-Boot/kernel/DTB may hard-code these
offsets. The current bootloader's ability to load the proposed layout
is UNKNOWN. No real flash or DTB update is authorized by this file.

## Future filesystem and update policy

    /rom             read-only UBIFS rootfs lower
    /overlay         UBIFS rootfs_data, read-write
    /overlay/upper   OverlayFS upperdir
    /overlay/work    OverlayFS workdir (same UBIFS mount)
    /                merged OverlayFS
    /identity        read-only identity service/mount, backend unresolved
    /tmp             tmpfs

System update updates kernel/DTB and rootfs UBI VOLUME (not the entire
UBI MTD), preserving rootfs_data and identity. Clean install resets
rootfs_data, preserving identity and factory boot chain. Factory reset
resets only rootfs_data; no firmware write.

OverlayFS whiteouts and persistent upper files can shadow new lower
defaults; migrations must version and merge config values explicitly.
SquashFS-on-ubiblock is only a research option, not the A113X boot
contract.

## Cost of allocating all remaining space

The requested rootfs_data autoresize gives all currently available UBI
volume space to user data; it does not leave unallocated volume blocks
for a future rootfs resize. If a later firmware rootfs grows, an updater
must safely snapshot and temporarily shrink/recreate rootfs_data (or
implement another hardware-proven migration route), verify restored
data and reserve enough RAM/external storage. A simple rootfs-volume
write cannot magically enlarge a fully allocated rootfs. The identity
MTD region must never be used as working space for this operation.

Rootfs image size and its future growth policy therefore remain separate
engineering constraints. UBI's internal bad-block reserves are mandatory
and cannot be consumed to make more user storage.

## Required acceptance before activation

1. Verify actual bootloader source/environment and relocation capability,
   DTB/MTD map, init= behavior, kernel/DTB loading and recovery.
2. Build rootfs and measure true UBIFS output plus UBI reserved blocks.
3. Select and verify identity format, source, integrity/ECC/redundancy,
   provisioning and recovery without exposing unique secrets in Git.
4. Implement early UBIFS read-only lower + persistent OverlayFS pivot;
   prove fallback that never silently formats a damaged upper volume.
5. Implement verified off-device backups, rootfs-only updates and
   reset semantics, test against power loss and bad NAND blocks.
6. Keep active legacy builder image and live Capsula untouched until
   independently hardware-validated.

Builder/storage.py is read-only. It checks contiguous aligned MTD
ranges, fixed boot-chain preservation, logical UBI mode and fail-closed
readiness gates, but CANNOT verify real boot or flash reliability.

## OpenIPC precedent

OpenIPC NAND uses UBIFS rootfs + rootfs_data with OverlayFS and often
vol_flags=autoresize; SquashFS is not universally the NAND lower.
Unlike some OpenIPC boards, this Capsula currently has separate physical
kernel and DTB partitions. Do not copy OpenIPC U-Boot flash offsets or
run its sysupgrade as-is.
