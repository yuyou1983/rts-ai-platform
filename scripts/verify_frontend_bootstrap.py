#!/usr/bin/env python3
"""Verify the Godot Start Game local backend bootstrap.

Runs the Godot headless bootstrap test multiple times sequentially,
verifying that:
  1. Each run passes (entities + fog-of-war received).
  2. Both ports (50051, 8080) are closed after each owned run.
  3. Pre-existing external services are not duplicated or terminated.

Usage:
  python3 scripts/verify_frontend_bootstrap.py --runs 3 --require-cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GODOT = os.environ.get("GODOT_BIN", "/Applications/Godot.app/Contents/MacOS/Godot")
GODOT_PATH = str(ROOT / "godot")
TEST_SCRIPT = "scripts/test_start_game_bootstrap.gd"
HELPER_SCRIPT = str(ROOT / "godot" / "scripts" / "run_frontend_backend.sh")
OUTPUT_FILE = str(ROOT / "harness" / "output" / "godot" / "bootstrap-runs.json")
GRPC_PORT = 50051
HTTP_PORT = 8080


def port_open(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except (OSError, ConnectionRefusedError):
        return False
    finally:
        s.close()


def kill_port_processes(port: int) -> None:
    """Kill any process listening on the given port."""
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{port}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        pids = result.stdout.strip().split()
        for pid in pids:
            if pid:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError):
                    pass
        if pids:
            time.sleep(1)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def ensure_ports_closed() -> bool:
    """Ensure both ports are closed, killing stragglers if needed."""
    for port in (GRPC_PORT, HTTP_PORT):
        if port_open(port):
            kill_port_processes(port)
    time.sleep(0.5)
    return not port_open(GRPC_PORT) and not port_open(HTTP_PORT)


def run_godot_test(log_file: str) -> tuple[bool, str]:
    """Run the Godot bootstrap test and return (passed, output)."""
    try:
        result = subprocess.run(
            [GODOT, "--headless", "--log-file", log_file,
             "--path", GODOT_PATH, "--script", TEST_SCRIPT],
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout + result.stderr
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT"
    except FileNotFoundError:
        return False, f"Godot binary not found: {GODOT}"


def start_external_backend() -> subprocess.Popen | None:
    """Start the backend as an external service (not owned by Godot)."""
    # Start the helper script in the background (no parent PID monitoring)
    try:
        proc = subprocess.Popen(
            ["bash", HELPER_SCRIPT, str(GRPC_PORT), str(HTTP_PORT), "0"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return None
    # Wait for readiness
    for _ in range(40):
        if port_open(HTTP_PORT):
            return proc
        time.sleep(0.25)
    proc.terminate()
    return None


def stop_external_backend(proc: subprocess.Popen) -> None:
    """Stop the externally started backend."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify Godot Start Game local backend bootstrap"
    )
    parser.add_argument(
        "--runs", type=int, default=3,
        help="Number of sequential clean-start runs (default: 3)",
    )
    parser.add_argument(
        "--require-cleanup", action="store_true",
        help="Fail if ports remain open after each owned run",
    )
    parser.add_argument(
        "--test-external", action="store_true", default=True,
        help="Also test external-service preservation (default: True)",
    )
    args = parser.parse_args()

    results: list[dict] = []
    all_passed = True

    # ── Clean-start runs ──
    for i in range(args.runs):
        run_id = f"clean-start-{i + 1}"
        print(f"\n=== Run {run_id} ===")

        # Ensure ports are closed before each run
        if not ensure_ports_closed():
            print(f"  FAIL: could not close ports before {run_id}")
            results.append({
                "run_id": run_id,
                "type": "clean-start",
                "passed": False,
                "reason": "ports not closed before run",
                "ports_closed_before": False,
                "ports_closed_after": False,
            })
            all_passed = False
            continue

        log_file = f"/tmp/rts-verify-run-{i + 1}.log"
        passed, output = run_godot_test(log_file)

        # Wait for cleanup
        time.sleep(2)
        ports_after = not port_open(GRPC_PORT) and not port_open(HTTP_PORT)

        if args.require_cleanup and not ports_after:
            print(f"  FAIL: ports not closed after {run_id}")
            # Kill stragglers
            ensure_ports_closed()
            all_passed = False
        elif not passed:
            print(f"  FAIL: Godot test failed for {run_id}")
            all_passed = False
        else:
            print(f"  PASS: {run_id}")

        # Extract pass/fail line from output
        pass_line = ""
        for line in output.split("\n"):
            if "PASS:" in line or "FAIL:" in line:
                pass_line = line.strip()
                break

        results.append({
            "run_id": run_id,
            "type": "clean-start",
            "passed": passed and (ports_after or not args.require_cleanup),
            "reason": pass_line if passed else output[:200],
            "ports_closed_before": True,
            "ports_closed_after": ports_after,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    # ── External-service preservation test ──
    if args.test_external:
        run_id = "external-preservation"
        print(f"\n=== Run {run_id} ===")

        # Ensure ports are closed first
        ensure_ports_closed()

        # Start external backend
        ext_proc = start_external_backend()
        if ext_proc is None:
            print(f"  FAIL: could not start external backend for {run_id}")
            results.append({
                "run_id": run_id,
                "type": "external-preservation",
                "passed": False,
                "reason": "could not start external backend",
                "external_service_survived": False,
            })
            all_passed = False
        else:
            # Verify external services are up
            ext_ports_up = port_open(GRPC_PORT) and port_open(HTTP_PORT)
            if not ext_ports_up:
                print(f"  FAIL: external backend not ready for {run_id}")
                results.append({
                    "run_id": run_id,
                    "type": "external-preservation",
                    "passed": False,
                    "reason": "external backend not ready",
                    "external_service_survived": False,
                })
                all_passed = False
            else:
                # Run the Godot test — it should use the existing service
                log_file = "/tmp/rts-verify-external.log"
                passed, output = run_godot_test(log_file)
                time.sleep(2)

                # Check that external services survived
                ext_survived = port_open(GRPC_PORT) and port_open(HTTP_PORT)

                if passed and ext_survived:
                    print(f"  PASS: {run_id} (external services preserved)")
                else:
                    print(f"  FAIL: {run_id} (passed={passed}, survived={ext_survived})")
                    all_passed = False

                pass_line = ""
                for line in output.split("\n"):
                    if "PASS:" in line or "FAIL:" in line:
                        pass_line = line.strip()
                        break

                results.append({
                    "run_id": run_id,
                    "type": "external-preservation",
                    "passed": passed and ext_survived,
                    "reason": pass_line if passed else output[:200],
                    "external_service_started": True,
                    "external_service_survived": ext_survived,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            # Clean up external backend
            if ext_proc:
                stop_external_backend(ext_proc)
                time.sleep(1)

    # ── Ensure final cleanup ──
    ensure_ports_closed()

    # ── Write evidence ──
    evidence = {
        "test": "frontend-bootstrap",
        "godot_version": "4.6.2.stable.official",
        "grpc_port": GRPC_PORT,
        "http_port": HTTP_PORT,
        "runs": results,
        "all_passed": all_passed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
    Path(OUTPUT_FILE).write_text(json.dumps(evidence, indent=2) + "\n")
    print(f"\nEvidence written to {OUTPUT_FILE}")

    # ── Summary ──
    clean_runs = [r for r in results if r["type"] == "clean-start"]
    ext_runs = [r for r in results if r["type"] == "external-preservation"]
    print(f"\n=== Summary ===")
    print(f"Clean-start runs: {sum(1 for r in clean_runs if r['passed'])}/{len(clean_runs)} passed")
    print(f"External preservation: {sum(1 for r in ext_runs if r['passed'])}/{len(ext_runs)} passed")
    print(f"Overall: {'PASS' if all_passed else 'FAIL'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
