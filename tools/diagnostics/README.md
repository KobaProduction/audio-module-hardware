# Optional HAL diagnostics

These programs consume the same HAL contract that Application will use.
They are not separate hardware drivers with hard-coded GPIO and event indexes.

- inspect_capabilities.py is a host/developer Python read-only inspector.
  It can match the actual Linux IIO BH1730 and Hynitron CSK05T device names
  recorded in the author's pinned kernel sources. All unproven capabilities
  remain UNKNOWN, including physical microphone count and LED ring support.
- Other diagnostics (ALSA capture/playback test, speaker channels, buttons,
  display text, LEDs) require verified native HAL adapters before they
  are safe portable tools.

Nothing is installed into the Alpine image by default. Python is NOT
added to the target just for host-side diagnostics.
