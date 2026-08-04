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


def test_strategy_runner_writes_packet_per_strategy(tmp_path, monkeypatch):
    from harness.evolve.strategy_runner import generate_strategy_packets

    fixture_path = ROOT / "harness/skills/tasks/godot-vfx/sc1-resource-alignment.json"
    out_dir = tmp_path / "runs"
    manifest = generate_strategy_packets(fixture_path, out_dir=out_dir, run_id="run-test")

    assert manifest["run_id"] == "run-test"
    assert manifest["skill_name"] == "godot-specialist"
    assert len(manifest["packets"]) == 4
    for packet in manifest["packets"]:
        packet_path = out_dir / packet["packet_path"]
        assert packet_path.exists()
        text = packet_path.read_text()
        assert "Read `.agents/skills/godot-specialist/SKILL.md` first" in text
        assert "Record a SkillTrial v2" in text


def test_strategy_packet_includes_vertical_ticket_sections(tmp_path):
    """Generated packets must render the vertical ticket sections before
    Validation Commands."""
    from harness.evolve.strategy_runner import generate_strategy_packets

    fixture_path = ROOT / "harness/skills/tasks/godot-vfx/sc1-resource-alignment.json"
    out_dir = tmp_path / "runs"
    manifest = generate_strategy_packets(fixture_path, out_dir=out_dir, run_id="run-vertical")

    expected_sections = [
        "## Source Specification",
        "## Blocked By",
        "## Acceptance Criteria",
        "## Verification Seams",
        "## Evidence Outputs",
        "## Stop Condition",
    ]
    for packet in manifest["packets"]:
        text = (out_dir / packet["packet_path"]).read_text()
        # Every vertical section header is present.
        for section in expected_sections:
            assert section in text, f"missing section {section!r} in packet {packet['strategy_label']}"
        # The vertical sections must appear before the Validation Commands section.
        for section in expected_sections:
            assert text.index(section) < text.index("## Validation Commands"), (
                f"{section!r} must precede Validation Commands"
            )
        # Stop condition pins the fixture id and forbids starting other tickets.
        assert "Execute ONLY the current task fixture" in text
        # Source spec and acceptance content render from the fixture.
        fixture = json.loads(fixture_path.read_text())
        assert fixture["source_spec"] in text
        assert fixture["acceptance_criteria"][0] in text
        assert fixture["verification_seams"][0] in text
        assert fixture["evidence_outputs"][0] in text
