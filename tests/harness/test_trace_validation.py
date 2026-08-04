from __future__ import annotations

import json
from pathlib import Path

from harness.trace.validate_traces import validate_file


def _write_trial(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data) + "\n")


def _base_trial() -> dict:
    return {
        "schema_version": 2,
        "task_id": "trace-001",
        "task_description": "fix godot vfx alignment",
        "skill_name": "godot-specialist",
        "skill_version": "0.1.0",
        "candidate_id": "",
        "agent_run_id": "run-001",
        "task_fixture_id": "godot-vfx/sc1-resource-alignment",
        "baseline_or_candidate": "baseline",
        "strategy_label": "A",
        "outcome": "pass",
        "skill_md_read": True,
        "primary_script_called": False,
        "primary_action_invoked": True,
        "tool_calls": [{"tool": "Read", "args_summary": ".agents/skills/godot-specialist/SKILL.md"}],
        "validation_commands_run": ["python3 scripts/verify_presentation_scene.py"],
        "validation_results": ["pass"],
        "validation_exit_codes": [0],
        "validation_stdout_hashes": ["sha256:abc"],
        "validation_stderr_summaries": [""],
        "functional_verification": "pass",
        "failure_log_summary": "",
        "token_count": 1000,
        "turn_count": 4,
        "duration_seconds": 12.5,
        "touched_files": ["harness/skills/tasks/godot-vfx/sc1-resource-alignment.json"],
        "silent_bypass_detected": False,
        "silent_bypass_details": [],
        "timestamp": "2026-06-08T00:00:00+00:00",
    }


def test_strict_trace_accepts_complete_v2_record(tmp_path):
    path = tmp_path / "trials.jsonl"
    _write_trial(path, _base_trial())
    assert validate_file(path, strict=True) == []


def test_strict_trace_infers_missing_skill_read_as_bypass(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_trial()
    trial["skill_md_read"] = False
    trial["silent_bypass_detected"] = False
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("silent_bypass_inferred" in issue for issue in issues)


def test_strict_trace_infers_missing_validation_as_bypass(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_trial()
    trial["validation_commands_run"] = []
    trial["validation_results"] = []
    trial["silent_bypass_detected"] = False
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("validation_commands_run empty" in issue for issue in issues)


# ─── Candidate-aware strict validation ──────────────────────────


def _base_candidate_trial() -> dict:
    """A fully valid candidate trial that passes all strict checks."""
    trial = _base_trial()
    trial["baseline_or_candidate"] = "candidate"
    trial["candidate_id"] = "cand-001"
    trial["agent_run_id"] = "run-001"
    trial["task_fixture_id"] = "tasks/godot-vfx/sc1-resource-alignment"
    trial["skill_md_read"] = True
    trial["primary_action_invoked"] = True
    trial["validation_commands_run"] = ["python3 scripts/verify_presentation_scene.py"]
    trial["validation_results"] = ["pass"]
    trial["validation_exit_codes"] = [0]
    trial["functional_verification"] = "pass"
    trial["outcome"] = "pass"
    return trial


def test_strict_candidate_trial_passes_when_complete(tmp_path):
    path = tmp_path / "trials.jsonl"
    _write_trial(path, _base_candidate_trial())
    assert validate_file(path, strict=True) == []


def test_strict_baseline_trial_exempt_from_candidate_checks(tmp_path):
    """Baseline trials must not be flagged by candidate-only rules."""
    path = tmp_path / "trials.jsonl"
    trial = _base_trial()  # baseline, candidate_id=""
    _write_trial(path, trial)
    # baseline is exempt: no candidate_* issues should appear
    issues = validate_file(path, strict=True)
    assert not any("candidate trial" in i for i in issues)


def test_strict_candidate_trial_missing_candidate_id(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_candidate_trial()
    trial["candidate_id"] = ""
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("missing non-empty candidate_id" in i for i in issues)


def test_strict_candidate_trial_missing_agent_run_id(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_candidate_trial()
    trial["agent_run_id"] = ""
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("missing non-empty agent_run_id" in i for i in issues)


def test_strict_candidate_trial_missing_skill_md_read(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_candidate_trial()
    trial["skill_md_read"] = False
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("did not read SKILL.md" in i for i in issues)


def test_strict_candidate_trial_missing_validation_exit_codes(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_candidate_trial()
    trial["validation_exit_codes"] = []
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("recorded no validation exit codes" in i for i in issues)


def test_strict_candidate_trial_outcome_not_pass(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_candidate_trial()
    trial["outcome"] = "fail"
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("candidate trial outcome != pass" in i for i in issues)


def test_strict_candidate_trial_functional_verification_not_pass(tmp_path):
    path = tmp_path / "trials.jsonl"
    trial = _base_candidate_trial()
    trial["functional_verification"] = "skip"
    _write_trial(path, trial)
    issues = validate_file(path, strict=True)
    assert any("functional_verification != pass" in i for i in issues)
