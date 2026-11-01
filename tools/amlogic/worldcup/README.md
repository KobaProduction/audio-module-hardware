# Amlogic WorldCup USB transport

This is the SoC/boot-ROM transport layer, NOT a Capsula Mini firmware builder.

- Windows source-only vendor transport experiments live under windows/.
- Board-specific NAND maps and factory calibration MUST come from a reviewed
  builder/devices profile rather than being hard-coded in common tools.
- External update.exe and DLLs are not included and may not be redistributed
  without licensing review.
- Discovery and backups do not constitute safe flashing or recovery proof.
- Never write bootloader/TPL/keys/BBT without independent device recovery.

The source tools were developed during the earlier Capsula Mini bring-up.
The mainline transport API and flash-profile integration are not yet complete.
