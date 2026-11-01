# Capsula Mini storage contract: preserve factory identity in place

## Verified read-only evidence, 2026-11-01

The existing NAND reserved MTD area already contains U-Boot Environment.
Two CRC32-valid environment blocks were found in the running 6 MiB
reserved partition at relative offsets 1048576 and 1179648, with a
64 KiB environment block size. The serial key agrees with a previously
captured U-Boot console environment. Both copies of ethaddr are valid
but contain DIFFERENT MAC values; one matches the post-flash console
capture. We must determine which copy U-Boot actively selects before
using a factory MAC automatically.

Unique values, factory keys, bootloader, BBT and calibration remain
in private original backup files plus an additional encrypted local
custody archive. No identifier values belong in public source Git.

## Physical MTD: unchanged vendor-compatible partitions

| MTD | Start MiB | Size MiB | Policy |
| --- | ---: | ---: | --- |
| bootloader | 0 | 2 | Protected |
| reserved | 2 | 6 | Protected: env, keys, BBT, calibration |
| tpl | 8 | 8 | Protected |
| misc | 16 | 2 | Protected |
| kernel | 18 | 25 | Retain original address |
| dtb | 43 | 1 | Retain original address |
| ubi | 44 | 212 | Last MTD partition, to NAND end |

NO separate physical Identity MTD partition, no relocation of Kernel
or DTB. Identity is a read-only logical provider backed by the actual
existing U-Boot Environment and factory sources, not a mountable root.

The current UBI has a single writable rootfs UBIFS volume of 1652
LEBs, no free available UBI volume LEBs and two bad PEBs in the
observed session. Do not assume a new UBI split can be created live.

## Candidate logical UBI volumes (design only)

Inside the existing final UBI MTD partition:

- rootfs (vol 0): immutable UBIFS OS, image-sized (tentative
  maximum 1024 LEB pending artifact measurement), mounted /rom ro.
- rootfs_data (vol 1): writable UBIFS, OverlayFS upper/work,
  autoresize to all remaining UBI-available volume capacity.
- No third UBI identity volume and no artificial fixed trailing
  free-volume reserve. UBI internally reserves bad-block/wear PEBs.

Logical UBI volumes are NOT physical contiguous NAND offsets. Exact
rootfs_data LEB capacity is unknown until an actual build, UBI
overhead, bad-block reserve and flash attach are measured.

    /rom             read-only UBIFS system
    /overlay         writable UBIFS data volume
    /overlay/upper   OverlayFS upper
    /overlay/work    OverlayFS work
    /                merged root namespace
    /tmp             volatile tmpfs

Neither /identity filesystem mount nor writes to U-Boot Environment
are required for this scheme. The future identity API reads the
verified existing factory source through a restricted provider.

## Update/reset semantics

System update replaces compatible Kernel/DTB and rootfs, preserving
selected user configs and all protected NAND/identity material.
Clean install resets user config, preserves factory env and serial.
Factory reset resets only the user layer.

As in OpenWrt NAND sysupgrade, replacing rootfs may require backing up
and recreating rootfs_data. Autoresize uses all free volume space,
which means a later enlarged rootfs cannot automatically grow while
rootfs_data owns the rest. An upgrade must have a verified migration
and temporary storage strategy.

OverlayFS whiteouts can mask new OS defaults, so copy selected
configuration state with migrations, not arbitrary full upperdir data.
SquashFS-on-ubiblock is only a research provider for another verified
boot contract, not a confirmed current A113X design.

## Open blockers

- The two valid ethaddr values conflict; authoritative U-Boot active
  copy selection and final MAC provenance are unverified.
- Current Alpine lacks fw_printenv, fw_setenv and fw_env.config.
- Building the two UBI volumes, early-init pivot and any on-device
  updater remain unimplemented and untested.
- Factory serial source may require further read-only validation.
- Exact rootfs capacity, UBI ECC/bad-block/power-loss recovery and
  rootfs_data migration must be accepted on a recoverable physical unit.
- The default Builder continues emitting legacy single writable UBIFS.
  storage-plan returns may_install=false and may_switch_boot=false.

See docs/OPENWRT_MIGRATION.md and uboot/IDENTITY.md.
