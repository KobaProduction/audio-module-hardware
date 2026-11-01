# OpenWrt source baseline (research only)

OpenWrt v25.12.6 is pinned by the peeled annotated tag commit. Its
`feeds.conf.default` points to five exact feed commits, copied in
`sources.json`. On 2026-11-01 the pinned release had 47 entries in
`target/linux`, with no `amlogic` or `meson` target. The exact tag and
feeds were inspected upstream; that is source evidence, **not** a build.

OpenWrt 25.12 uses `apk`, like modern Alpine, but OpenWrt's package
metadata, platform integration, `procd`, `ubus`, `UCI`, `netifd`, and
`sysupgrade` are not interchangeable with the existing Alpine services.
Its pinned release's kernel baseline must also be reconciled with the
Capsula Mini author's Linux 6.18.x A113X driver/DTS changes.

The Builder's device `openwrt-port.json` owns the proposed board port and
its fail-closed acceptance status. It deliberately does not create an
upstream `target/linux/amlogic` directory or claim an image recipe exists.
No toolchain, image, kernel, DTB or UBI build has yet been validated.

Run `python3 -m builder.build openwrt-plan --target capsula-mini-native`
to inspect the read-only source/port readiness report. The existing Alpine
`plan`, `rootfs` and `image` phases are unchanged. No OpenWrt installation,
flash or sysupgrade path is exposed.
