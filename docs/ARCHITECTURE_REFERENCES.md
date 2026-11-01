# Development architecture references — not an OpenWrt port

## Decision and scope

We use **OpenWrt as an engineering architecture reference**, not as a target
operating system or firmware distribution. The first Audio Module device,
Capsula Mini (Amlogic A113X), continues to use source-built Linux with Alpine
3.24.1, OpenRC, iwd and its existing boot/storage contract. No OpenWrt
`target/linux` port, toolchain, feeds, userspace, image, sysupgrade or
`openwrt-plan` build phase belongs in this project.

The goal is the **development method**: shared SoC support, declarative board
profiles, modular components, deterministic source inputs, a single image
assembler, controlled updates and device-specific validation. Adapt ideas
without copying platform-specific implementation or flash assumptions.

## Architecture concepts mapped to owners

| OpenWrt concept (reference) | Audio Module owner / concrete rule |
| --- | --- |
| `target/linux/<family>` / shared kernel patches | `kernel/platforms` owns SoC sources, revision pins, config features and patches; no board duplication |
| Device definitions and DTS variants | `builder/devices/<device>` holds board wiring, DTS selection, NAND geometry and minimal variants |
| Packages / feeds / dependencies | `firmware/alpine/components.json` holds reusable Alpine packages and OpenRC services; Builder selects optional components |
| ImageBuilder `PROFILE`, `PACKAGES`, `FILES` | Builder resolves device profile, packages, overlays and artifacts from pinned inputs; no OpenWrt ImageBuilder binary required |
| Build profiles and release manifests | Builder produces target-scoped artifact checksums and compatibility metadata; a completed build is not hardware approval |
| Read-only system + persistent data | `firmware/storage` defines generic UBIFS/OverlayFS behavior; `builder/storage` validates device-specific capacity (design-only) |
| Factory data and U-Boot environment separation | `uboot` and protected NAND remain authoritative; the identity provider must only read verified factory sources |
| `sysupgrade` / backup-retention principles | `firmware/updates` owns an independent signed compatibility checker, preservation contract and future recoverable updater — not OpenWrt sysupgrade |

OpenIPC is an **independent** reference for eventual component/repository
ownership and minimal device overlays; OpenIPC and OpenWrt are not the same
project or a required runtime dependency. The current integrated Hardware
repository retains these boundaries now and may split later only when useful.

## Non-goals and protected invariants

- No OS migration or OpenWrt A113X port. No change to the Alpine toolchain,
  package repositories or boot process for the sake of architectural similarity.
- No automatic migration from OpenRC to procd, Alpine configuration to UCI,
  Alpine APK feeds to OpenWrt feeds, or the vendor image to sysupgrade.
- Preserve the exact current MTD partition offsets, vendor U-Boot/TPL,
  factory reserved contents and recorded backups.
- Do not add an Identity MTD partition: factory identities remain in verified
  reserved/U-Boot sources; conflicting redundant `ethaddr` copies block
  choosing a canonical MAC until proven.
- Do not activate the proposed read-only rootfs + rootfs_data/OverlayFS
  migration before independent hardware recovery and retention tests.
- No new build mode, downloadable distribution checkout or background
  task merely to mimic a reference architecture.

## Immediate development workflow

1. Select a device profile as data; resolve shared SoC/kernel and Alpine
   component inputs once. Pin release inputs, including hashes where relevant.
2. Assemble with the existing Builder; compile only enabled kernel drivers,
   package only selected services and apply board overlays last.
3. Check file provenance, image bounds, NAND preservation, optional feature
   completeness and generated manifests offline.
4. Validate output on recoverable hardware before any firmware installation,
   persistence switch or update authorization. Retain independent factory
   recovery paths and keep a known-good build.
5. Move mature reusable logic to the correct component owner instead of
   copying it into each device profile or making per-device Git branches.

For implementation sources and safety see `docs/ARCHITECTURE.md`,
`docs/STORAGE_LAYOUT.md`, `docs/PERSISTENCE.md` and `docs/UPDATES.md`.
The useful external reference points are OpenWrt's
[`target/linux`](https://github.com/openwrt/openwrt/tree/main/target/linux),
[`include/image.mk`](https://github.com/openwrt/openwrt/blob/main/include/image.mk)
and [ImageBuilder documentation](https://openwrt.org/docs/guide-user/additional-software/imagebuilder).
Their content informs the design; they are not dependencies of this build.
