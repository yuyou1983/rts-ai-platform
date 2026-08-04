#!/usr/bin/env python3
"""Contract tests for the upgraded code-review skill."""
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SKILL_PATH = REPO / ".agents" / "skills" / "code-review" / "SKILL.md"
FIXTURE_PATH = REPO / "harness" / "skills" / "tasks" / "code-review" / "combat-remediation-review.json"

REQUIRED_HEADINGS = [
    "Pin The Fixed Point",
    "Locate The Originating Specification",
    "Standards Axis",
    "Specification Axis",
    "Source Truth Axis",
    "Independent Verdicts",
]

def test_skill_file_exists():
    assert SKILL_PATH.exists()

def test_required_headings_present():
    content = SKILL_PATH.read_text()
    for heading in REQUIRED_HEADINGS:
        assert heading in content, f"Missing heading: {heading}"

def test_uses_git_diff_fixed_point():
    content = SKILL_PATH.read_text()
    assert "git diff" in content
    assert "fixed-point" in content.lower() or "fixed point" in content.lower()

def test_does_not_require_subagent():
    content = SKILL_PATH.read_text()
    assert "subagent" not in content.lower() or "does not require" in content.lower()

def test_does_not_merge_verdicts():
    content = SKILL_PATH.read_text()
    # Must have separate verdict lines per axis
    assert "Standards" in content and "Specification" in content
    assert "Verdict:" in content

def test_review_fixture_exists():
    assert FIXTURE_PATH.exists()

def test_fixture_forbids_runtime_changes():
    import json
    fixture = json.loads(FIXTURE_PATH.read_text())
    forbidden = fixture.get("forbidden_paths", [])
    assert "simcore/" in forbidden or any("simcore" in p for p in forbidden)
    assert "godot/scripts/" in forbidden or any("godot" in p for p in forbidden)

def test_fixture_detects_qa_drift():
    import json
    fixture = json.loads(FIXTURE_PATH.read_text())
    criteria = fixture.get("acceptance_criteria", [])
    assert any("drift" in c.lower() or "disagree" in c.lower() or "status" in c.lower() for c in criteria)
