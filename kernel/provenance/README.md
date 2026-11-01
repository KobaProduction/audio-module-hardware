# Capsula Mini A113X author source provenance

Kernel support was developed in the upstream Git tree by comp18man and
other upstream authors. It is source code, not an opaque firmware image.
This repository builds a pinned Git commit from that source under its
kernel component. No 2+ GiB duplicate of Linux is committed here.

The comp18man-a113x-delta.json file catalogs 246 paths changed relative to
the Linux 6.18.56 stable merge base, including each Git blob OID.
The changed source code is retrieved as the pinned Linux tree and built.

Actual driver ownership belongs to the kernel tree, including:
- drivers/auxdisplay/: seven-segment indicator class and display handling
- drivers/input/keyboard/csk05t.c: touch-button controller
- drivers/iio/light/bh1730.c: ambient light sensor
- drivers/leds/leds-is31fl32xx.c: RGB LED controller
- sound/soc/codecs/ntp8918.c: amplifier codec
- sound/soc/meson/axg-pdm.c: microphone input
- drivers/net/wireless/amlogic/w1/: W1 Wi-Fi stack, RF tables
- drivers/bluetooth/hci_aml.c: Bluetooth
- drivers/mtd/nand/raw/: NAND support
- Documentation/devicetree/bindings/: hardware bindings

The original Capsula Mini DTS stays in the kernel source tree, as Linux
requires. Choosing that DTS for the board and specifying variant differences
belongs to Builder alone. The original marusia_mini_defconfig is kernel
source; Builder selects it.

This inventory is not a license grant for vendor radio blobs and RF data.
Their individual redistributability needs review. The comparison base is
a Linux stable merge point, not a complete attribution history.
