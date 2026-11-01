# Audio Module HAL contract — v1

HAL is an API boundary, not a replacement for Linux drivers.
Current implementation is a BUILD-HOST compiler for declarative
device capabilities. Future runtime adapters belong to existing
Linux subsystems, instead of hardcoded input/event or GPIO numbers.

Key division:

- Kernel: drivers and standard device APIs (ALSA, evdev, IIO, LED class,
  DRM/KMS/framebuffer, GPIO chardev, hwmon, power_supply).
- Firmware: reusable HAL runtime support, network managers, audio
  services, and optional diagnostic executables. Components are selected,
  not installed globally.
- Builder: device/variant declarations, physical wiring/connector
  mapping, enabled firmware components, and exported capabilities.
- Application: consumer of the versioned HAL contract. It must gracefully
  handle absent/unknown/offline capabilities and subscribe to changes.
- Tools: opt-in diagnostics using the same API as Application.
  Diagnostics are not required to boot or play audio.

hal/manifest.py validates and compiles device declarations.
Builder writes /usr/share/audio-module/capabilities-v1.json in rootfs.
The descriptor has origin=builder-declared and runtime_verified=false.
Do not describe this static file as proof that hardware is operational.

Do not add Python runtime to Alpine to run this build-host compiler.
A small native runtime library/daemon can be selected later, after
its IPC/security contracts are agreed. JSON stays language-neutral.

See docs/HAL_CONTRACT.md.
