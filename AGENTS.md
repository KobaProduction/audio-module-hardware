# AGENTS.md

Read README.md, then docs/ARCHITECTURE.md completely before work.
For HAL capability/backend work read docs/HAL_CONTRACT.md and hal/README.md.
For OTA/version-check/update work read docs/UPDATES.md.
For target changes read builder/README.md and the selected device profile.

Project: Koba Audio Module — Hardware. Own reusable SoC/kernel enablement,
U-Boot policy, source-based Alpine image creation, builder-owned device profiles, and
eventually transport/backup/recovery tooling.

Current first supported profile is capsula-mini-native on Amlogic A113X.
main contains shared sources and builder/device profiles, NOT unrelated device
fork branches. Do not incorporate unique device secrets, factory dumps,
closed vendor binaries or unlicensed blobs into Git.

Full source build is NOT hardware acceptance. Preserve the factory
bootloader and lower 0x01200000 of NAND; no flasher/erase step is
part of the initial builder. Never call a generated image flash-ready
without reproducible tests and a validated recovery path.

Future repository extraction follows OpenIPC-style independent component
ownership while preserving pinned source and image contracts.

Use relevant skills and Git workflow from:
https://github.com/ArthurKoba/ai-agent-workflow
