# Original Capsula Mini Linux distribution: source ownership

This inventory distinguishes three evidence classes:
1. Compilable third-party sources that can be pinned, attributed and built.
2. Shell helpers whose text was visible on the running Alpine image, but
   whose redistribution license is not established yet.
3. Opaque vendor binaries / device-specific NAND images whose source,
   licensing or reconstruction is not yet available.

Do not copy unknown-license userland code or factory images into public Git
just because they are extractable from a working speaker.

## Linux kernel sources

Source: https://github.com/comp18man/vk-capsula-mini-a113x-linux
Pinned revision: 8d850405b091aaf217f8bb1bbdf22852f5cdb61e.
A complete machine-readable index of 246 paths changed from Linux 6.18.56
is in kernel/provenance/comp18man-a113x-delta.json.

| Driver / subsystem | Original Linux source | Ownership |
| --- | --- | --- |
| Four-digit, seven-segment clock display | drivers/auxdisplay/seg-led-class.c, line-display.c, led bindings | Kernel, selected by Builder DTS |
| Touch sensors | drivers/input/keyboard/csk05t.c | Kernel, configured by Builder DTS |
| Ambient light | drivers/iio/light/bh1730.c | Kernel, configured by Builder DTS |
| RGB ring/panel LEDs | drivers/leds/leds-is31fl32xx.c | Kernel, configured by Builder DTS |
| Speaker amplifier | sound/soc/codecs/ntp8918.c | Kernel, configured by Builder audio wiring |
| Digital microphones | sound/soc/meson/axg-pdm.c | Kernel, configured by Builder audio wiring |
| W1 Wi-Fi chipset and RF tables | drivers/net/wireless/amlogic/w1/ | Kernel, selected by Builder modules; closed parts reviewed separately |
| Bluetooth HCI | drivers/bluetooth/hci_aml.c | Kernel, selected by Builder config |
| NAND/UBI adjustments | drivers/mtd/nand/raw/ | Kernel; NAND geometry in Builder |
| Capsula Mini physical wiring | Upstream: `arch/arm64/boot/dts/amlogic/meson-axg-s420-marusia-mini.dts`; built from the source-patched `meson-axg-capsula-mini.dts` | DTS source/patch in Kernel; selection in Builder |

Kernel source remains an immutable Git dependency, not a source-less image
or an independent duplicate of all 2+ GiB of Linux. Git history retains
actual authorship and individual source licenses.

## User-space utilities observed on the running Alpine

The following are **observations**, not claims that source is licensed or
that each tool already has a complete new implementation.

| Existing file or function | Intended owner | Next action |
| --- | --- | --- |
| /usr/local/bin/clockdisp (shell) | Tools / optional display diagnostic; board wiring remains Builder data | If retained, use the generic Linux segment-display interface. Runtime display behavior belongs to Application / future HAL provider, not Builder executable logic |
| /usr/local/bin/lightmon (shell) | Tools / optional read-only sensor diagnostic | Use discovered IIO attributes; Application owns runtime sensor responses via the future HAL interface |
| /usr/local/bin/touch-keys (shell) | Tools / optional read-only input diagnostic | Discover input devices; Application owns event/action processing via the future HAL interface |
| /usr/local/bin/ringled (static AArch64 ELF) | Private historical reference only; excluded from this device | No ring capability is selected or planned for Capsula Mini; do not bundle or reimplement without a new explicit requirement |
| /usr/local/bin/mic-speaker-test (shell) | Tools / optional ALSA diagnostic, board mapping via Builder | Application owns production audio routing and streams; tools must not become runtime dependencies |
| /usr/local/bin/bt-pair (shell) | Firmware / optional Bluetooth component | Reimplement generic BlueZ pairing configuration |
| /usr/local/bin/wifi-connect-iwd (shell) | Firmware / optional Wi-Fi component | Reimplement generic iwd provisioning, never commit credentials |
| /usr/local/bin/offline-speak (shell) | Application / future optional TTS pipeline | No TTS engine or voice pipeline is selected; Firmware may package an approved generic dependency later |
| /usr/local/bin/check-secure.sh (shell) | Firmware / security checks | Port generic system/security status policy |

System services and configuration:
- OpenRC, SSH, iwd, BlueZ, ALSA, dnsmasq and other generic package/service
  definitions belong in firmware/alpine/components.json.
- Generic USB NCM/ACM implementation belongs to Firmware; Capsula Mini USB
  manufacturer/product/serial/MAC values belong in its Builder overlay.
- The WPA3/SAE workaround is a board/driver-specific Builder override.
- USB static IP, local hostname, NAND fstab, bootloader-retain policy,
  flash geometry and UBI offsets are Builder device data, not Firmware.
- Future optional features are selected in Builder, not removed by copying
  and editing complete OS images per board.

## Bootloader, blob and tool custody

| Original artifact | Location/owner | State |
| --- | --- | --- |
| Bootloader NAND partition, source unknown | uboot/ | Retain factory bootloader; private backup only |
| TPL/DDR initialization, source unknown | uboot/ | Private backup; research upstream source/reverse |
| Reserved/BBT/keys/calibration | Restricted local backups | Not source files; never publish, overwrite or share |
| Firmware/eq_8918.bin and Wi-Fi RF binary parts | Linux source tree firmware/ and build packaging | Verify source, individual license and redistributability |
| Author Linux flasher.sh | tools/amlogic/worldcup historical reference | Original file kept offline pending rights and transport decomposition |
| Proprietary Amlogic update/update.exe/DLL | tools/amlogic/worldcup backend dependency | No source or redistribution grant verified; exclude executables |
| User-created Windows WorldCup utilities | tools/amlogic/worldcup/windows/ | Source imported; generic transport not yet complete |
| Alpine rootfs.ubi and kernel Image from author's release | Build inputs reference only | Do NOT commit opaque prebuilt release in our source tree |

## Acceptance boundaries

The classification is grounded in upstream sources, the original distribution
file list, and read-only observations of the running speaker. It does not
prove that scripts or binary content can be redistributed, that the full
kernel/U-Boot is buildable, or that a newly produced firmware boots.

Next steps:
- Validate the existing source-built kernel/DTB/modules and Alpine/UBI image on recoverable physical hardware before authorizing installation.
- Extract generic audio/network tool functionality into Firmware.
- Keep board wiring in Builder; implement optional diagnostics in Tools and device runtime behavior in Application, over the agreed HAL contract.
- Keep ring LED excluded; do not change the retained factory U-Boot without verified recovery and separate authorization.
- Integrate generic tool transport with validated Builder NAND profiles.

## HAL migration state

The contract for physical microphone/speaker counts, pixel vs segment
displays and detachable outputs is now documented under
docs/HAL_CONTRACT.md. Actual native Linux HAL adapters have NOT yet
been ported. The original ringled remains a private behavioral sample,
not a mandatory firmware asset. Builder excludes unimplemented ring
functions from the exported capability set.
