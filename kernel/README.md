# Kernel and SoC platforms

SoC-specific kernel source and revision are defined once in
platforms/<soc>.json. Initial SoC: Amlogic A113X, based on the pinned
comp18man/vk-capsula-mini-a113x-linux source tree.

Concrete board defconfig and DTB selection belong to Builder device profiles.
Multiple speakers based on one SoC can share sources without source duplication.

Build Image, DTB and modules from sources; proprietary drivers and firmware
require explicit provenance and licensing review.
