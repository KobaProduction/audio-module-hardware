# Root filesystem and writable overlay ownership

This component owns generic boot-storage contracts, not Capsula-specific
flash offsets, volume budgets, or bootloader environment changes.

## OpenIPC NAND reference

Modern OpenIPC NAND layouts for selected XMedia SoCs mount a read-only
UBIFS rootfs lower, and overlay a writable UBIFS rootfs_data upper/work.
This is not necessarily SquashFS on NAND. NOR devices often use
SquashFS+JFFS2. A SquashFS root on UBIBLOCK is a separate, sometimes
retired OpenIPC NAND variant. Use the actual NAND precedent, not its
NOR-specific sysupgrade offsets.

## Proposed boot contract: source-only, not installed

    UBI volume rootfs       -> read-only UBIFS lower at /rom
    UBI volume rootfs_data  -> read/write UBIFS at /overlay
    /overlay/upper + /overlay/work -> merged OverlayFS at /
    UBI volume identity     -> read-only UBIFS at /identity
    /tmp                    -> tmpfs

The early init must execute before Alpine OpenRC starts. It must remount
the rootfs lower read-only, mount/validate the data and identity volumes,
create upper/work on the same filesystem, pivot_root into the merged root,
and transfer /dev and /proc before exec of /sbin/init. Neither the early
init nor bootloader parameters are installed by the current builder.
The existing kernel boot root name remains ubi0:rootfs in the proposal,
but a new init/pivot boot contract still needs physical acceptance.

If rootfs_data cannot mount, do not wipe it. Only a separately validated
recovery or volatile RAM overlay may be used, with explicit loss-of-
persistence indication. If identity cannot mount, do not invent a serial.
No automatic formatting, partition resizing, or writes on mount failure.

## Firmware lifecycle and ownership

Generic firmware supplies the root image, overlay init, packages and
service policy. Builder defines volume geometry and device-specific
mount/provisioning choices. The Application and optional diagnostics must
not address raw NAND or choose volume IDs.

Normal update: replace only the rootfs VOLUME, retain rootfs_data and
identity. Clean install: reset rootfs_data, preserve identity. Factory
reset: reset rootfs_data without replacing rootfs. No current updater
implements any of these writes safely.

A whole UBI image that recreates all volumes destroys persistent state.
The existing single-UBIFS image builder remains legacy-only and the
candidate multi-volume proposal is deliberately not installable.

## Candidate rootfs audit

builder.storage.audit_immutable_rootfs is a conservative read-only check
for common host/network credentials and device-unique state. It blocks
immutable lower-image packaging when known personalized files are found.
It is not a comprehensive secrets scanner, and does not make the
future storage design installable. Source and artifact acceptance differ.
