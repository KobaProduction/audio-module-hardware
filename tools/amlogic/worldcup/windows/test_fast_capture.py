"""Offline unit tests of fast read-only USB capture."""
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import fast_capture as fc


class FakeProcess:
    def __init__(self, output: bytes, returncode: int = 0):
        self.stdout = output
        self.stderr = b""
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def communicate(self):
        return (self.stdout, self.stderr)

    def kill(self):
        self.returncode = -9


class FastCaptureTests(unittest.TestCase):
    def test_output_classification(self):
        self.assertTrue(fc.is_identified(b"Firmware version: v2", b""))
        self.assertFalse(fc.is_identified(b"Firmware version: x\nERR: failed", b""))
        self.assertEqual(fc.classify(b"No [WorldCup Device] device after scan", b""), "not_present")

    def test_detect_success_and_clean_exit(self):
        responses = [
            FakeProcess(b"No [WorldCup Device] device after scan", -1020),
            FakeProcess(b"Firmware version: v2"),
        ]
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(fc.subprocess, "Popen", side_effect=responses) as called:
                detected = fc.capture(
                    Path("dummy.exe"),
                    timeout_seconds=1,
                    interval_seconds=0.02,
                    inflight_limit=2,
                    log_file=Path(temp)/"log",
                )
                self.assertTrue(detected)
                self.assertGreaterEqual(called.call_count, 2)

    def test_invalid_params(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                fc.capture(Path("x"), interval_seconds=0, log_file=Path(temp)/"log")
            with self.assertRaises(ValueError):
                fc.capture(Path("x"), inflight_limit=100, log_file=Path(temp)/"log")


if __name__ == "__main__":
    unittest.main()
