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


def test_held_out_candidate_packets_bind_overlay_and_unique_runs(tmp_path, monkeypatch):
    import harness.evolve.strategy_runner as runner
    from harness.evolve.strategy_runner import generate_held_out_candidate_packets

    skill_name = "fake-skill"
    candidate_id = "cand-exact-patch"
    overlay = tmp_path / "overlay"
    overlay_skill = overlay / skill_name
    overlay_skill.mkdir(parents=True)
    (overlay_skill / "SKILL.md").write_text("# Candidate Skill\n")
    (overlay / ".candidate.json").write_text(json.dumps({
        "schema_version": 1,
        "candidate_id": candidate_id,
        "skill_name": skill_name,
        "skill_md_sha256": "sha256:skill-md",
    }))

    held_out_dir = tmp_path / "held-out"
    suite_dir = held_out_dir / skill_name
    suite_dir.mkdir(parents=True)
    scenario_ids = ["held-out/fake/one", "held-out/fake/two"]
    (suite_dir / "suite.json").write_text(json.dumps({
        "skill_name": skill_name,
        "scenarios": [
            {
                "id": scenario_id,
                "description": f"Review fixture {scenario_id}",
                "validation_commands": ["python3 -c \"assert True\""],
                "pass_criteria": "The review identifies the planted issue.",
            }
            for scenario_id in scenario_ids
        ],
    }))
    monkeypatch.setattr(runner, "HELD_OUT_DIR", held_out_dir)

    out_dir = tmp_path / "runs"
    manifest = generate_held_out_candidate_packets(
        skill_name,
        overlay,
        out_dir=out_dir,
        run_id="candidate-run",
    )

    assert manifest["candidate_id"] == candidate_id
    assert manifest["candidate_overlay_path"] == str(overlay.resolve())
    assert manifest["skill_md_sha256"] == "sha256:skill-md"
    assert len(manifest["packets"]) == 2
    assert len({packet["agent_run_id"] for packet in manifest["packets"]}) == 2
    for packet, scenario_id in zip(manifest["packets"], scenario_ids):
        assert packet["scenario_id"] == scenario_id
        text = (out_dir / packet["packet_path"]).read_text()
        overlay_skill_path = overlay.resolve() / skill_name / "SKILL.md"
        assert f"Read `{overlay_skill_path}` first" in text
        assert "Do not read the repository base skill" in text
        assert f"- `candidate_id`: `{candidate_id}`" in text
        assert f"- `agent_run_id`: `{packet['agent_run_id']}`" in text
        assert "- `baseline_or_candidate`: `candidate`" in text
