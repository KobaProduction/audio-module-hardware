"""Offline tests: no USB device required; never issue NAND operations."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import win_flash as flash


class FakeReadBackend:
    def __init__(self, short_name: str | None = None):
        self.short_name = short_name
        self.detected = False

    def find_device(self, seconds: float) -> None:
        self.detected = True

    def read_partition(self, name: str, length: int, output: Path) -> None:
        actual = length // 2 if name == self.short_name else length
        output.write_bytes(b"A" * actual)

    def read_flash_region(self, address: int, length: int, output: Path) -> None:
        output.write_bytes(b"B" * length)


class WindowsPortTests(unittest.TestCase):
    def test_bulk_command_prefix_and_bound(self):
        self.assertEqual(
            flash.bulk_payload("nand read 0x1080000 0x300000 0x100000"),
            "echo; nand read 0x1080000 0x300000 0x100000",
        )
        with self.assertRaises(flash.FlashToolError):
            flash.bulk_payload("x" * 100)

    def test_identify_does_not_trust_vendor_return_code(self):
        self.assertTrue(flash.usb_response_is_identified("Firmware version: 1.0"))
        self.assertFalse(flash.usb_response_is_identified("failed"))
        self.assertFalse(flash.usb_response_is_identified("err: Firmware version 0"))
        self.assertTrue(flash.usb_response_is_error("[INFO]Failed test"))

    def test_vendor_image_header(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "Image"
            data = bytearray(64)
            data[8:16] = (0x80000).to_bytes(8, "little")
            data[56:60] = b"ARM" + bytes([0x64])
            image.write_bytes(data)
            valid, message = flash.validate_image(image)
            self.assertTrue(valid, message)
            data[56:60] = bytes(4)
            image.write_bytes(data)
            valid, _ = flash.validate_image(image)
            self.assertFalse(valid)

    def test_requires_windows_executable(self):
        with TemporaryDirectory() as d:
            not_windows = Path(d) / "update.exe"
            not_windows.write_bytes(b"\x7fELF" + b"\0" * 30)
            with self.assertRaises(flash.FlashToolError):
                flash.WindowsUpdateBackend(not_windows)

    def test_manifest_size_and_hash_verification(self):
        with TemporaryDirectory() as d:
            path = Path(d)
            self.assertEqual(
                flash.result_for_dump("data", 0x40000, path / "absent").status,
                "missing",
            )
            file = path / "data.bin"
            file.write_bytes(b"\0" * 0x20000)
            self.assertEqual(
                flash.result_for_dump("data", 0x40000, file).status,
                "short-bad-blocks-unverified",
            )

    def test_complete_mock_backup_then_tamper(self):
        with TemporaryDirectory() as d:
            fake = FakeReadBackend()
            with (
                patch.object(flash, "BACKUP_ROOT", Path(d) / "backups"),
                patch.object(flash, "STOCK_PARTS", (("bootloader", 0x20000), ("data", 0x20000))),
                patch.object(flash, "RESERVED", (("bbt", 0x280000, 0x20000),)),
            ):
                target = flash.backup(fake, "my-board", 0.1)
                self.assertTrue(fake.detected)
                manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["status"], "complete-sizes-only")
                self.assertTrue(flash.verify_backup(target))
                with (target / "data.bin").open("r+b") as f:
                    f.write(b"BAD")
                self.assertFalse(flash.verify_backup(target))

    def test_short_backup_never_marked_complete(self):
        with TemporaryDirectory() as d:
            fake = FakeReadBackend(short_name="data")
            with (
                patch.object(flash, "BACKUP_ROOT", Path(d) / "backups"),
                patch.object(flash, "STOCK_PARTS", (("data", 0x40000),)),
                patch.object(flash, "RESERVED", ()),
            ):
                target = flash.backup(fake, "my-board", 0.1)
                manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["status"], "INCOMPLETE")
                self.assertFalse(flash.verify_backup(target))

    def test_invalid_board_name(self):
        with TemporaryDirectory() as d:
            with patch.object(flash, "BACKUP_ROOT", Path(d) / "backups"):
                with self.assertRaises(flash.FlashToolError):
                    flash.backup(FakeReadBackend(), "../escape", 1)


if __name__ == "__main__":
    unittest.main()
