from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_SCHEMA = ROOT / "harness/skills/tasks/schema.json"
GODOT_FIXTURE = ROOT / "harness/skills/tasks/godot-vfx/sc1-resource-alignment.json"


def test_godot_vfx_fixture_matches_schema():
    import jsonschema

    schema = json.loads(TASK_SCHEMA.read_text())
    fixture = json.loads(GODOT_FIXTURE.read_text())
    jsonschema.validate(fixture, schema)


def test_godot_vfx_fixture_has_four_unique_strategies():
    fixture = json.loads(GODOT_FIXTURE.read_text())
    labels = [s["label"] for s in fixture["fresh_agent_strategies"]]
    assert labels == ["A", "B", "C", "D"]
    assert len(labels) == len(set(labels))


def test_godot_vfx_fixture_forbids_runtime_business_layers():
    fixture = json.loads(GODOT_FIXTURE.read_text())
    assert "simcore/" in fixture["forbidden_paths"]
    assert "agents/" in fixture["forbidden_paths"]
    assert "godot/scripts/" in fixture["forbidden_paths"]
