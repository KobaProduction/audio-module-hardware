# GitHub repositories, owners and Application handoff

This is the cross-repository ownership and agent navigation map for Koba Audio
Module. It describes the existing arrangement, not a firmware installation
approval or an instruction to split repositories.

## Actual GitHub layout

| Repository | Owns | Must not own |
| --- | --- | --- |
| [KobaProduction/audio-module-hardware](https://github.com/KobaProduction/audio-module-hardware) | Kernel/SoC, DTS, factory U-Boot policy, Alpine firmware, internal Builder, board profiles, HAL declaration, images, backup/flash/recovery tools | Application daemon, audio graph, management UI, voice orchestration |
| [KobaProduction/audio-module-application](https://github.com/KobaProduction/audio-module-application) | Future always-on device daemon, local API, web UI, audio routing/pipelines, event/action handling, connectors to external assistants and home automation | Drivers, DTB/flash partitions, U-Boot, firmware image creation, factory private data |

There are exactly **two Audio Module repositories** now. Do not create an
audio-module-firmware or audio-module-builder repository. Kernel, U-Boot,
Firmware, Builder, HAL and Tools are logical components within Hardware.
Extraction into additional repositories is a **future option only** if
ownership and independent release cycles justify it; no such migration is
approved. Hardware owns device profiles under builder/devices, not a Git
branch for each speaker. Both projects use main for shared integration.

[ArthurKoba/ai-agent-workflow](https://github.com/ArthurKoba/ai-agent-workflow)
is an independent **universal workflow/skill library**, not a Koba Audio
Module product repository. Its AGENTS.md routes to on-demand task skills;
its rules do not replace project-local architecture. OpenIPC inspired
component separation and minimal board overlays. OpenWrt inspired SoC,
device, package and image development patterns **only**. Neither OS is
being ported to replace our source-built Linux/Alpine. See
[architecture references](ARCHITECTURE_REFERENCES.md) for the details.

## Hardware directory authority / owner routing

| Question or change | Read here |
| --- | --- |
| Pinned A113X kernel and reusable SoC patches, Kconfig | kernel/README.md, kernel/platforms, kernel/patches |
| Factory U-Boot, serial, MAC, protected NAND | uboot/README.md, uboot/IDENTITY.md |
| Shared Alpine packages, OpenRC and generic rootfs overlay | firmware/alpine/README.md, firmware/alpine/components.json |
| **Concrete board and variant**, DTB/defconfig choice, enabled features, NAND geometry and device-specific overlay | **builder/devices/<device>/** and builder/README.md |
| Rootfs/kernel/UBI build orchestration, image manifest | builder/build.py and builder/README.md |
| HAL semantic IDs and capability JSON schema | docs/HAL_CONTRACT.md, hal/README.md and hal/manifest.py |
| Persistent data, upgrade/backup policy | docs/STORAGE_LAYOUT.md, docs/PERSISTENCE.md, docs/UPDATES.md |
| Transport, recovery, diagnostics | tools/README.md |
| Third-party provenance and licensing | docs/AUTHOR_SOURCE_MAPPING.md, kernel/provenance |
| App daemon, API, UI, audio graph | **Application** repository and its [Issue #1](https://github.com/KobaProduction/audio-module-application/issues/1) |

Kernel and Firmware own reusable source. Only Builder selects device-specific
wiring, NAND geometry, components, overlays and optional features. Runtime
audio routing, event handling and UI are **Application** concerns; a
board-specific capability declaration is not application runtime code.
External voice assistant orchestration is not owned by either device repo.

## Hardware → Application: what actually exists

Hardware Builder currently emits the declared capability JSON at
/usr/share/audio-module/capabilities-v1.json, schema
koba.audio-module.capabilities, version 1, origin builder-declared,
runtime_verified false. The [HAL contract](HAL_CONTRACT.md) defines the
meaning of stable IDs, optional features, unknown counts and Linux provider
hints. These are **build-time declarations, not proof that devices work**.

No general, versioned on-device HAL IPC or native HAL daemon exists yet.
No stable ALSA index, sensor endpoint, SPDIF routing, application API or
update-write command should be inferred from a board profile. Application
should design runtime discovery and its local API using the Hardware HAL
contract, while coordinating native provider ownership through
[Hardware #4](https://github.com/KobaProduction/audio-module-hardware/issues/4).
Application must not treat runtime_verified=false as available hardware.

The Application repository exists but has **no runtime implementation yet**.
Its framework, IPC/API, audio engine and service split are not approved.
See its [architecture Issue #1](https://github.com/KobaProduction/audio-module-application/issues/1).
A future Application release can be selected and bundled **by Hardware's
existing internal Builder**, only after its package/version compatibility
contract is agreed and implemented. Do not move Builder to Application or
bundle an unimplemented/unauthorized runtime.

Firmware updates, flash, U-Boot and identity are privileged Hardware
boundaries. Application can eventually consume read-only status and an
authorized update service, not perform raw NAND writes via a normal API.

## New-agent entry and GitHub hygiene

1. In Hardware, read AGENTS.md, then README.md and docs/ARCHITECTURE.md as
   routed. Load domain documents from the table only when relevant.
2. For Application tasks, enter that separate repository, read its own
   AGENTS.md and README.md, and inspect its live GitHub Issue #1. Link back
   to this Hardware-owned contract; do not duplicate it as a second source.
3. Use the [Git workflow skill](https://github.com/ArthurKoba/ai-agent-workflow/blob/main/skills/git-workflow.md)
   and actual GitHub permissions. The project's AI writer publishes changes
   through a branch/PR as required; independent reviewer validates and merges.
   No long-lived per-device branches.
4. Tracked .githooks/pre-push runs scripts/verify.sh when the checkout
   explicitly has core.hooksPath=.githooks. The same script is run by
   .github/workflows/verify.yml on push/PR. See README.md for local build.
   Merely having hook files does not prove they are active in another clone.
5. .gitignore excludes local .work/, generated images, credentials and
   private NAND/device dumps. Do not upload closed vendor binaries or
   backup archives. Ignore rules do not grant redistribution rights.

AGENTS.md is the mandatory local map. CLAUDE.md or an AGENT.cmd launcher is
not part of this repository's current contract or necessary for onboarding.

## Transfer versus physical acceptance

Hardware's **source-architecture/build foundation** can be handed to the
Hardware backlog while Application development begins now. A source-based
Alpine/Kernel/DTB/modules/UBI build was completed in WSL; a later DTS rename
was independently compiled and gave a byte-identical DTB. **The latest
complete image is not yet physically booted or hardware-accepted.**

Hardware remains responsible for actual boot/peripheral tests, recovery,
safe UBI persistence and update apply, factory identity (conflicting
redundant ethaddr values), and the unverified SPDIF variant. Do not flash
the working speaker or assume user data persists across whole-UBI writes.
These independent tasks stay open in GitHub:
[HAL #4](https://github.com/KobaProduction/audio-module-hardware/issues/4),
[identity/storage #7](https://github.com/KobaProduction/audio-module-hardware/issues/7),
[updates/recovery #3](https://github.com/KobaProduction/audio-module-hardware/issues/3)
and [architecture improvements #10](https://github.com/KobaProduction/audio-module-hardware/issues/10).

Completing the repository/handoff documentation **does not close** those
hardware-acceptance Issues or imply production readiness.
