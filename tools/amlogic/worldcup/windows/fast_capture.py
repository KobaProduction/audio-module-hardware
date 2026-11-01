"""Fast read-only WorldCup loader capture by staggered concurrent identify probes.

No NAND operations. Windows Amlogic update.exe uses a separate process for
each call; this utility overlaps bounded, short-lived probes to reduce gaps.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
UPDATE = HERE / "update.exe"
LOG = HERE / "fast_capture.log"
EXPECTED_SHA256 = "F1DE686CF4FF770EE9DF0ACC2721E6A8195C81B556CA8894C04EB3BAC7CB2CAA"


def is_identified(stdout: bytes, stderr: bytes) -> bool:
    result = (stdout + b"\n" + stderr).decode("utf-8", errors="replace").lower()
    return "firmware version" in result and "err:" not in result and "[info]failed" not in result


def classify(stdout: bytes, stderr: bytes) -> str:
    result = (stdout + b"\n" + stderr).decode("utf-8", errors="replace").lower()
    if is_identified(stdout, stderr):
        return "identified"
    if "no [worldcup device]" in result or "can not find device" in result:
        return "not_present"
    if "err:" in result or "failed" in result:
        return "error"
    return "other"


def read_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def capture(
    executable: Path,
    timeout_seconds: float = 300.0,
    interval_seconds: float = 0.07,
    inflight_limit: int = 4,
    probe_timeout_seconds: float = 5.0,
    log_file: Path = LOG,
) -> bool:
    if inflight_limit < 1 or inflight_limit > 8:
        raise ValueError("inflight_limit must be between 1 and 8")
    if interval_seconds < 0.02:
        raise ValueError("interval must be at least 20 ms")
    if timeout_seconds <= 0:
        raise ValueError("timeout must be positive")

    # A separate in-flight process may temporarily claim the USB interface.
    # Concurrency is intentionally bounded and stops upon first success.
    active: dict[subprocess.Popen[bytes], float] = {}
    stats = Counter()
    launched = 0
    started = time.monotonic()
    deadline = started + timeout_seconds
    next_launch = started
    next_report = started + 5
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with log_file.open("a", encoding="utf-8") as log:
            log.write(
                f"\nSTART {datetime.now(timezone.utc).isoformat()} "
                f"timeout={timeout_seconds} interval_ms={interval_seconds*1000:.0f} "
                f"inflight={inflight_limit}\n"
            )
            log.flush()
            print(
                f"FAST CAPTURE ACTIVE: {interval_seconds*1000:.0f}ms stagger, "
                f"{inflight_limit} concurrent read-only identify scans.",
                flush=True,
            )
            print("Disconnect and reconnect/power-cycle the speaker now.", flush=True)
            while time.monotonic() < deadline:
                now = time.monotonic()
                if len(active) < inflight_limit and now >= next_launch:
                    try:
                        proc = subprocess.Popen(
                            [str(executable), "identify", "7"],
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
                    except OSError as exc:
                        log.write(f"PROCESS_LAUNCH_ERROR {exc}\n")
                        print(f"ERROR: cannot start update.exe: {exc}", flush=True)
                        return False
                    active[proc] = now
                    launched += 1
                    next_launch = now + interval_seconds

                for proc, begin in list(active.items()):
                    if proc.poll() is None:
                        if now - begin > probe_timeout_seconds:
                            proc.kill()
                            proc.communicate()
                            del active[proc]
                            stats["timeout"] += 1
                        continue
                    out, err = proc.communicate()
                    del active[proc]
                    kind = classify(out, err)
                    stats[kind] += 1
                    if kind == "identified":
                        msg = (out + b"\n" + err).decode("utf-8", errors="replace")
                        log.write(f"SUCCESS after={now-started:.3f}s probes={launched}\n{msg}\n")
                        log.flush()
                        print("WORLD CUP IDENTIFIED:", msg.strip(), flush=True)
                        return True
                    if kind in ("error", "other") and stats[kind] <= 3:
                        log.write(
                            f"probe={launched} kind={kind} rc={proc.returncode} "
                            f"output={(out+err).decode('utf-8',errors='replace')[:300]!r}\n"
                        )

                if now >= next_report:
                    summary = " ".join(f"{k}={v}" for k, v in sorted(stats.items()))
                    print(
                        f"Scanning... elapsed={now-started:.0f}s probes={launched} "
                        f"active={len(active)} {summary}",
                        flush=True,
                    )
                    next_report = now + 5
                time.sleep(0.005)

            log.write(f"TIMEOUT probes={launched} stats={dict(stats)}\n")
            print(f"TIMEOUT: No device captured. Probes={launched}.", flush=True)
            return False
    finally:
        for proc in active:
            if proc.poll() is None:
                proc.kill()
            proc.communicate()


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast read-only Amlogic WorldCup capture.")
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--interval-ms", type=float, default=70)
    parser.add_argument("--parallel", type=int, default=4)
    parser.add_argument("--probe-timeout", type=float, default=5)
    args = parser.parse_args()
    if not UPDATE.is_file():
        print(f"ERROR: update.exe missing: {UPDATE}", file=sys.stderr)
        return 2
    digest = read_file_hash(UPDATE)
    if digest != EXPECTED_SHA256:
        print(f"ERROR: update.exe SHA-256 changed: {digest}", file=sys.stderr)
        return 2
    try:
        succeeded = capture(
            executable=UPDATE,
            timeout_seconds=args.timeout,
            interval_seconds=args.interval_ms / 1000,
            inflight_limit=args.parallel,
            probe_timeout_seconds=args.probe_timeout,
        )
        return 0 if succeeded else 1
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
