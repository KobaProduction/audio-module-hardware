"""No device access or real serial/MAC data in these fixtures."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zlib

from uboot.env_audit import audit_environment, EnvironmentAuditError


def make_slot(entries: dict[str, str]) -> bytes:
    data = b"\0".join(
        name.encode() + b"=" + val.encode() for name, val in entries.items()
    ) + b"\0\0"
    payload = data + b"\xff" * (65536 - 4 - len(data))
    return (zlib.crc32(payload) & 0xffffffff).to_bytes(4, "little") + payload


def make_reserved(left: dict[str, str], right: dict[str, str]) -> bytes:
    out = bytearray(b"\xff" * (4 * 131072))
    out[131072:131072 + 65536] = make_slot(left)
    out[262144:262144 + 65536] = make_slot(right)
    return bytes(out)


class EnvironmentTests(unittest.TestCase):
    def test_two_valid_copies_with_mac_conflict(self):
        data = make_reserved(
            {"serial": "TEST-FICTIONAL-001", "ethaddr": "02:aa:aa:aa:aa:01"},
            {"ethaddr": "02:aa:aa:aa:aa:02"},
        )
        report = audit_environment(data)
        self.assertEqual(report["crc_valid_block_count"], 2)
        self.assertFalse(report["identifier_checks"]["ethaddr"]["distinct_copy_values_agree"])
        self.assertEqual(report["identifier_checks"]["serial"]["copies_with_nonempty_key"], 1)
        self.assertFalse(report["identifier_checks"]["ethaddr"]["authoritative_active_copy_proven"])
        self.assertNotIn("TEST-FICTIONAL-001", str(report))
        self.assertNotIn("02:aa:aa", str(report))

    def test_corrupted_crc_rejects_copy(self):
        data = bytearray(make_reserved({"serial": "X"}, {"serial": "Y"}))
        data[131072 + 15] ^= 0x10
        report = audit_environment(bytes(data))
        self.assertEqual(report["crc_valid_block_count"], 1)

    def test_identical_copies_do_not_prove_active_bootloader_selection(self):
        data = make_reserved({"serial": "TEST"}, {"serial": "TEST"})
        report = audit_environment(data)
        self.assertTrue(report["identifier_checks"]["serial"]["distinct_copy_values_agree"])
        self.assertFalse(report["identifier_checks"]["serial"]["authoritative_active_copy_proven"])

    def test_reject_unbounded_dump(self):
        with self.assertRaises(EnvironmentAuditError):
            audit_environment(b"0" * (16 * 1024 * 1024 + 1))

    def test_offline_cli_never_prints_values(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "env.bin"
            source.write_bytes(make_reserved({"serial": "SECRET-TEST-IDENTIFIER"},
                                             {"ethaddr": "02:aa:aa:aa:aa:02"}))
            result = subprocess.run(
                [sys.executable, "-m", "uboot.env_audit", "--file", str(source)],
                capture_output=True, text=True, timeout=10, check=True,
            )
            self.assertNotIn("SECRET-TEST-IDENTIFIER", result.stdout)
            self.assertIn('"identifiers_exposed": false', result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
