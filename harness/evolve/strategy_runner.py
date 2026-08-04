from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / "harness/skills/candidates/strategy_runs"


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


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate fresh-agent strategy packets")
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    manifest = generate_strategy_packets(args.fixture, args.out_dir, args.run_id)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
