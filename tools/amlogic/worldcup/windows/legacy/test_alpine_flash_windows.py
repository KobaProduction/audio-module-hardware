"""Offline tests for write-stage safety; never access USB or NAND."""
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
import alpine_flash_windows as f


class AlpineFlashTests(TestCase):
    def test_plan_preserves_vendor_region(self):
        x = f.preflight()
        self.assertEqual(x["erase_from"], "0x1200000")
        self.assertEqual(x["erase_bytes"], 0x10000000 - 0x01200000)
        self.assertEqual(x["bootdelay_seconds"], 1)
        self.assertEqual(x["kernel_bytes"], 16715784)

    def test_exact_boot_environment_contract(self):
        settings = f.env_expected(16715784, 38596)
        self.assertEqual(settings["bootdelay"], "1")
        self.assertEqual(settings["bootcmd"], "run ka kb kc kd")
        self.assertEqual(settings["ka"], "setenv bootargs $" + "{ba}")
        self.assertIn("nand read 0x1000000 0x2b00000 0x20000", settings["kb"])
        self.assertIn("nand read 0x1080000 0x1200000 0x1000000", settings["kc"])

    def test_bulk_payload_limit_checked_before_usb(self):
        with patch.object(f, "vendor") as vendor:
            with self.assertRaises(f.FlashError):
                f.bulk("x" * 70)
            vendor.assert_not_called()

    def test_environment_words_fit_vendor_bulk(self):
        commands = []
        with patch.object(f, "bulk", side_effect=commands.append):
            f.set_long_environment("ba", f.env_expected(16715784, 38596)["ba"])
        self.assertGreater(len(commands), 1)
        self.assertTrue(commands[0].startswith("setenv ba "))
        for cmd in commands:
            self.assertLessEqual(len(("echo; " + cmd).encode("ascii")), 63)

    def test_flash_refuses_protected_addresses(self):
        with TemporaryDirectory() as d:
            file = Path(d) / "tiny.bin"
            file.write_bytes(b"\x01" * 2048)
            with patch.object(f, "ram_write") as ram:
                with self.assertRaises(f.FlashError):
                    f.flash_image(file, f.KERNEL_OFF - 2048, f.DTB_OFF, f.KERNEL_RAM, "kernel", Path(d))
                ram.assert_not_called()

    def test_flash_verification_detects_mismatch(self):
        with TemporaryDirectory() as d:
            file = Path(d) / "tiny.img"
            file.write_bytes(b"TEST" * 512)
            with patch.object(f, "ram_write"), patch.object(f, "bulk"), patch.object(f, "ram_read", return_value=b"\x00"*2048):
                with self.assertRaisesRegex(f.FlashError, "verify mismatch"):
                    f.flash_image(file, f.KERNEL_OFF, f.DTB_OFF, f.KERNEL_RAM, "kernel", Path(d))


if __name__ == "__main__":
    main()
