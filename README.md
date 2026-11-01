# Koba Audio Module ? Hardware

Hardware enablement and firmware tooling for the Koba Audio Module device family.

## Responsibilities

- Linux kernel, drivers, Device Tree and hardware variants.
- Reproducible Alpine/Linux firmware and target-specific builds.
- Flashing, inspection, device provisioning, backup and recovery tooling.
- Board/SoC capabilities and low-level hardware compatibility.

VK Capsula Mini A113X is an initial device target, not the identity of this project.
Native and SPDIF-modified variants may use different Device Trees.

## Boundaries

- The daemon, API and web UI belong to KobaProduction/audio-module-application.
- Central voice assistants and shared conversations live in a separate backend.
- Do not commit personal factory NAND dumps, proprietary blobs or credentials.

## Status

Initial repository only. Architecture, licensing, firmware imports, target layouts
and build systems will be agreed separately.

Workflow: https://github.com/ArthurKoba/ai-agent-workflow

## Development status

Only project scope and repository-level safety checks are initialized.
No application code, board support sources or runtime toolchain have been adopted.
The current pre-push and CI verification checks documentation completeness, whitespace,
and accidental secrets; it **rejects source files** until the relevant build, lint and
test toolchain is approved and added to the same gate.

On a fresh checkout, enable the tracked Git hook:

    git config core.hooksPath .githooks

Run the initial verification from the repository root:

    sh scripts/verify.sh
