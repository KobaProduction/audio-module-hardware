# Kernel and SoC platforms

SoC-specific kernel source and revision are defined once in
platforms/<soc>.json. Initial SoC: Amlogic A113X, based on the pinned
comp18man/vk-capsula-mini-a113x-linux source tree.

Concrete board defconfig and DTB selection belong to Builder device profiles.
Multiple speakers based on one SoC can share sources without source duplication.

Build Image, DTB and modules from sources; proprietary drivers and firmware
require explicit provenance and licensing review.

## Optional drivers

Each SoC's config_features maps an optional HAL function to kernel
Kconfig symbols. Builder derives the enabled feature set and generates
a kernel .config overlay, re-resolves Kconfig and checks the result
before compilation. Core SoC, boot, MTD and other mandatory kernel
support stays in the pinned defconfig.

Driver selection does not authorize exporting closed blobs. In the
current A113X defconfig some embedded firmware data is compiled into
the kernel; package and kernel blob provenance still need review before
any redistributable firmware release.
