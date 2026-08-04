"""Tests for skill registry invocation + composition semantics (Task 1, Gate A1).

These tests pin the workflow-semantics fields added to the skill registry schema
(`invocation_mode`, `skill_kind`, `completion_criteria`, `composes`) and the
composition-graph invariants enforced by ``validate_composition``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from harness.skills.validate_registry import validate, validate_composition

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "harness" / "skills" / "schema.json"
REGISTRY_PATH = REPO_ROOT / "harness" / "skills" / "registry.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _load_registry() -> list[dict]:
    return json.loads(REGISTRY_PATH.read_text())


def _entry(
    name: str,
    invocation_mode: str = "both",
    skill_kind: str = "discipline",
    composes: list[str] | None = None,
    completion_criteria: list[str] | None = None,
) -> dict:
    """Build a minimal valid entry for composition-graph fixtures."""
    return {
        "name": name,
        "invocation_mode": invocation_mode,
        "skill_kind": skill_kind,
        "composes": list(composes) if composes else [],
        "completion_criteria": completion_criteria or ["targeted tests pass"],
    }


# ─── Schema semantics ──────────────────────────────────────────


class TestSchemaSemantics:
    def test_registry_requires_workflow_semantics(self) -> None:
        schema = _load_schema()
        required = set(schema["required"])
        assert {"invocation_mode", "skill_kind", "completion_criteria"} <= required

    def test_registry_semantic_enums_are_closed(self) -> None:
        schema = _load_schema()
        props = schema["properties"]
        assert props["invocation_mode"]["enum"] == ["user", "model", "both"]
        assert props["skill_kind"]["enum"] == [
            "orchestrator",
            "discipline",
            "domain",
            "gate",
        ]

    def test_composes_pattern_validates(self) -> None:
        schema = _load_schema()
        composes = schema["properties"]["composes"]
        assert composes["type"] == "array"
        assert composes["uniqueItems"] is True
        assert composes.get("default") == []
        pattern = composes["items"]["pattern"]

        # Valid skill identifiers match the pattern (leading lowercase letter
        # followed by one or more lowercase/digit/hyphen chars -> length >= 2).
        for good in ("godot-gdscript-specialist", "test-matrix", "code-review", "x1"):
            assert re.fullmatch(pattern, good), good
        # Invalid identifiers are rejected.
        for bad in ("Godot_Specialist", "1bad", "has space", "UPPER!", "", "a"):
            assert not re.fullmatch(pattern, bad), bad

        jsonschema = pytest.importorskip("jsonschema")
        # A composes entry violating the pattern fails schema validation.
        bad_pattern = _entry("bad-pattern", "both", "orchestrator", composes=["UPPER!"])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad_pattern, schema)
        # Duplicate composes entries are rejected by uniqueItems.
        dup = _entry("dup-orc", "both", "orchestrator", composes=["a-skill", "a-skill"])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(dup, schema)


# ─── Composition graph ─────────────────────────────────────────


class TestCompositionGraph:
    def test_composition_targets_exist(self) -> None:
        # Synthetic registry referencing a non-existent target.
        reg = [_entry("alpha", "user", "orchestrator", composes=["ghost"])]
        issues = validate_composition(reg)
        assert any(
            "alpha" in i and "ghost" in i and "does not exist" in i for i in issues
        )

        # Real registry: every composes target resolves to a registered skill.
        real_issues = validate_composition(_load_registry())
        assert not any("does not exist" in i for i in real_issues)

    def test_composition_graph_has_no_cycles(self) -> None:
        # Synthetic 2-cycle: alpha -> beta -> alpha.
        reg = [
            _entry("alpha", "user", "orchestrator", composes=["beta"]),
            _entry("beta", "user", "orchestrator", composes=["alpha"]),
        ]
        issues = validate_composition(reg)
        assert any("cycle" in i.lower() for i in issues)
        # The cycle report must name the participating edges.
        assert any("alpha" in i and "beta" in i for i in issues)

        # Real registry: the directed composition graph is acyclic.
        real_issues = validate_composition(_load_registry())
        assert not any("cycle" in i.lower() for i in real_issues)

    def test_non_orchestrator_has_no_composition_edges(self) -> None:
        # A discipline (non-orchestrator) may not carry composes edges.
        reg = [
            _entry("solo", "model", "discipline", composes=["other"]),
            _entry("other", "model", "discipline"),
        ]
        issues = validate_composition(reg)
        assert any("solo" in i and "non-orchestrator" in i for i in issues)

        # Real registry: only orchestrators compose.
        real = _load_registry()
        real_issues = validate_composition(real)
        assert not any("non-orchestrator" in i for i in real_issues)
        for entry in real:
            if entry.get("composes"):
                assert entry["skill_kind"] == "orchestrator", entry["name"]

    def test_model_skill_does_not_require_user_only_child(self) -> None:
        # A model orchestrator cannot depend on a user-only child.
        reg = [
            _entry("mo", "model", "orchestrator", composes=["uokid"]),
            _entry("uokid", "user", "discipline"),
        ]
        issues = validate_composition(reg)
        assert any(
            "mo" in i and "user-only child" in i and "uokid" in i for i in issues
        )

        # A model orchestrator composing a model/both child is allowed.
        ok = [
            _entry("mo2", "model", "orchestrator", composes=["mkid"]),
            _entry("mkid", "model", "discipline"),
        ]
        assert not any("user-only child" in i for i in validate_composition(ok))

        # Real registry: no model orchestrator requires a user-only child.
        real_issues = validate_composition(_load_registry())
        assert not any("user-only child" in i for i in real_issues)

    def test_all_skills_have_nonempty_completion_criteria(self) -> None:
        # Every registry entry must declare at least one observable criterion.
        for entry in _load_registry():
            cc = entry.get("completion_criteria")
            assert isinstance(cc, list), entry["name"]
            assert len(cc) >= 1, entry["name"]
            assert all(isinstance(c, str) and c.strip() for c in cc), entry["name"]

        # A schema-level empty array is rejected.
        schema = _load_schema()
        jsonschema = pytest.importorskip("jsonschema")
        empty = _entry("empty-cc", "both", "discipline", completion_criteria=[])
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(empty, schema)

    def test_no_skill_composes_itself(self) -> None:
        # Synthetic self-composition.
        reg = [_entry("loopy", "user", "orchestrator", composes=["loopy"])]
        issues = validate_composition(reg)
        assert any("loopy" in i and "cannot compose itself" in i for i in issues)

        # Real registry: no skill composes itself.
        real = _load_registry()
        for entry in real:
            assert entry["name"] not in (entry.get("composes") or []), entry["name"]
        real_issues = validate_composition(_load_registry())
        assert not any("cannot compose itself" in i for i in real_issues)

    def test_all_entries_carry_semantic_fields(self) -> None:
        """Gate A1: all 23 entries carry invocation_mode, skill_kind, composes."""
        real = _load_registry()
        assert len(real) == 23
        for entry in real:
            assert entry["invocation_mode"] in {"user", "model", "both"}, entry["name"]
            assert entry["skill_kind"] in {
                "orchestrator",
                "discipline",
                "domain",
                "gate",
            }, entry["name"]
            assert isinstance(entry.get("composes"), list), entry["name"]

    def test_real_registry_passes_full_validate(self) -> None:
        """Gate A1: the full validator (schema + composition) returns no issues."""
        issues = validate()
        assert issues == [], "\n".join(issues)
