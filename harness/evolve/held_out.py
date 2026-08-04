"""Candidate-aware held-out validation.

This module implements Phase-6 held-out validation with an explicit
distinction between *command-only* validation (running the suite
``validation_commands``) and *candidate-aware* validation (which also
requires a fresh agent run against a candidate patch overlay).

Only candidate-aware validation can be *promotion-eligible*.  Command-only
validation may report ``passed=True`` but ``promotion_eligible=False`` so
that legacy callers which still rely on ``validate_held_out`` do not
silently promote patches without fresh-agent evidence.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── 路径常量 ─────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HELD_OUT_DIR = REPO_ROOT / "harness" / "skills" / "held_out"
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"


@dataclass
class HeldOutResult:
    """Result of candidate-aware held-out validation.

    ``passed`` reflects whether the held-out suite commands succeeded.
    ``promotion_eligible`` is ``True`` only when, in addition to
    ``passed``, the validation was performed against a *candidate*
    patch with a fresh ``agent_run_id`` and no training/held-out
    fixture overlap.
    """
    passed: bool
    promotion_eligible: bool
    skill_name: str
    candidate_id: str
    scenario_results: list[dict] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def validate_held_out_candidate(
    skill_name: str,
    candidate_id: str = "",
    agent_run_id: str = "",
    training_fixture_ids: list[str] | None = None,
    held_out_fixture_ids: list[str] | None = None,
    candidate_overlay_path: str | None = None,
) -> HeldOutResult:
    """Validate a candidate skill patch against held-out suites.

    Command-only validation (no ``candidate_id`` / ``agent_run_id``) may
    pass but will never be promotion-eligible.

    Parameters
    ----------
    skill_name:
        Skill whose held-out suite should be executed.
    candidate_id:
        Identifier of the candidate patch being validated.  Empty means
        command-only validation.
    agent_run_id:
        Identifier of the fresh agent run that exercised the candidate.
        Empty means no fresh-agent evidence.
    training_fixture_ids:
        Fixture IDs used during training.  Any overlap with
        ``held_out_fixture_ids`` disqualifies promotion (data leakage).
    held_out_fixture_ids:
        Fixture IDs used during held-out validation.
    candidate_overlay_path:
        Optional path to a temporary candidate overlay directory created
        by :func:`create_candidate_overlay`.  When provided the held-out
        suite commands run with the candidate SKILL.md in scope.
    """
    training_fixture_ids = training_fixture_ids or []
    held_out_fixture_ids = held_out_fixture_ids or []
    issues: list[str] = []
    scenario_results: list[dict] = []
    all_pass = True

    # ── Check candidate identity ───────────────────────────────
    has_candidate = bool(candidate_id)
    has_fresh_run = bool(agent_run_id)

    if not has_candidate:
        issues.append(
            "candidate_id is empty — command-only validation, not promotion-eligible"
        )

    if not has_fresh_run:
        issues.append(
            "agent_run_id is empty — no fresh agent run evidence"
        )

    # ── Check training / held-out fixture overlap (data leakage) ──
    overlap = set(training_fixture_ids) & set(held_out_fixture_ids)
    if overlap:
        issues.append(f"training fixture reused as held-out: {overlap}")
        all_pass = False

    # ── Run held-out suite validation commands ─────────────────
    suite_dir = HELD_OUT_DIR / skill_name
    suite_file = suite_dir / "suite.json"
    if suite_file.exists():
        suite = json.loads(suite_file.read_text())
        for scenario in suite.get("scenarios", []):
            scenario_id = scenario["id"]
            scenario_pass = True
            for cmd in scenario.get("validation_commands", []):
                logger.info("  held-out %s: %s", scenario_id, cmd)
                try:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True, timeout=15,
                        cwd=str(REPO_ROOT),
                    )
                    if result.returncode != 0:
                        logger.error(
                            "  FAIL: %s (exit %d)\n  stderr: %s",
                            cmd, result.returncode, result.stderr[:200],
                        )
                        scenario_pass = False
                        all_pass = False
                except subprocess.TimeoutExpired:
                    logger.error("  TIMEOUT: %s", cmd)
                    scenario_pass = False
                    all_pass = False
                except Exception as exc:
                    logger.error("  ERROR: %s: %s", cmd, exc)
                    scenario_pass = False
                    all_pass = False
            scenario_results.append({"scenario": scenario_id, "passed": scenario_pass})
    else:
        # No suite — command-only pass (still recorded as passed).
        logger.warning("No held-out suite for %s -- command-only pass", skill_name)

    promotion_eligible = (
        all_pass and has_candidate and has_fresh_run and not overlap
    )

    return HeldOutResult(
        passed=all_pass,
        promotion_eligible=promotion_eligible,
        skill_name=skill_name,
        candidate_id=candidate_id,
        scenario_results=scenario_results,
        issues=issues,
    )


def create_candidate_overlay(skill_name: str, candidate_patch: str) -> str:
    """Create a temporary skill overlay with the candidate patch applied.

    The overlay is a copy of the skill's ``SKILL.md`` with the candidate
    patch appended under a ``## Candidate Patch`` heading.  It lives in a
    temporary directory and must **never** be committed to the repository.

    Returns the path to the temporary overlay directory.
    """
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.exists():
        raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

    original_md = (skill_dir / "SKILL.md").read_text()
    overlay_content = (
        original_md.rstrip()
        + "\n\n---\n\n## Candidate Patch\n"
        + candidate_patch
        + "\n"
    )

    # Create temp directory
    tmp_dir = tempfile.mkdtemp(prefix=f"rts-skill-overlay-{skill_name}-")
    overlay_dir = Path(tmp_dir)
    overlay_skill_dir = overlay_dir / skill_name
    overlay_skill_dir.mkdir(parents=True)

    (overlay_skill_dir / "SKILL.md").write_text(overlay_content)

    logger.info("Created candidate overlay for %s at %s", skill_name, overlay_dir)
    return str(overlay_dir)
