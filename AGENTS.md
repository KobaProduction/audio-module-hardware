# AGENTS.md

Read README.md, then docs/ARCHITECTURE.md completely before work.
For GitHub repository ownership and Application handoff, read docs/REPOSITORIES.md.
For HAL capability/backend work read docs/HAL_CONTRACT.md and hal/README.md.
For OTA/version-check/update work read docs/UPDATES.md and docs/PERSISTENCE.md.
For filesystem/image layout work read docs/STORAGE_LAYOUT.md, docs/ARCHITECTURE_REFERENCES.md, firmware/storage/README.md and the selected Builder storage.json.
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

OpenWrt is an architecture/development-workflow reference ONLY. Do not create
OpenWrt SoC ports, feeds, toolchains, image build lanes or distro migration tasks.
Keep source-built Alpine and the existing kernel unless explicitly directed
to change the operating system. See docs/ARCHITECTURE_REFERENCES.md.

Use relevant skills and Git workflow from:
https://github.com/ArthurKoba/ai-agent-workflow

Current Capsula Mini has no persistent UBI volume separate from writable
rootfs. Never claim identity/settings survive a complete UBI overwrite;
enforce off-device verified backup/restore and hardware recovery first.

The OverlayFS multi-volume proposal is DESIGN ONLY: do not reformat the working UBI rootfs, install a new init, or assume SquashFS boot compatibility without hardware acceptance.

Existing protected reserved NAND holds U-Boot Environment with conflicting ethaddr copies. Do not choose or write ethaddr automatically, disclose values, or add a new Identity partition without evidence.
