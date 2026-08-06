from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "harness/skills/candidates/strategy_runs"
HELD_OUT_DIR = REPO_ROOT / "harness/skills/held_out"


def _load_fixture(fixture_path: Path) -> dict[str, Any]:
    return json.loads(fixture_path.read_text())


def _packet_text(fixture: dict[str, Any], strategy: dict[str, Any]) -> str:
    focus = "\n".join(f"- `{p}`" for p in strategy["focus_files"])
    rules = "\n".join(f"- {r}" for r in strategy["extra_rules"])
    validations = "\n".join(f"- `{cmd}`" for cmd in fixture["validation_commands"])
    forbidden = "\n".join(f"- `{p}`" for p in fixture["forbidden_paths"])
    criteria = "\n".join(f"- {p}" for p in fixture["pass_criteria"])
    skill = fixture["skill_name"]

    # Vertical ticket semantics (optional on legacy fixtures).
    source_spec = fixture.get("source_spec", "")
    blocked_by = fixture.get("blocked_by", [])
    acceptance = fixture.get("acceptance_criteria", [])
    seams = fixture.get("verification_seams", [])
    evidence = fixture.get("evidence_outputs", [])

    source_spec_line = f"`{source_spec}`" if source_spec else "_(none declared)_"
    blocked_lines = "\n".join(f"- `{b}`" for b in blocked_by) if blocked_by else "_(none — ticket is ungated)_"
    acceptance_lines = "\n".join(f"- {c}" for c in acceptance) if acceptance else "_(none declared)_"
    seams_lines = "\n".join(f"- `{s}`" for s in seams) if seams else "_(none declared)_"
    evidence_lines = "\n".join(f"- `{p}`" for p in evidence) if evidence else "_(none declared)_"

    return f"""# Strategy {strategy["label"]}: {strategy["description"]}

Task fixture: `{fixture["id"]}`
Skill: `{skill}`

## Required First Action

Read `.agents/skills/{skill}/SKILL.md` first and follow its instructions.

## Task

{fixture["description"]}

## Focus Files

{focus}

## Strategy Rules

{rules}

## Forbidden Runtime Paths

{forbidden}

## Source Specification

{source_spec_line}

## Blocked By

{blocked_lines}

## Acceptance Criteria

{acceptance_lines}

## Verification Seams

{seams_lines}

## Evidence Outputs

{evidence_lines}

## Stop Condition

Execute ONLY the current task fixture (`{fixture["id"]}`). Do not begin any other
fixture. Stop after every verification seam passes and all evidence outputs have
been recorded/updated. If a seam fails, stop and report the failure rather than
proceeding to a different ticket.

## Validation Commands

{validations}

## Pass Criteria

{criteria}

## Trace Requirement

Record a SkillTrial v2 with:
- `skill_name`: `{skill}`
- `task_fixture_id`: `{fixture["id"]}`
- `strategy_label`: `{strategy["label"]}`
- `skill_md_read`: true only if the SKILL.md was actually read
- `primary_action_invoked`: true only if the declared primary action was actually invoked
- `validation_commands_run`: the exact validation commands run
- `validation_exit_codes`: command exit codes in the same order
- `baseline_or_candidate`: `baseline`
"""


def generate_strategy_packets(
    fixture_path: Path,
    out_dir: Path = DEFAULT_OUT_DIR,
    run_id: str | None = None,
) -> dict[str, Any]:
    fixture = _load_fixture(fixture_path)
    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    packets: list[dict[str, str]] = []
    for strategy in fixture["fresh_agent_strategies"]:
        rel = Path(run_id) / f"strategy-{strategy['label']}.md"
        packet_path = out_dir / rel
        packet_path.write_text(_packet_text(fixture, strategy))
        packets.append({
            "strategy_label": strategy["label"],
            "packet_path": str(rel),
        })

    manifest = {
        "run_id": run_id,
        "fixture_id": fixture["id"],
        "skill_name": fixture["skill_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "packets": packets,
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest


def _held_out_candidate_packet_text(
    *,
    skill_name: str,
    scenario: dict[str, Any],
    candidate_id: str,
    agent_run_id: str,
    overlay_skill_path: Path,
    skill_md_sha256: str,
) -> str:
    validations = "\n".join(
        f"- `{command}`" for command in scenario.get("validation_commands", [])
    )
    fixture_files = scenario.get("fixture_files", [])
    fixture_lines = (
        "\n".join(f"- `{fixture_file}`" for fixture_file in fixture_files)
        if fixture_files
        else "_(none declared)_"
    )
    expected_findings = scenario.get("expected_findings", [])
    expected_lines = (
        "\n".join(
            f"- `{item['axis']}`: one of `{item['allowed_verdicts']}`"
            for item in expected_findings
        )
        if expected_findings
        else "_(none declared)_"
    )
    return f"""# Held-Out Candidate Scenario

Scenario: `{scenario["id"]}`
Skill: `{skill_name}`

## Required First Action

Read `{overlay_skill_path}` first. Do not read the repository base skill for
this run. Follow the candidate overlay as the authoritative skill definition.

## Task

{scenario["description"]}

## Fixture Files

{fixture_lines}

Review only the declared fixture inputs for the scenario. Treat them as an
isolated change set; do not substitute the current working-tree diff.

## Expected Evidence Shape

{expected_lines}

## Validation Commands

{validations}

## Pass Criteria

{scenario["pass_criteria"]}

## Trace Requirement

Record one SkillTrial containing these exact identities:
- `skill_name`: `{skill_name}`
- `candidate_id`: `{candidate_id}`
- `agent_run_id`: `{agent_run_id}`
- `task_fixture_id`: `{scenario["id"]}`
- `baseline_or_candidate`: `candidate`
- `skill_md_sha256`: `{skill_md_sha256}`

Also record non-zero token, turn, and duration metrics; runner provenance; a
runner output hash; exact validation commands, exit codes, and stdout hashes.
Set `functional_verification=pass` and `outcome=pass` only when the scenario's
behavioral pass criteria are actually satisfied. Do not edit runtime business
paths while validating a skill candidate.
"""


def generate_held_out_candidate_packets(
    skill_name: str,
    candidate_overlay_path: Path,
    *,
    out_dir: Path = DEFAULT_OUT_DIR,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Generate one fresh-agent packet for every candidate held-out scenario."""
    overlay = candidate_overlay_path.resolve()
    metadata_path = overlay / ".candidate.json"
    if not metadata_path.is_file():
        raise FileNotFoundError(f"candidate overlay metadata not found: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("skill_name") != skill_name:
        raise ValueError("candidate overlay skill_name does not match requested skill")

    candidate_id = metadata.get("candidate_id", "")
    skill_md_sha256 = metadata.get("skill_md_sha256", "")
    if not candidate_id or not skill_md_sha256:
        raise ValueError("candidate overlay metadata lacks identity or skill hash")
    overlay_skill_path = overlay / skill_name / "SKILL.md"
    if not overlay_skill_path.is_file():
        raise FileNotFoundError(f"candidate overlay skill not found: {overlay_skill_path}")

    suite_path = HELD_OUT_DIR / skill_name / "suite.json"
    if not suite_path.is_file():
        raise FileNotFoundError(f"held-out suite not found: {suite_path}")
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    scenarios = suite.get("scenarios", [])
    if not scenarios:
        raise ValueError(f"held-out suite has no scenarios: {suite_path}")

    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("candidate-%Y%m%d-%H%M%S")
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    packets: list[dict[str, str]] = []
    for index, scenario in enumerate(scenarios, 1):
        agent_run_id = f"{run_id}-{index:02d}"
        rel = Path(run_id) / f"held-out-{index:02d}.md"
        packet_path = out_dir / rel
        packet_path.write_text(
            _held_out_candidate_packet_text(
                skill_name=skill_name,
                scenario=scenario,
                candidate_id=candidate_id,
                agent_run_id=agent_run_id,
                overlay_skill_path=overlay_skill_path,
                skill_md_sha256=skill_md_sha256,
            ),
            encoding="utf-8",
        )
        packets.append({
            "scenario_id": scenario["id"],
            "agent_run_id": agent_run_id,
            "packet_path": str(rel),
        })

    manifest = {
        "run_id": run_id,
        "fixture_type": "held-out-candidate",
        "skill_name": skill_name,
        "candidate_id": candidate_id,
        "candidate_overlay_path": str(overlay),
        "skill_md_sha256": skill_md_sha256,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "packets": packets,
    }
    (run_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate fresh-agent strategy packets")
    parser.add_argument("fixture", type=Path, nargs="?")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--held-out-skill", default="")
    parser.add_argument("--candidate-overlay", type=Path)
    args = parser.parse_args()

    if args.held_out_skill:
        if args.candidate_overlay is None:
            parser.error("--candidate-overlay is required with --held-out-skill")
        manifest = generate_held_out_candidate_packets(
            args.held_out_skill,
            args.candidate_overlay,
            out_dir=args.out_dir,
            run_id=args.run_id,
        )
    else:
        if args.fixture is None:
            parser.error("fixture is required unless --held-out-skill is used")
        manifest = generate_strategy_packets(args.fixture, args.out_dir, args.run_id)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
