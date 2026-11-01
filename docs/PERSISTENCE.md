# Device identity and settings persistence — policy v1 (NOT install-ready)

## Current device evidence (Capsula Mini, 2026-11-01)

- NAND: bootloader (2 MiB), reserved (6 MiB), tpl (8 MiB),
  misc (2 MiB), kernel, dtb, ubi.
- Protected factory/boot-chain region is below 0x01200000 (18 MiB).
  This does NOT prove that every unique serial or credential is stored there.
- Linux rootfs is a writable UBIFS mounted from ubi0:rootfs.
- Read-only ubinfo reports ONE rootfs volume: 1652 LEBs, 200 MiB,
  zero available UBI eraseblocks and two physical bad blocks.
- SSH host keys, iwd Wi-Fi settings, Bluetooth state, machine-id and
  user SSH authorization may live INSIDE the replaceable rootfs.
- The current Builder produces a whole UBI image containing rootfs.
  Replacing it can erase all mutable rootfs state.
- USB gadget serial value capsula-mini-unprovisioned is NOT a verified
  factory serial or a unique device identifier.

Therefore our existing implementation CANNOT guarantee preserving
serial numbers, pairing and settings during UBI firmware replacement.
No on-device backup, restore, migration, update or rollback service is installed.

## Data ownership and install modes

| Data | system-update | clean-install | factory-reset |
| --- | --- | --- | --- |
| Factory NAND: bootloader, TPL, BBT, factory keys/calibration | Preserve | Preserve | Preserve |
| Unique device identity, provisioned USB serial, SSH host keys, machine-id | Preserve | Preserve | Preserve |
| User Wi-Fi/BT pairing, SSH authorized keys, hostname, app settings | Preserve | Reset | Reset |
| Kernel, DTB, rootfs and OS packages | Update | Replace | Unchanged |

Clean install is not a factory-chip erase and must not change immutable
factory identity. Reprovisioning identity needs its OWN explicitly
authorized, audited operation.

The candidate inventory of rootfs identity vs user paths is in
builder/devices/capsula-mini-native/persistence.json. This is NOT yet
a complete verified backup source list; future services may add paths.
New applications must declare owned mutable paths and versioned migration
procedures before they may be updated.

Suggested separate stores (NOT deployed yet):
- /var/lib/audio-module/identity — generated/provisioned device secrets
- /var/lib/audio-module/settings — user application preferences
- /var/lib/iwd and /var/lib/bluetooth — network and pairing state

Do not restore entire old /etc over new firmware; migrate specific known
paths with permissions, owners and application/schema versions intact.

## Safe migration requirement

With zero spare UBI LEBs, no persistent data volume can be allocated
safely in the current full-size UBI layout without redesign/repartition.
A verified OFF-DEVICE backup is therefore required before full UBI
replacement, even for a clean install (identity-only backup).

Before allowing writes:
1. Verify actual device identity/serial source and where it is stored.
2. Enumerate ALL mutable state needing preservation.
3. Create encrypted, restricted off-device backups with verifiable hashes,
   owner/mode metadata and restore validation. NEVER put backups in Git.
4. For system-update, restore identity and user state; for clean-install,
   restore identity only. Apply declared schema migrations.
5. Test post-restore serial, SSH, Wi-Fi, Bluetooth and app settings.
6. Establish and hardware-test bootable recovery, UBI bad-block handling
   and power-loss behavior before calling any update safe.

In the future, separate rootfs, immutable identity and user-data volumes
or partitions may be preferable. Repartitioning or re-creating UBI
volumes is destructive and MUST NOT be done on the working speaker
without separate hardware acceptance.

## Implemented behavior now

firmware/updates/persistence.py validates the device-specific preservation
inventory and returns explicit plans for system-update, clean-install
and factory-reset. ALL MODES return can_apply=false, with blockers.
The signed-release checker also returns the preservation plan.
No code in this phase touches flash or reads private key material.

This is SOURCE VALIDATION, not proof of operational persistence.


## Future storage split (not yet active)

Builder/devices/capsula-mini-native/storage.json contains a planned
three-volume UBIFS layout. System updates would replace only the
read-only rootfs volume; a persistent rootfs_data OverlayFS layer
would keep user configuration, while an independent identity volume
would survive clean install and factory reset. The existing device has
none of these separate volumes; all current update/reset write paths
remain blocked until a verified migration and recovery path exists.
See docs/STORAGE_LAYOUT.md.
