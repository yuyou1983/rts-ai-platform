"""Contract tests for the Godot Start Game local backend bootstrap.

These tests statically verify the structural and behavioural contracts that
the S1 acceptance criteria require.  They do not launch Godot or Python
services; they inspect the GDScript source, the shell helper, and the
verification harness for the properties that must hold for Start Game to own
local backend readiness safely.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GODOT = ROOT / "godot" / "scripts"
BRIDGE = GODOT / "grpc_bridge.gd"
GAME_VIEW = GODOT / "game_view.gd"
MAIN_MENU = GODOT / "main_menu.gd"
HELPER = GODOT / "run_frontend_backend.sh"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_frontend_bootstrap.py"
TEST_BOOTSTRAP = GODOT / "test_start_game_bootstrap.gd"


# ─── grpc_bridge.gd contracts ──────────────────────────────────


def test_bridge_has_bootstrap_toggle() -> None:
    """enable_local_bootstrap must be an @export so release builds can disable it."""
    text = BRIDGE.read_text(encoding="utf-8")
    assert re.search(r"@export\s+var\s+enable_local_bootstrap\s*:\s*bool", text), (
        "grpc_bridge.gd must @export var enable_local_bootstrap: bool"
    )


def test_bridge_has_bootstrap_failed_signal() -> None:
    """A bootstrap_failed signal must exist so the frontend can surface errors."""
    text = BRIDGE.read_text(encoding="utf-8")
    assert re.search(r"signal\s+bootstrap_failed\s*\(", text), (
        "grpc_bridge.gd must define signal bootstrap_failed(reason: String)"
    )


def test_bridge_uses_structured_process_api() -> None:
    """Must use OS.create_process with an argument array, not a shell string."""
    text = BRIDGE.read_text(encoding="utf-8")
    assert "OS.create_process" in text, (
        "grpc_bridge.gd must use OS.create_process for structured process launching"
    )
    # Must not use OS.execute with a command string containing user-controlled values
    # (OS.execute with shell=True is forbidden for user-input paths)
    assert not re.search(r'OS\.execute\s*\(\s*f?"', text), (
        "grpc_bridge.gd must not use OS.execute with string interpolation "
        "(shell concatenation risk)"
    )


def test_bridge_has_port_readiness_check() -> None:
    """Must check port readiness before retrying start_game."""
    text = BRIDGE.read_text(encoding="utf-8")
    assert "StreamPeerTCP" in text or "port_is_open" in text.lower() or "_is_port_open" in text, (
        "grpc_bridge.gd must perform a TCP port readiness check"
    )


def test_bridge_has_bounded_bootstrap_timeout() -> None:
    """Bootstrap must have a bounded timeout, not retry indefinitely."""
    text = BRIDGE.read_text(encoding="utf-8")
    # Must reference a timeout limit (msec or seconds)
    has_timeout = bool(
        re.search(r"max_wait_msec|_bootstrap_timeout|timeout_msec", text)
    )
    assert has_timeout, "grpc_bridge.gd must define a bounded bootstrap timeout"


def test_bridge_has_single_retry_guard() -> None:
    """Must retry start_game only once; no indefinite retry loop."""
    text = BRIDGE.read_text(encoding="utf-8")
    # _bootstrap_retried flag prevents repeated bootstrap attempts
    assert "_bootstrap_retried" in text or "_bootstrap_attempted" in text, (
        "grpc_bridge.gd must guard against multiple bootstrap attempts"
    )


def test_bridge_cleans_up_owned_process() -> None:
    """_exit_tree must kill only the process this bridge owns."""
    text = BRIDGE.read_text(encoding="utf-8")
    assert re.search(r"func\s+_exit_tree\s*\(\s*\)\s*->\s*void", text), (
        "grpc_bridge.gd must define _exit_tree()"
    )
    # Must reference OS.kill or the owned pid cleanup
    assert "OS.kill" in text or "_owned_backend_pid" in text, (
        "grpc_bridge.gd must clean up the owned backend process on exit"
    )


def test_bridge_has_owned_pid_tracking() -> None:
    """Must track whether this process launched the helper."""
    text = BRIDGE.read_text(encoding="utf-8")
    assert "_owned_backend_pid" in text, (
        "grpc_bridge.gd must track the owned backend PID separately"
    )


# ─── game_view.gd contracts ─────────────────────────────────────


def test_game_view_connects_error_signals() -> None:
    """game_view must connect bootstrap_failed and/or connection_lost signals."""
    text = GAME_VIEW.read_text(encoding="utf-8")
    assert "bootstrap_failed" in text or "connection_lost" in text, (
        "game_view.gd must connect to bootstrap_failed or connection_lost"
    )


def test_game_view_has_error_overlay() -> None:
    """game_view must show a visible error state, not an empty GameView."""
    text = GAME_VIEW.read_text(encoding="utf-8")
    # Must have an error overlay or error label
    has_error = any(
        kw in text
        for kw in ("_error_overlay", "_error_label", "_show_error", "_backend_error")
    )
    assert has_error, (
        "game_view.gd must show a visible error state on backend failure"
    )


# ─── main_menu.gd contracts ─────────────────────────────────────


def test_main_menu_preserves_external_service_path() -> None:
    """main_menu must still change scene to game_view (external services path)."""
    text = MAIN_MENU.read_text(encoding="utf-8")
    assert "change_scene_to_file" in text, (
        "main_menu.gd must still change to game_view scene"
    )


# ─── run_frontend_backend.sh contracts ─────────────────────────


def test_helper_script_syntax_valid() -> None:
    """bash -n must pass on the helper script."""
    result = subprocess.run(
        ["bash", "-n", str(HELPER)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"bash -n failed: {result.stderr}"
    )


def test_helper_has_port_open_check() -> None:
    """Helper must check if ports are already in use (preserve external services)."""
    text = HELPER.read_text(encoding="utf-8")
    assert "port_open" in text, (
        "run_frontend_backend.sh must check port_open before starting services"
    )


def test_helper_has_cleanup_trap() -> None:
    """Helper must have a cleanup trap for owned services."""
    text = HELPER.read_text(encoding="utf-8")
    assert "trap" in text and "cleanup" in text, (
        "run_frontend_backend.sh must have a cleanup trap"
    )


def test_helper_has_parent_pid_monitoring() -> None:
    """Helper must monitor parent PID to clean up when the owning process exits."""
    text = HELPER.read_text(encoding="utf-8")
    assert "PARENT_PID" in text, (
        "run_frontend_backend.sh must monitor PARENT_PID for cleanup"
    )


def test_helper_does_not_use_eval() -> None:
    """Helper must not use eval or unsafe variable expansion."""
    text = HELPER.read_text(encoding="utf-8")
    assert "eval " not in text, (
        "run_frontend_backend.sh must not use eval"
    )


def test_helper_uses_argument_array_not_shell_string() -> None:
    """Helper args must be structured, not shell-concatenated."""
    text = HELPER.read_text(encoding="utf-8")
    # Ports and parent PID are passed as positional args, not concatenated
    assert '"$1"' in text or '"$2"' in text or '"$3"' in text, (
        "run_frontend_backend.sh must use positional arguments, not shell concatenation"
    )


# ─── verify_frontend_bootstrap.py contracts ────────────────────


def test_verify_script_exists() -> None:
    """The verification harness script must exist."""
    assert VERIFY_SCRIPT.exists(), (
        f"scripts/verify_frontend_bootstrap.py must exist at {VERIFY_SCRIPT}"
    )


def test_verify_script_has_runs_argument() -> None:
    """Must accept --runs argument for sequential clean-start verification."""
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "--runs" in text, (
        "verify_frontend_bootstrap.py must accept --runs argument"
    )


def test_verify_script_has_require_cleanup_argument() -> None:
    """Must accept --require-cleanup to verify ports are closed after each run."""
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "--require-cleanup" in text, (
        "verify_frontend_bootstrap.py must accept --require-cleanup argument"
    )


def test_verify_script_is_valid_python() -> None:
    """Must be syntactically valid Python."""
    text = VERIFY_SCRIPT.read_text(encoding="utf-8")
    ast.parse(text)


# ─── test_start_game_bootstrap.gd contracts ────────────────────


def test_bootstrap_test_checks_entities_and_fog() -> None:
    """The Godot bootstrap test must verify non-empty entities and fog-of-war."""
    text = TEST_BOOTSTRAP.read_text(encoding="utf-8")
    assert "entities" in text, (
        "test_start_game_bootstrap.gd must check entities"
    )
    assert "fog" in text, (
        "test_start_game_bootstrap.gd must check fog-of-war data"
    )


def test_bootstrap_test_has_timeout() -> None:
    """The bootstrap test must have a timeout to prevent hanging."""
    text = TEST_BOOTSTRAP.read_text(encoding="utf-8")
    assert "timeout" in text.lower() or "Timer" in text, (
        "test_start_game_bootstrap.gd must have a timeout"
    )


# ─── Evidence output contract ──────────────────────────────────


def test_evidence_output_path_exists() -> None:
    """The bootstrap-runs.json evidence output path must be a valid directory."""
    evidence_dir = ROOT / "harness" / "output" / "godot"
    assert evidence_dir.exists(), (
        f"harness/output/godot/ must exist for bootstrap-runs.json evidence"
    )


if __name__ == "__main__":
    sys.exit(0)
