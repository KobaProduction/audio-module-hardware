# Bootloader

Capsula Mini native initially retains factory U-Boot/TPL.
DDR setup and boot-chain compatibility have not been validated with a
source-built replacement. The protected NAND region and factory keys,
calibration and BBT must never be overwritten by image assembly.

## Vendor boot-chain custody / reverse engineering

The original author's distribution contains closed Amlogic loader utilities
and the device has vendor bootloader and TPL NAND regions. Their source
licensing and reproducible DDR/SPL initialization are not yet known.

Evidence collected from the board:
- bootloader NAND partition: 2 MiB
- reserved NAND partition: 6 MiB, contains factory-specific data
- tpl NAND partition: 8 MiB
- kernel NAND partition follows above 18 MiB protected region

Factory files including bootloader.bin, tpl.bin and reserved areas remain in
local restricted backups. Do not publish or overwrite device-specific
copies, calibration data, BBT or keys. Reconstruct the boot chain from
source only after identifying upstream U-Boot/SPL support and confirming a
hardware recovery path. No bootloader replacement target is implemented.

## Verified U-Boot environment and factory identity

Read IDENTITY.md. Reserved NAND has CRC-valid env copies containing serial/ethaddr, but the ethaddr copies disagree. No new identity MTD is required and no U-Boot Environment writes are allowed.
