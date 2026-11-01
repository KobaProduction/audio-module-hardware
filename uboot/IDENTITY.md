# Factory identity discovery and protected custody

Read-only inspection of the running Capsula Mini on 2026-11-01 found
two CRC32-valid U-Boot Environment slots within the 6 MiB protected
reserved MTD partition. Relative offsets: 1048576 and 1179648.
Each valid slot contains a 65536-byte CRC-framed environment.

The serial key is present in a valid slot and matches a previously
saved U-Boot console capture. The two valid ethaddr values DIFFER:
one matches the post-flash console capture, while U-Boot's active
copy selection is unverified. Do not pick a MAC by guesswork.

The current Alpine system has neither fw_printenv/fw_setenv tools
nor /etc/fw_env.config. No U-Boot Environment writes were attempted.

Factory rsv-keys, rsv-bbt, rsv-ddr and related calibration files are
already preserved in private recovery backups. A new DPAPI CurrentUser
encrypted custody archive on KOBA-LAPTOP contains the captured
identifiers, two env slots and factory sections; its encrypted archive
was decrypted and integrity-tested. DPAPI is NOT a portable backup.
Keep the original NAND recovery copies independently.

Identity policy:
- Read nonsecret identifiers from proven factory/U-Boot sources.
- Keep private keys, calibration/BBT, encrypted credentials in their
  original protected factory areas. Do NOT migrate them into env.
- Store user Wi-Fi credentials, Bluetooth pairs and app preferences
  in rootfs_data with explicit update preservation rules.
- No new Identity MTD partition and no dynamic MAC/serial rewriting.
- Confirm authoritative redundant U-Boot Environment behavior and
  underlying factory source before exposing ethaddr as authoritative.

For future offline audits:
  python3 -m uboot.env_audit --file PATH_TO_PRIVATE_RESERVED_BACKUP

This command reports CRC/consistency only and never displays values.
It does not read live MTD or make any writes.
