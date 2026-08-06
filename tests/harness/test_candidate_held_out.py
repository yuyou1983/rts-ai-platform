#!/usr/bin/env python3
"""Tests for candidate-aware held-out validation."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from harness.evolve.held_out import (
    HeldOutResult,
    candidate_id_for_patch,
    create_candidate_overlay,
    validate_held_out_candidate,
)
from harness.trace.schema import SkillTrial


def _write_suite(root: Path, skill_name: str = "fake-skill") -> list[str]:
    scenario_ids = ["held-out/fake/one", "held-out/fake/two"]
    suite_dir = root / skill_name
    suite_dir.mkdir(parents=True)
    suite = {
        "skill_name": skill_name,
        "scenarios": [
            {
                "id": scenario_id,
                "description": f"Exercise {scenario_id}",
                "validation_commands": ["python3 -c \"assert 2 + 2 == 4\""],
                "pass_criteria": "The command and fresh-agent evidence pass.",
            }
            for scenario_id in scenario_ids
        ],
    }
    (suite_dir / "suite.json").write_text(json.dumps(suite))
    return scenario_ids


def _candidate_trial(
    *,
    candidate_id: str,
    agent_run_id: str,
    fixture_id: str,
    skill_md_sha256: str,
    overlay_path: str = "",
) -> SkillTrial:
    return SkillTrial(
        task_id=fixture_id,
        task_description="Fresh held-out candidate run",
        skill_name="fake-skill",
        skill_version="0.1.0",
        candidate_id=candidate_id,
        agent_run_id=agent_run_id,
        task_fixture_id=fixture_id,
        baseline_or_candidate="candidate",
        strategy_label="held-out",
        skill_md_read=True,
        primary_action_invoked=True,
        tool_calls=[{
            "tool": "Read",
            "args_summary": str(
                (Path(overlay_path) / "fake-skill" / "SKILL.md").resolve()
            ),
        }],
        validation_commands_run=["python3 -c \"assert 2 + 2 == 4\""],
        validation_results=["pass"],
        validation_exit_codes=[0],
        validation_stdout_hashes=["sha256:stdout"],
        functional_verification="pass",
        token_count=100,
        turn_count=2,
        duration_seconds=1.5,
        outcome="pass",
        skill_md_sha256=skill_md_sha256,
        runner_provenance="codex/task/run-001",
        runner_output_hash="sha256:runner-output",
    )


def test_command_only_held_out_is_not_promotion_eligible():
    """Command-only validation may pass but must not be promotion-eligible."""
    result = HeldOutResult(
        passed=True,
        promotion_eligible=False,
        skill_name="test-skill",
        candidate_id="",
        scenario_results=[{"scenario": "cmd-only", "passed": True}],
        issues=["command-only validation is not promotion-eligible"],
    )
    assert result.passed is True
    assert result.promotion_eligible is False


def test_baseline_trial_cannot_validate_candidate():
    """A baseline trial cannot serve as candidate evidence."""
    result = HeldOutResult(
        passed=True,
        promotion_eligible=False,
        skill_name="test-skill",
        candidate_id="",
        scenario_results=[],
        issues=["baseline trial cannot validate candidate"],
    )
    assert result.promotion_eligible is False


def test_candidate_trial_requires_candidate_id():
    """A candidate trial must have a non-empty candidate_id."""
    result = validate_held_out_candidate(
        skill_name="test-skill",
        candidate_id="",
        agent_run_id="run-001",
    )
    assert result.promotion_eligible is False
    assert any("candidate_id" in issue for issue in result.issues)


def test_candidate_trial_requires_fresh_agent_run_id():
    """A candidate trial must have a non-empty agent_run_id."""
    result = validate_held_out_candidate(
        skill_name="test-skill",
        candidate_id="cand-001",
        agent_run_id="",
    )
    assert result.promotion_eligible is False
    assert any("agent_run_id" in issue for issue in result.issues)


def test_arbitrary_candidate_ids_cannot_become_promotion_eligible():
    result = validate_held_out_candidate(
        skill_name="code-review",
        candidate_id="fabricated-candidate",
        agent_run_id="fabricated-run",
    )

    assert result.promotion_eligible is False
    assert any("overlay" in issue.lower() for issue in result.issues)


def test_missing_held_out_suite_is_a_failed_validation(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    monkeypatch.setattr(held_out_mod, "HELD_OUT_DIR", tmp_path / "held_out")
    result = validate_held_out_candidate("missing-skill")

    assert result.passed is False
    assert result.promotion_eligible is False
    assert any("suite" in issue.lower() for issue in result.issues)


def test_training_fixture_cannot_be_reused_as_held_out():
    """Training fixture IDs cannot be used as held-out scenario IDs."""
    result = validate_held_out_candidate(
        skill_name="test-skill",
        candidate_id="cand-001",
        agent_run_id="run-001",
        training_fixture_ids=["tasks/godot-vfx/sc1-resource-alignment"],
        held_out_fixture_ids=["tasks/godot-vfx/sc1-resource-alignment"],
    )
    assert result.promotion_eligible is False
    assert any("training" in issue.lower() for issue in result.issues)


def test_candidate_overlay_creates_temporary_skill(tmp_path, monkeypatch):
    """create_candidate_overlay writes a temp SKILL.md with the patch appended."""
    import harness.evolve.held_out as held_out_mod

    # Build a fake skill directory under tmp_path
    skill_dir = tmp_path / ".agents" / "skills" / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Fake Skill\n\nprimary_action: write_file\n")

    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", tmp_path / ".agents" / "skills")

    overlay_path = held_out_mod.create_candidate_overlay("fake-skill", "## New Rule\nDo X.")
    overlay = Path(overlay_path)
    assert overlay.exists()
    overlay_md = (overlay / "fake-skill" / "SKILL.md").read_text()
    metadata = json.loads((overlay / ".candidate.json").read_text())
    assert "primary_action: write_file" in overlay_md
    assert "## Candidate Patch" in overlay_md
    assert "## New Rule" in overlay_md
    assert metadata["candidate_id"] == candidate_id_for_patch(
        "fake-skill", "## New Rule\nDo X."
    )
    assert metadata["skill_name"] == "fake-skill"
    assert metadata["skill_md_sha256"].startswith("sha256:")
    # The overlay must live outside the repository working tree (temp dir)
    assert not overlay.is_relative_to(REPO)


def test_candidate_overlay_raises_for_missing_skill(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", tmp_path / ".agents" / "skills")
    with pytest.raises(FileNotFoundError):
        held_out_mod.create_candidate_overlay("no-such-skill", "patch")


def test_candidate_evidence_must_cover_every_scenario(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Fake\nprimary_action: review\n")
    held_out_dir = tmp_path / "held-out"
    scenario_ids = _write_suite(held_out_dir)
    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(held_out_mod, "HELD_OUT_DIR", held_out_dir)

    patch_text = "Require three-axis findings."
    candidate_id = candidate_id_for_patch("fake-skill", patch_text)
    overlay_path = create_candidate_overlay("fake-skill", patch_text)
    metadata = json.loads((Path(overlay_path) / ".candidate.json").read_text())
    one_trial = _candidate_trial(
        candidate_id=candidate_id,
        agent_run_id="run-one",
        fixture_id=scenario_ids[0],
        skill_md_sha256=metadata["skill_md_sha256"],
        overlay_path=overlay_path,
    )

    result = validate_held_out_candidate(
        "fake-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=[one_trial],
    )

    assert result.passed is True
    assert result.promotion_eligible is False
    assert any(scenario_ids[1] in issue for issue in result.issues)


def test_exact_overlay_and_fresh_trials_are_promotion_eligible(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Fake\nprimary_action: review\n")
    held_out_dir = tmp_path / "held-out"
    scenario_ids = _write_suite(held_out_dir)
    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(held_out_mod, "HELD_OUT_DIR", held_out_dir)

    patch_text = "Require three-axis findings."
    candidate_id = candidate_id_for_patch("fake-skill", patch_text)
    overlay_path = create_candidate_overlay("fake-skill", patch_text)
    metadata = json.loads((Path(overlay_path) / ".candidate.json").read_text())
    trials = [
        _candidate_trial(
            candidate_id=candidate_id,
            agent_run_id=f"run-{index}",
            fixture_id=scenario_id,
            skill_md_sha256=metadata["skill_md_sha256"],
            overlay_path=overlay_path,
        )
        for index, scenario_id in enumerate(scenario_ids, 1)
    ]

    result = validate_held_out_candidate(
        "fake-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=trials,
    )

    assert result.passed is True
    assert result.promotion_eligible is True
    assert result.agent_run_ids == ["run-1", "run-2"]


def test_candidate_trial_identity_and_overlay_hash_must_match(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Fake\nprimary_action: review\n")
    held_out_dir = tmp_path / "held-out"
    scenario_ids = _write_suite(held_out_dir)
    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(held_out_mod, "HELD_OUT_DIR", held_out_dir)

    patch_text = "Require three-axis findings."
    candidate_id = candidate_id_for_patch("fake-skill", patch_text)
    overlay_path = create_candidate_overlay("fake-skill", patch_text)
    trials = [
        _candidate_trial(
            candidate_id="cand-from-another-patch",
            agent_run_id=f"run-{index}",
            fixture_id=scenario_id,
            skill_md_sha256="sha256:another-overlay",
            overlay_path=overlay_path,
        )
        for index, scenario_id in enumerate(scenario_ids, 1)
    ]

    result = validate_held_out_candidate(
        "fake-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=trials,
    )

    assert result.promotion_eligible is False
    assert any("candidate_id mismatch" in issue for issue in result.issues)
    assert any("skill_md_sha256 does not match" in issue for issue in result.issues)


def test_candidate_trials_require_unique_run_ids(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Fake\nprimary_action: review\n")
    held_out_dir = tmp_path / "held-out"
    scenario_ids = _write_suite(held_out_dir)
    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(held_out_mod, "HELD_OUT_DIR", held_out_dir)

    patch_text = "Require three-axis findings."
    candidate_id = candidate_id_for_patch("fake-skill", patch_text)
    overlay_path = create_candidate_overlay("fake-skill", patch_text)
    metadata = json.loads((Path(overlay_path) / ".candidate.json").read_text())
    trials = [
        _candidate_trial(
            candidate_id=candidate_id,
            agent_run_id="duplicate-run",
            fixture_id=scenario_id,
            skill_md_sha256=metadata["skill_md_sha256"],
            overlay_path=overlay_path,
        )
        for scenario_id in scenario_ids
    ]

    result = validate_held_out_candidate(
        "fake-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=trials,
    )

    assert result.promotion_eligible is False
    assert any("unique agent_run_id" in issue for issue in result.issues)


def test_candidate_trial_must_read_overlay_as_first_action(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Fake\nprimary_action: review\n")
    held_out_dir = tmp_path / "held-out"
    scenario_ids = _write_suite(held_out_dir)
    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(held_out_mod, "HELD_OUT_DIR", held_out_dir)

    patch_text = "Require three-axis findings."
    candidate_id = candidate_id_for_patch("fake-skill", patch_text)
    overlay_path = create_candidate_overlay("fake-skill", patch_text)
    metadata = json.loads((Path(overlay_path) / ".candidate.json").read_text())
    trials = [
        _candidate_trial(
            candidate_id=candidate_id,
            agent_run_id=f"run-{index}",
            fixture_id=scenario_id,
            skill_md_sha256=metadata["skill_md_sha256"],
            overlay_path=overlay_path,
        )
        for index, scenario_id in enumerate(scenario_ids, 1)
    ]
    trials[0].tool_calls[0]["args_summary"] = ".agents/skills/fake-skill/SKILL.md"

    result = validate_held_out_candidate(
        "fake-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=trials,
    )

    assert result.promotion_eligible is False
    assert any("first tool call" in issue for issue in result.issues)


def test_candidate_trial_must_match_expected_axis_verdicts(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "fake-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Fake\nprimary_action: review\n")
    held_out_dir = tmp_path / "held-out"
    scenario_ids = _write_suite(held_out_dir)
    suite_path = held_out_dir / "fake-skill" / "suite.json"
    suite = json.loads(suite_path.read_text())
    suite["scenarios"][0]["expected_findings"] = [{
        "axis": "Standards",
        "allowed_verdicts": ["FAIL", "CONCERNS"],
    }]
    suite["scenarios"][1]["expected_findings"] = [{
        "axis": "Specification",
        "allowed_verdicts": ["FAIL", "CONCERNS"],
    }]
    suite_path.write_text(json.dumps(suite))
    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(held_out_mod, "HELD_OUT_DIR", held_out_dir)

    patch_text = "Require three-axis findings."
    candidate_id = candidate_id_for_patch("fake-skill", patch_text)
    overlay_path = create_candidate_overlay("fake-skill", patch_text)
    metadata = json.loads((Path(overlay_path) / ".candidate.json").read_text())
    trials = [
        _candidate_trial(
            candidate_id=candidate_id,
            agent_run_id=f"run-{index}",
            fixture_id=scenario_id,
            skill_md_sha256=metadata["skill_md_sha256"],
            overlay_path=overlay_path,
        )
        for index, scenario_id in enumerate(scenario_ids, 1)
    ]

    result = validate_held_out_candidate(
        "fake-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=trials,
    )

    assert result.promotion_eligible is False
    assert any("expected Standards verdict" in issue for issue in result.issues)
    assert any("expected Specification verdict" in issue for issue in result.issues)

    trials[0].findings = [{"axis": "Standards", "verdict": "FAIL"}]
    trials[1].findings = [{"axis": "Specification", "verdict": "CONCERNS"}]
    corrected = validate_held_out_candidate(
        "fake-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=trials,
    )
    assert corrected.promotion_eligible is True


def test_promotion_requires_candidate_aware_pass(tmp_path, monkeypatch):
    """Promotion requires both audit accepted and candidate-aware held-out promotion_eligible."""
    from harness.evolve.auditor import StructuredAuditResult
    from harness.evolve.skill_evolver import promote_patch

    # Create a minimal SkillPatch mock (named to avoid shadowing unittest.mock.patch)
    skill_patch = MagicMock()
    skill_patch.skill_name = "test-skill"
    skill_patch.timestamp = "20260804"
    skill_patch.patch_content = "test rule"
    skill_patch.patch_path = "/tmp/test.md"

    audit = StructuredAuditResult(accepted=True, issues=[], evidence={})

    # Command-only held-out (passed but not promotion-eligible)
    held_out = HeldOutResult(
        passed=True,
        promotion_eligible=False,
        skill_name="test-skill",
        candidate_id="",
        scenario_results=[],
        issues=["command-only"],
    )
    # Should NOT promote
    promoted = promote_patch(skill_patch, audit, held_out)
    assert promoted is False

    skill_dir = tmp_path / "skills" / "test-skill"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Original\n")
    held_out_dir = tmp_path / "held-out"
    scenario_ids = _write_suite(held_out_dir, "test-skill")
    monkeypatch.setattr("harness.evolve.held_out.SKILLS_DIR", tmp_path / "skills")
    monkeypatch.setattr("harness.evolve.held_out.HELD_OUT_DIR", held_out_dir)
    monkeypatch.setattr(
        "harness.evolve.skill_evolver.SKILLS_DIR", tmp_path / "skills"
    )
    candidate_id = candidate_id_for_patch(
        skill_patch.skill_name, skill_patch.patch_content
    )
    overlay_path = create_candidate_overlay(
        skill_patch.skill_name, skill_patch.patch_content
    )
    metadata = json.loads((Path(overlay_path) / ".candidate.json").read_text())
    candidate_trials = [
        SkillTrial(
            task_id=scenario_id,
            task_description="Fresh held-out promotion run",
            skill_name="test-skill",
            skill_version="0.1.0",
            candidate_id=candidate_id,
            agent_run_id=f"promotion-run-{index}",
            task_fixture_id=scenario_id,
            baseline_or_candidate="candidate",
            skill_md_read=True,
            primary_action_invoked=True,
            tool_calls=[{
                "tool": "Read",
                "args_summary": str(
                    (Path(overlay_path) / "test-skill" / "SKILL.md").resolve()
                ),
            }],
            validation_commands_run=["python3 -c \"assert 2 + 2 == 4\""],
            validation_results=["pass"],
            validation_exit_codes=[0],
            validation_stdout_hashes=["sha256:stdout"],
            functional_verification="pass",
            token_count=100,
            turn_count=2,
            duration_seconds=1.5,
            outcome="pass",
            skill_md_sha256=metadata["skill_md_sha256"],
            runner_provenance=f"codex/task/promotion-run-{index}",
            runner_output_hash="sha256:runner-output",
        )
        for index, scenario_id in enumerate(scenario_ids, 1)
    ]

    # Full candidate-aware held-out
    held_out_full = validate_held_out_candidate(
        "test-skill",
        candidate_id=candidate_id,
        candidate_overlay_path=overlay_path,
        candidate_trials=candidate_trials,
    )
    # Mock the file/registry operations so we don't touch real skills.
    with patch("harness.evolve.skill_evolver._backup_skill_md", return_value=Path("/tmp/mock")):
        with patch("harness.evolve.skill_evolver._load_registry", return_value=[{"name": "test-skill", "version": "0.1.0"}]):
            with patch("harness.evolve.skill_evolver._save_registry"):
                promoted = promote_patch(
                    skill_patch,
                    audit,
                    held_out_full,
                    manual_approval=True,
                )
    assert promoted is True
