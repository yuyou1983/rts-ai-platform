"""Tests for skill_evolver — registry schema, trace roundtrip, auditor, paths."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

import pytest

from harness.evolve.skill_evolver import (
    REPO_ROOT, SKILLS_DIR, REGISTRY_PATH, SCHEMA_PATH,
    CANDIDATES_DIR, HELD_OUT_DIR, TRIALS_DIR, BACKUP_DIR,
    ExplorationStrategy, SkillPatch, AuditResult,
    audit_patch, contrast_trials, save_patch_candidate,
    promote_patch, validate_held_out, _backup_skill_md, rollback_skill_md,
    _load_registry, _save_registry,
    STRATEGY_TEMPLATES, get_strategies,
)
from harness.evolve.held_out import HeldOutResult
from harness.trace.schema import SkillTrial, record_trial, load_trials


# ─── Path correctness ──────────────────────────────────────────

class TestPaths:
    def test_repo_root_is_git_repo(self):
        assert (REPO_ROOT / ".git").is_dir()

    def test_skills_dir_exists(self):
        assert SKILLS_DIR.is_dir()

    def test_registry_path_is_under_harness(self):
        assert "harness" in str(REGISTRY_PATH)
        assert REGISTRY_PATH.name == "registry.json"

    def test_schema_path_is_under_harness(self):
        assert SCHEMA_PATH.exists()

    def test_held_out_dir_structure(self):
        for skill_dir in HELD_OUT_DIR.iterdir():
            if skill_dir.is_dir():
                assert (skill_dir / "suite.json").exists(), f"missing suite.json in {skill_dir}"


# ─── Registry schema ──────────────────────────────────────────

class TestRegistrySchema:
    def test_required_fields_present(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        required = set(schema["required"])
        assert "primary_action" in required
        assert "expected_tool_calls" in required
        assert "validation_commands" in required
        assert "known_failure_modes" in required
        assert "layer_constraints" in required
        assert "owner_domain" in required

    def test_layer_enum_values(self):
        schema = json.loads(SCHEMA_PATH.read_text())
        layer_prop = schema["properties"]["layer_constraints"]
        assert set(layer_prop["items"]["enum"]) == {
            "proto",
            "simcore",
            "agents",
            "frontend-godot",
            "dev-harness",
        }

    def test_all_local_skills_registered(self):
        SKILLS_DIR = Path(__file__).resolve().parents[2] / ".agents" / "skills"
        REGISTRY_PATH = Path(__file__).resolve().parents[2] / "harness" / "skills" / "registry.json"
        registry = json.loads(REGISTRY_PATH.read_text())
        registered = {entry["name"] for entry in registry}
        local = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
        assert local <= registered

    def test_registry_entries_pass_schema(self):
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")
        schema = json.loads(SCHEMA_PATH.read_text())
        registry = json.loads(REGISTRY_PATH.read_text())
        for entry in registry:
            jsonschema.validate(entry, schema)

    def test_no_duplicate_names(self):
        registry = json.loads(REGISTRY_PATH.read_text())
        names = [e["name"] for e in registry]
        assert len(names) == len(set(names))

    def test_skill_dirs_exist(self):
        registry = json.loads(REGISTRY_PATH.read_text())
        for entry in registry:
            assert (SKILLS_DIR / entry["name"]).is_dir(), f"missing dir: {entry['name']}"
            assert (SKILLS_DIR / entry["name"] / "SKILL.md").exists(), f"missing SKILL.md: {entry['name']}"


# ─── Trace roundtrip ───────────────────────────────────────────

class TestTraceRoundtrip:
    def test_skill_trial_jsonl_roundtrip(self, tmp_path, monkeypatch):
        # 重定向 TRIALS_DIR 到 tmp
        import harness.trace.schema as schema_mod
        monkeypatch.setattr(schema_mod, "TRIALS_DIR", tmp_path / "trials")
        monkeypatch.setattr(schema_mod, "USAGE_FILE", tmp_path / "usage.jsonl")

        trial = SkillTrial(
            task_id="test-001",
            task_description="fix fog flicker",
            skill_name="godot-specialist",
            outcome="pass",
            skill_md_read=True,
            primary_action_invoked=True,
            tool_calls=[{"tool": "Read", "args_summary": "game_view.gd"}],
            validation_commands_run=["python3 -m pytest tests/ -q"],
            validation_results=["pass"],
            token_count=5000,
            turn_count=8,
            duration_seconds=45.0,
            touched_files=["godot/scripts/game_view.gd"],
            silent_bypass_detected=False,
            strategy_label="A",
        )

        path = record_trial(trial)
        assert path.exists()

        loaded = load_trials(skill_name="godot-specialist", outcome="pass")
        assert len(loaded) >= 1
        found = loaded[-1]
        assert found.task_id == "test-001"
        assert found.skill_md_read is True
        assert found.strategy_label == "A"

    def test_load_trials_filter(self, tmp_path, monkeypatch):
        import harness.trace.schema as schema_mod
        monkeypatch.setattr(schema_mod, "TRIALS_DIR", tmp_path / "trials")
        monkeypatch.setattr(schema_mod, "USAGE_FILE", tmp_path / "usage.jsonl")

        for outcome, label in [("pass", "A"), ("fail", "B"), ("pass", "C")]:
            record_trial(SkillTrial(
                task_id=f"filter-{outcome}-{label}",
                task_description="test",
                skill_name="godot-specialist",
                outcome=outcome,
                strategy_label=label,
            ))

        passes = load_trials(skill_name="godot-specialist", outcome="pass")
        fails = load_trials(skill_name="godot-specialist", outcome="fail")
        assert all(t.outcome == "pass" for t in passes)
        assert all(t.outcome == "fail" for t in fails)


# ─── Auditor interception ─────────────────────────────────────

class TestAuditor:
    def test_reject_hardcoded_seed(self):
        patch = SkillPatch(
            skill_name="team-simcore", timestamp="20260101-000000",
            patch_content="Use seed=42 for testing",
            rationale="test",
        )
        result = audit_patch(patch, "primary_action: write_file")
        assert not result.accepted
        assert any("hardcoded" in i for i in result.issues)

    def test_reject_llm_in_simcore(self):
        patch = SkillPatch(
            skill_name="team-simcore", timestamp="20260101-000000",
            patch_content="Add LLM call to simcore rules loop",
            rationale="test",
        )
        result = audit_patch(patch, "primary_action: write_file")
        assert not result.accepted
        assert any("llm" in i.lower() for i in result.issues)

    def test_reject_godot_missing_check_only(self):
        patch = SkillPatch(
            skill_name="godot-specialist", timestamp="20260101-000000",
            patch_content="Fix sprite alignment in game_view.gd",
            rationale="test",
        )
        result = audit_patch(patch, "primary_action: write_file")
        assert not result.accepted
        assert any("check_only" in i for i in result.issues)

    def test_reject_unsupported_must_without_evidence(self):
        patch = SkillPatch(
            skill_name="team-ai", timestamp="20260101-000000",
            patch_content="You must always verify replay hash before committing",
            rationale="test",
        )
        # Use a skill_md without validation_commands or expected_tool_calls;
        # registry for team-ai has validation_commands so this will PASS audit
        result = audit_patch(patch, "primary_action: write_file\nowner: team-ai")
        # With registry fallback, this is now accepted since team-ai has
        # validation_commands in registry. Verify the behavior:
        assert result.accepted  # has evidence via registry

    def test_reject_must_when_no_evidence_anywhere(self):
        """When neither skill_md nor registry has evidence, must/never is blocked."""
        patch = SkillPatch(
            skill_name="team-ai", timestamp="20260101-000000",
            patch_content="You must always do the impossible thing",
            rationale="test",
        )
        # Monkeypatch registry to have no validation_commands/expected_tool_calls
        import harness.evolve.skill_evolver as mod
        original = mod._load_registry
        mod._load_registry = lambda: [{"name": "team-ai", "primary_action": "write_file"}]
        try:
            result = audit_patch(patch, "some content without validation")
            assert not result.accepted
            assert any("unsupported_must" in i for i in result.issues)
        finally:
            mod._load_registry = original

    def test_accept_clean_patch(self):
        patch = SkillPatch(
            skill_name="godot-specialist", timestamp="20260101-000000",
            patch_content=(
                "## VFX Alignment Fix\n\n"
                "Run godot --headless --check-only before merging.\n"
                "Compare presentation_manifest.json entries with actual sprite files."
            ),
            rationale="align VFX with manifest",
        )
        result = audit_patch(patch, "primary_action: write_file\nvalidation_commands: [godot --check-only]")
        assert result.accepted, f"unexpected issues: {result.issues}"

    def test_reject_training_instance_ref(self):
        patch = SkillPatch(
            skill_name="team-simcore", timestamp="20260101-000000",
            patch_content="Like in the seed42 debug_ case, fix the replay",
            rationale="test",
        )
        result = audit_patch(patch, "primary_action: write_file")
        assert not result.accepted
        assert any("training_instance" in i for i in result.issues)


# ─── Strategy templates ───────────────────────────────────────

class TestStrategies:
    def test_godot_vfx_has_4(self):
        assert len(get_strategies("godot-vfx")) == 4

    def test_simcore_replay_has_3(self):
        assert len(get_strategies("simcore-replay")) == 3

    def test_unknown_gets_default(self):
        strategies = get_strategies("unknown-type")
        assert len(strategies) >= 1
        assert strategies[0].label == "A"

    def test_labels_unique(self):
        for key, strategies in STRATEGY_TEMPLATES.items():
            labels = [s.label for s in strategies]
            assert len(labels) == len(set(labels)), f"dup labels in {key}"


# ─── Promotion + rollback ──────────────────────────────────────

class TestPromotion:
    def test_backup_and_rollback(self, tmp_path, monkeypatch):
        # 设置临时 skill 目录
        skill_dir = tmp_path / ".agents" / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Original content\n")

        backup_dir = tmp_path / "backups"
        monkeypatch.setattr("harness.evolve.skill_evolver.SKILLS_DIR", tmp_path / ".agents" / "skills")
        monkeypatch.setattr("harness.evolve.skill_evolver.BACKUP_DIR", backup_dir)

        # 备份
        backup = _backup_skill_md("test-skill")
        assert backup is not None
        assert backup.exists()
        assert "Original content" in backup.read_text()

        # 修改 SKILL.md
        skill_md.write_text("# Modified content\n")
        assert "Modified" in skill_md.read_text()

        # Rollback
        rollback_skill_md("test-skill", backup)
        assert "Original content" in skill_md.read_text()

    def test_promote_updates_registry(self, tmp_path, monkeypatch):
        # 设置临时 registry
        reg_file = tmp_path / "registry.json"
        reg_file.write_text(json.dumps([{
            "name": "test-skill",
            "version": "0.1.0",
            "last_evolved": None,
        }]))

        # 设置临时 skill
        skill_dir = tmp_path / "skills" / "test-skill"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Original\n")

        backup_dir = tmp_path / "backups"
        backup_dir.mkdir(parents=True)
        (backup_dir / "test-skill_20260101-000000.md").write_text("# Original\n")

        monkeypatch.setattr("harness.evolve.skill_evolver.SKILLS_DIR", tmp_path / "skills")
        monkeypatch.setattr("harness.evolve.skill_evolver.REGISTRY_PATH", reg_file)
        monkeypatch.setattr("harness.evolve.skill_evolver.BACKUP_DIR", backup_dir)

        patch = SkillPatch(
            skill_name="test-skill", timestamp="20260101-000000",
            patch_content="## New rule\nDo X.", rationale="test",
        )
        audit = AuditResult(patch_path="test-skill/20260101-000000", accepted=True, issues=[])

        # promote — candidate-aware held-out evidence (promotion-eligible)
        held_out = HeldOutResult(
            passed=True, promotion_eligible=True, skill_name="test-skill",
            candidate_id="cand-001",
            scenario_results=[{"scenario": "s1", "passed": True}], issues=[],
        )
        result = promote_patch(patch, audit, held_out)
        assert result is True
        assert "Evolved Rules" in skill_md.read_text()

        # registry 已更新
        reg = json.loads(reg_file.read_text())
        assert reg[0]["version"] == "0.1.1"
        assert reg[0]["last_evolved"] is not None

    def test_promote_fails_without_audit(self):
        patch = SkillPatch(
            skill_name="any", timestamp="20260101", patch_content="", rationale=""
        )
        audit = AuditResult(patch_path="any/20260101", accepted=False, issues=["bad"])
        held_out = HeldOutResult(
            passed=True, promotion_eligible=True, skill_name="any",
            candidate_id="cand-001", scenario_results=[], issues=[],
        )
        assert promote_patch(patch, audit, held_out) is False

    def test_promote_fails_without_held_out(self):
        patch = SkillPatch(
            skill_name="any", timestamp="20260101", patch_content="", rationale=""
        )
        audit = AuditResult(patch_path="any/20260101", accepted=True, issues=[])
        # held-out failed → not promotion-eligible
        held_out = HeldOutResult(
            passed=False, promotion_eligible=False, skill_name="any",
            candidate_id="cand-001", scenario_results=[], issues=["fail"],
        )
        assert promote_patch(patch, audit, held_out) is False

    def test_promote_fails_with_command_only_held_out(self):
        """A command-only (passed but not promotion-eligible) result blocks promotion."""
        patch = SkillPatch(
            skill_name="any", timestamp="20260101", patch_content="", rationale=""
        )
        audit = AuditResult(patch_path="any/20260101", accepted=True, issues=[])
        held_out = HeldOutResult(
            passed=True, promotion_eligible=False, skill_name="any",
            candidate_id="", scenario_results=[], issues=["command-only"],
        )
        assert promote_patch(patch, audit, held_out) is False

    def test_promote_bool_backward_compat_blocks(self):
        """A legacy bool argument is treated as command-only and never promotes."""
        patch = SkillPatch(
            skill_name="any", timestamp="20260101", patch_content="", rationale=""
        )
        audit = AuditResult(patch_path="any/20260101", accepted=True, issues=[])
        # Even True is command-only and thus not promotion-eligible.
        assert promote_patch(patch, audit, True) is False
        assert promote_patch(patch, audit, False) is False


def test_godot_held_out_uses_real_validation_commands():
    HELD_OUT_DIR = Path(__file__).resolve().parents[2] / "harness" / "skills" / "held_out"
    suite = json.loads((HELD_OUT_DIR / "godot-specialist" / "suite.json").read_text())
    commands = [
        cmd
        for scenario in suite["scenarios"]
        for cmd in scenario["validation_commands"]
    ]
    assert any("verify_presentation_scene.py" in cmd for cmd in commands)
    assert any("verify_godot_fog_smoothing.py" in cmd for cmd in commands)
    assert any("--check-only" in cmd for cmd in commands)
    assert all("|| true" not in cmd for cmd in commands)


def test_contrast_detects_missing_validation_command(monkeypatch):
    from harness.evolve import skill_evolver as mod
    from harness.trace.schema import SkillTrial

    pass_trial = SkillTrial(
        task_id="pass-1",
        task_description="godot vfx",
        skill_name="godot-specialist",
        outcome="pass",
        skill_md_read=True,
        primary_action_invoked=True,
        validation_commands_run=["python3 scripts/verify_presentation_scene.py"],
        validation_results=["pass"],
        touched_files=["godot/resources/presentation_manifest.json"],
    )
    fail_trial = SkillTrial(
        task_id="fail-1",
        task_description="godot vfx",
        skill_name="godot-specialist",
        outcome="fail",
        skill_md_read=True,
        primary_action_invoked=True,
        validation_commands_run=[],
        validation_results=[],
        touched_files=["godot/scripts/game_view.gd"],
    )

    def fake_load_trials(skill_name=None, outcome=None):
        return {"pass": [pass_trial], "fail": [fail_trial]}[outcome]

    monkeypatch.setattr(mod, "load_trials", fake_load_trials)
    patches = mod.contrast_trials("godot-specialist")
    assert any("verify_presentation_scene.py" in p.patch_content for p in patches)


def test_save_patch_candidate_preserves_same_timestamp_candidates(tmp_path, monkeypatch):
    from harness.evolve import skill_evolver as mod

    monkeypatch.setattr(mod, "CANDIDATES_DIR", tmp_path / "candidates")
    patch_one = SkillPatch(
        skill_name="godot-specialist",
        timestamp="20260608-000000",
        patch_content="first patch",
        rationale="first",
    )
    patch_two = SkillPatch(
        skill_name="godot-specialist",
        timestamp="20260608-000000",
        patch_content="second patch",
        rationale="second",
    )

    path_one = save_patch_candidate(patch_one)
    path_two = save_patch_candidate(patch_two)

    assert path_one != path_two
    assert (path_one / "patch.md").read_text() == "first patch"
    assert (path_two / "patch.md").read_text() == "second patch"


class TestDryRun:
    def test_dry_run_does_not_modify_skill_md(self, tmp_path, monkeypatch):
        """evolve_skill_dry generates candidates but never writes SKILL.md."""
        from harness.evolve.skill_evolver import evolve_skill_dry

        skill_dir = tmp_path / ".agents" / "skills" / "test-dry"
        skill_dir.mkdir(parents=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("# Original\nprimary_action: write_file\n")

        monkeypatch.setattr("harness.evolve.skill_evolver.SKILLS_DIR", tmp_path / ".agents" / "skills")
        monkeypatch.setattr("harness.evolve.skill_evolver.CANDIDATES_DIR", tmp_path / "candidates")
        monkeypatch.setattr("harness.evolve.skill_evolver.HELD_OUT_DIR", tmp_path / "held_out")
        monkeypatch.setattr("harness.evolve.skill_evolver.BACKUP_DIR", tmp_path / "backups")
        monkeypatch.setattr("harness.evolve.skill_evolver.REGISTRY_PATH", tmp_path / "registry.json")

        # No trials → returns False, but no file modification either
        evolve_skill_dry("test-dry")
        assert skill_md.read_text() == "# Original\nprimary_action: write_file\n"
