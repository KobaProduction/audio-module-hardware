# Shared Alpine firmware layer

The firmware layer is deliberately **not** a device description. It owns:

- Official pinned Alpine minirootfs/apk sources and signing-key enforcement.
- Generic, reusable packages and OpenRC services in components.json.
- Common overlay files for SSH policy, USB gadget implementation, and later
  update/network maintenance utilities.

A Builder device profile chooses the components to include. Unselected
components must not be installed or enabled. Device-specific IWD quirks,
gadget identification, network IP/MAC, sensors, partitions, and peripheral
configuration stay under builder/devices/<device>/overlay/.

The common USB gadget service reads its per-device identity from
/etc/conf.d/usbgadget. It is NOT specific to Capsula Mini. The current
prototype VID/PID are retained for compatibility with Windows; production
USB identity and unique serial/MAC provisioning need dedicated review.

The rootfs still needs full build/boot verification; do not use it to
overwrite a working device until boot and recovery gates are satisfied.
