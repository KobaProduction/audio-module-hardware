# Rootfs / SquashFS / OverlayFS design for Audio Module

## Decision: use the OpenIPC NAND separation

For Capsula Mini start with read-only UBIFS for the system rootfs,
writable UBIFS for rootfs_data, and a merged OverlayFS namespace at /.
A third protected identity volume holds unique provisioned device state.
Use SquashFS as a future alternative lower filesystem, not as a required
A113X rootfs format. An existing vendor bootloader that expects
root=ubi0:rootfs must not be assumed to boot SquashFS through UBIBLOCK.

Current kernel command line roots the device in a SINGLE writable UBIFS
rootfs. UBI reports no free LEBs. The proposal does NOT describe the
currently running layout.

## Proposal: three UBI volumes inside existing MTD ubi partition

Current physical evidence: partition ubi = 212 MiB, PEB = 131072 bytes,
LEB = 126976 bytes; old rootfs holds 1652 LEBs, UBI has separate bad-
block management reserve, two bad PEBs were reported.

Only after verified external backup and successful recovery testing:

| Volume | ID | Maximum | Purpose |
| --- | --- | --- | --- |
| rootfs | 0 | 1024 LEB (about 124 MiB) | immutable read-only system |
| rootfs_data | 1 | 512 LEB (about 62 MiB) | writable user/test overlay |
| identity | 2 | 16 LEB (about 1.94 MiB) | protected identity, read-only mounted |
| unallocated capacity | n/a | 100 LEB (about 12.1 MiB) | future volume growth |

These are trial capacity BOUNDS within the old rootfs LEB budget, not
confirmed image sizes. Spare UBI LEBs here are NOT a substitute for
UBI-internal bad-block reserves. The true new-image capacity must be
checked against physical NAND, bad-block behavior and generated images.
The identity volume must not be provisioned by putting universal serial
or secret placeholders into a public rootfs image.

The builder storage.json describes ONLY a design candidate. Validation
rejects overcommit, changed factory/volume policy, and an assertion that
boot/migration/recovery have been validated. The current single-volume
builder path remains active and unchanged.

## Mount and update contract

    /rom          -> UBIFS rootfs lower, mount read-only
    /overlay      -> UBIFS rootfs_data, persistent
    /overlay/upper + /overlay/work -> same UBIFS filesystem
    /             -> OverlayFS merged root
    /identity     -> read-only UBIFS identity, separate from resettable data
    /tmp          -> tmpfs

A filesystem update must use a safe, proven rootfs-volume-only write,
not an entire rootfs.ubi image containing all volumes. rootfs_data
retains settings and test artifacts. A clean install clears only
rootfs_data; a factory reset clears only rootfs_data without flashing
the base OS. Unique identity and factory NAND are preserved in all modes.

OverlayFS upper files and whiteouts can mask newly shipped lower OS
defaults. Settings migration MUST handle those semantics; replacing
rootfs is not itself an automatic settings migration.

## Hardware acceptance needed before activation

1. Enable CONFIG_OVERLAY_FS in the pinned kernel; retain UBIFS/UBI.
2. Establish and boot-test early init and pivot_root before Alpine
   OpenRC; test preserved init/bootargs and correct /rom mounting.
3. Initialize each volume with proper UBIFS metadata/owner/modes.
   Protect and provision identity from verified factory source.
4. Build actual rootfs and measure against planned volume limits;
   verify NAND bad-block, ECC and UBI reserve handling.
5. Test power-loss, corrupted overlay and insufficient-storage
   scenarios without silently erasing existing settings.
6. Implement signed per-volume rootfs updates and recoverable
   rollback; do not enable automatic NAND writes before evidence.

SquashFS-on-ubiblock remains a research-only backend until its own
kernel/bootloader/init mount contract is hardware verified.

## Sources inspected

OpenIPC wiki: en/nand-rootfs-layouts.md.
OpenIPC Firmware: general/overlay/init,
general/scripts/ubifs/ubinize.cfg,
br-ext-chip-hisilicon/board/hi3516ev200/ubinize-nand.cfg.

No foreign firmware installation code or NAND offsets were copied.

## Local no-flash storage review

The build-host storage-plan command only computes volumes and blockers,
and does not run ubinize, mount or write NAND. The storage-audit
command checks a staged rootfs for known personal data paths and
fails closed if any are present. It never reads or logs their contents.
A clean audit is necessary, not sufficient: future components can store
credentials elsewhere, and the device must still be hardware-tested.

The present Alpine staging uses a user-supplied authorized SSH public key
and a board-local USB identity placeholder. The future immutable root
must not embed personalized credentials or a supposedly unique serial.
The identity/data volume must be provisioned separately, with validated
permissions and verified restore/migration. This has not been implemented.
