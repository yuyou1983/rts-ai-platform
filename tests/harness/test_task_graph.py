#!/usr/bin/env python3
"""Tests for vertical ticket task graph validation."""
import json
import pytest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO / "harness" / "skills" / "tasks" / "schema.json"
TASKS_DIR = REPO / "harness" / "skills" / "tasks"

REQUIRED_FIELDS = ["source_spec", "blocked_by", "acceptance_criteria", "verification_seams", "evidence_outputs", "status"]
VALID_STATUSES = {"blocked", "ready", "in_progress", "verification", "done"}

def test_schema_requires_vertical_fields():
    schema = json.loads(SCHEMA_PATH.read_text())
    required = set(schema["required"])
    assert set(REQUIRED_FIELDS) <= required, f"Missing required fields: {set(REQUIRED_FIELDS) - required}"

def test_schema_status_enum():
    schema = json.loads(SCHEMA_PATH.read_text())
    status_prop = schema["properties"]["status"]
    assert set(status_prop["enum"]) == VALID_STATUSES

def test_schema_requires_at_least_one_criterion():
    schema = json.loads(SCHEMA_PATH.read_text())
    for field in ["acceptance_criteria", "verification_seams", "evidence_outputs"]:
        assert schema["properties"][field]["minItems"] >= 1, f"{field} should require at least 1 item"

def _load_fixtures():
    fixtures = []
    for path in TASKS_DIR.rglob("*.json"):
        if path.name == "schema.json":
            continue
        fixtures.append((path.stem, json.loads(path.read_text())))
    return fixtures

def test_all_fixtures_have_required_fields():
    for name, fixture in _load_fixtures():
        for field in REQUIRED_FIELDS:
            assert field in fixture, f"{name}: missing {field}"

def test_all_fixtures_have_valid_status():
    for name, fixture in _load_fixtures():
        assert fixture["status"] in VALID_STATUSES, f"{name}: invalid status {fixture['status']}"

def test_blocked_by_references_exist():
    fixtures = _load_fixtures()
    ids = {name for name, _ in fixtures}
    for name, fixture in fixtures:
        for blocker in fixture.get("blocked_by", []):
            assert blocker in ids, f"{name}: unknown blocker '{blocker}'"

def test_ready_requires_done_blockers():
    fixtures = _load_fixtures()
    status_by_id = {name: fixture["status"] for name, fixture in fixtures}
    for name, fixture in fixtures:
        if fixture["status"] == "ready":
            for blocker in fixture.get("blocked_by", []):
                assert status_by_id.get(blocker) == "done", f"{name}: blocker '{blocker}' is not done"

def test_source_specs_exist_on_disk():
    for name, fixture in _load_fixtures():
        spec = fixture.get("source_spec", "")
        if spec:
            assert (REPO / spec).exists(), f"{name}: source_spec '{spec}' does not exist"

def test_no_fixture_path_in_own_forbidden():
    for name, fixture in _load_fixtures():
        forbidden = fixture.get("forbidden_paths", [])
        fixture_path = f"harness/skills/tasks/"
        for f in forbidden:
            assert not f.startswith("harness/skills/tasks"), f"{name}: forbidden path '{f}' overlaps task fixtures"

def test_validate_tasks_script_passes():
    import subprocess
    result = subprocess.run(
        ["python3", "harness/skills/validate_tasks.py"],
        capture_output=True, text=True, cwd=str(REPO)
    )
    assert result.returncode == 0, f"validate_tasks.py failed: {result.stdout}\n{result.stderr}"
