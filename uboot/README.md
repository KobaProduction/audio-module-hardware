# Bootloader

Capsula Mini native initially retains factory U-Boot/TPL.
DDR setup and boot-chain compatibility have not been validated with a
source-built replacement. The protected NAND region and factory keys,
calibration and BBT must never be overwritten by image assembly.
