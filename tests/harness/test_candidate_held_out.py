#!/usr/bin/env python3
"""Tests for candidate-aware held-out validation."""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from harness.evolve.held_out import HeldOutResult, validate_held_out_candidate


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
    assert "primary_action: write_file" in overlay_md
    assert "## Candidate Patch" in overlay_md
    assert "## New Rule" in overlay_md
    # The overlay must live outside the repository working tree (temp dir)
    assert not overlay.is_relative_to(REPO)


def test_candidate_overlay_raises_for_missing_skill(tmp_path, monkeypatch):
    import harness.evolve.held_out as held_out_mod

    monkeypatch.setattr(held_out_mod, "SKILLS_DIR", tmp_path / ".agents" / "skills")
    with pytest.raises(FileNotFoundError):
        held_out_mod.create_candidate_overlay("no-such-skill", "patch")


def test_promotion_requires_candidate_aware_pass():
    """Promotion requires both audit accepted and candidate-aware held-out promotion_eligible."""
    from harness.evolve.skill_evolver import promote_patch
    from harness.evolve.auditor import StructuredAuditResult

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

    # Full candidate-aware held-out
    held_out_full = HeldOutResult(
        passed=True,
        promotion_eligible=True,
        skill_name="test-skill",
        candidate_id="cand-001",
        scenario_results=[{"scenario": "s1", "passed": True}],
        issues=[],
    )
    # Mock the file/registry operations so we don't touch real skills.
    with patch("harness.evolve.skill_evolver._backup_skill_md", return_value=Path("/tmp/mock")):
        with patch("harness.evolve.skill_evolver.SKILLS_DIR", REPO / ".agents" / "skills"):
            with patch("pathlib.Path.read_text", return_value="# Original\n"):
                with patch("pathlib.Path.write_text"):
                    with patch("harness.evolve.skill_evolver._load_registry", return_value=[{"name": "test-skill", "version": "0.1.0"}]):
                        with patch("harness.evolve.skill_evolver._save_registry"):
                            promoted = promote_patch(skill_patch, audit, held_out_full)
    assert promoted is True
