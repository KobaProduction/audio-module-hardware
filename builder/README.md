# Builder

The only owner of concrete device profiles. This is the thin integration
layer over the shared kernel and firmware sources:

- Select SoC platform metadata from kernel/platforms/<soc>.json.
- Select physical board and variant from devices/<device>/profile.json.
- Compile the kernel using its shared source pin and board-specific config.
- Assemble the shared Alpine rootfs, then apply minimal board overlays.
- Produce kernel Image, DTB, UBI and manifest with validation metadata.

From repository root, the read-only build plan is:

    python3 -m builder.build plan --target capsula-mini-native

Builder never flashes a physical device. When needed, this whole directory
can be extracted into its own repository without moving individual devices.

## Reusable firmware-component selection

The device profile firmware.components list selects shared components from
firmware/alpine/components.json (Alpine APK packages and OpenRC services).
For example, removing bluetooth from a device profile removes the Bluetooth
package set and service startup from that device build without changing the
common firmware source. Removing wifi removes iwd and wireless-regdb. A
device cannot omit base. The local firmware packages are resolved by apk
from the Alpine repository: exact package revisions are not yet locked.

## Explicit HAL and kernel-driver selection

Each device supplies a capabilities.json declaration of its hardware
functions and a profile.hal.enabled_capabilities whitelist. Builder
intersects the whitelist with its selected firmware.components.
Disabled functions are not exposed to Application. Planned functions
are never advertised. Ring LED is deliberately absent from the Capsula Mini profile.

Kernel platform metadata maps known optional feature IDs to Kconfig
driver symbols. Builder writes a generated .config override and runs
olddefconfig, then fails if resolved settings contradict the selection.
This is an engineering gate: it does not prove that physical drivers
have probed or that all indirectly linked kernel code is removable.

For actual hardware status the future HAL runtime must probe Linux.
The static descriptor always sets runtime_verified=false.


## Storage design (not currently enabled)

Each device may declare storage.json separately from its active firmware
profile. The first Capsula candidate contains UBIFS rootfs, UBIFS
rootfs_data which autoresizes to the remaining UBI space. Identity
is an independent protected physical MTD partition after the boot chain
and before kernel/DTB.
The read-only storage-plan command checks MTD order and UBI space policy and never
changes the NAND or image builder. The active layout is explicitly
legacy-single-ubifs; activating a future layout without validating a
new early-init boot contract is forbidden.
