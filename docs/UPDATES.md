# Update architecture: OpenIPC ideas, without copying unsafe flash assumptions

OpenIPC uses a device-specific release channel and a sysupgrade tool that
understands kernel/rootfs images. The useful concepts are device identity,
version detection, compatible firmware assets, and explicit kernel/rootfs
selection. Its NOR/SquashFS and NAND update scripts are NOT directly
compatible with our Capsula Mini NAND/UBIFS boot layout.

## Required phases

1. **Discover:** choose an update channel based on device variant, SoC,
   HAL ABI and current firmware version.
2. **Authenticate:** get manifest over TLS and verify an Ed25519 signature
   from a trusted public key provisioned on the device. Checksums alone
   are NOT a publisher authenticity check.
3. **Inspect:** reject incompatible SoC/board, kernel, HAL ABI, downgrade,
   missing artifacts, oversized partitions, or unapproved releases.
4. **Stage:** download complete firmware images into isolated storage, check
   their hashes, storage capacity and free space, never overwrite live
   bootloader/keys/BBT/calibration.
5. **Apply/rollback:** MUST remain disabled on the A113X first target until
   power-loss handling, UBI bad-block ECC, independent recovery/rollback,
   boot health and settings persistence are hardware-validated.
6. **Post-boot:** report health and firmware versions to the Application
   and centralized service. No automatic update without explicit policy.

## What is actually implemented now

firmware/updates/check.py is a **host-side offline reference checker**:
it requires a detached Ed25519 signature, trusted PEM public key, target
profile and installed version; validates compatibility, manifest fields
and NAND partition sizes; never fetches artifacts, never writes NAND.
The project does not store signing private keys or user-specific secrets.

An example signed release JSON has these fields:

    {
      "schema": 1,
      "target": "capsula-mini-native",
      "soc": "amlogic-a113x",
      "version": "1.0.0",
      "hal_abi_major": 1,
      "bootloader": "retain-vendor",
      "hardware_approved": true,
      "kernel_revision": "PINNED_KERNEL_SHA",
      "artifacts": {
        "Image": {"url": "https://example.org/release/Image", "sha256": "64_lowercase_hex", "bytes": 123456},
        "board.dtb": {"url": "https://example.org/release/board.dtb", "sha256": "64_lowercase_hex", "bytes": 123456},
        "rootfs.ubi": {"url": "https://example.org/release/rootfs.ubi", "sha256": "64_lowercase_hex", "bytes": 123456}
      }
    }

The example is conceptual, not an approved update or a real downloadable
release. The flag hardware_approved=true is only allowed after independent
hardware tests and authorized release signing.

The current builder manifests are expressly NOT_HARDWARE_VALIDATED and must
not be represented as installable updates.

## Future integration with Application

Application may call a separate, privileged native firmware update service.
No arbitrary shell command execution or update through the normal untrusted
HAL control socket. Version-check/status APIs may be read-only.
Update write operations need dedicated authorization, audit records,
transaction state, and recovery policy. No timer-based update monitoring is
enabled by the current code.
