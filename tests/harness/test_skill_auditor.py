from __future__ import annotations

from harness.evolve.auditor import audit_candidate_patch


def test_auditor_rejects_runtime_business_code_target():
    result = audit_candidate_patch(
        skill_name="godot-specialist",
        patch_content="Add a rule: edit simcore/rules.py to make fog stable.",
        skill_md_content="primary_action: write_file\nvalidation_commands: [python3 scripts/verify_presentation_scene.py]",
        evidence={"touched_files": ["simcore/rules.py"]},
    )
    assert not result.accepted
    assert "runtime_business_code_target" in result.issues


def test_auditor_rejects_training_fixture_leak():
    result = audit_candidate_patch(
        skill_name="godot-specialist",
        patch_content="Always fix godot-vfx/sc1-resource-alignment by changing CommandCenter atlas_rect to [205,190,145,95].",
        skill_md_content="primary_action: write_file\nvalidation_commands: [python3 scripts/verify_presentation_scene.py]",
        evidence={"task_fixture_id": "godot-vfx/sc1-resource-alignment"},
    )
    assert not result.accepted
    assert "fixture_specific_rule" in result.issues


def test_auditor_accepts_general_validation_rule():
    result = audit_candidate_patch(
        skill_name="godot-specialist",
        patch_content="For Godot VFX tasks, run presentation manifest validation before changing runtime scripts and record atlas/fallback failures as evidence.",
        skill_md_content="primary_action: write_file\nvalidation_commands: [python3 scripts/verify_presentation_scene.py]",
        evidence={"touched_files": [".agents/skills/godot-specialist/SKILL.md"]},
    )
    assert result.accepted
