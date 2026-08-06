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

import hashlib
import json
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from harness.trace.schema import SkillTrial, validate_candidate_trial

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
    agent_run_ids: list[str] = field(default_factory=list)
    held_out_fixture_ids: list[str] = field(default_factory=list)
    candidate_overlay_path: str = ""
    candidate_patch_sha256: str = ""
    candidate_trials: list[SkillTrial] = field(default_factory=list, repr=False)
    training_fixture_ids: list[str] = field(default_factory=list)


def _sha256_text(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def candidate_id_for_patch(skill_name: str, candidate_patch: str) -> str:
    """Return the stable identity for one skill patch.

    Caller-provided labels are not identities. Binding the skill name and exact
    patch text prevents evidence from one candidate being reused for another.
    """
    payload = f"{skill_name}\0{candidate_patch}"
    return "cand-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def validate_candidate_overlay(
    overlay_path: str | None,
    *,
    skill_name: str,
    candidate_id: str,
) -> tuple[dict, list[str]]:
    if not overlay_path:
        return {}, ["candidate overlay is required for promotion evidence"]

    overlay = Path(overlay_path)
    metadata_path = overlay / ".candidate.json"
    skill_md_path = overlay / skill_name / "SKILL.md"
    issues: list[str] = []
    if not metadata_path.is_file():
        issues.append(f"candidate overlay metadata missing: {metadata_path}")
    if not skill_md_path.is_file():
        issues.append(f"candidate overlay SKILL.md missing: {skill_md_path}")
    if issues:
        return {}, issues

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {}, [f"candidate overlay metadata is invalid: {exc}"]

    if metadata.get("skill_name") != skill_name:
        issues.append("candidate overlay skill_name does not match requested skill")
    if metadata.get("candidate_id") != candidate_id:
        issues.append("candidate overlay candidate_id does not match requested candidate")
    actual_skill_hash = _sha256_text(skill_md_path.read_text(encoding="utf-8"))
    if metadata.get("skill_md_sha256") != actual_skill_hash:
        issues.append("candidate overlay SKILL.md hash does not match metadata")
    return metadata, issues


def validate_held_out_candidate(
    skill_name: str,
    candidate_id: str = "",
    agent_run_id: str = "",
    training_fixture_ids: list[str] | None = None,
    held_out_fixture_ids: list[str] | None = None,
    candidate_overlay_path: str | None = None,
    candidate_trials: list[SkillTrial] | None = None,
) -> HeldOutResult:
    """Validate a candidate skill patch against held-out suites.

    Command-only validation (no ``candidate_id`` / ``agent_run_id``) may
    pass but will never be promotion-eligible.

    Parameters
    ----------
    skill_name:
        Skill whose held-out suite should be executed.
    candidate_id:
        Derived identifier of the candidate patch being validated. Empty means
        command-only validation; caller labels alone never establish identity.
    agent_run_id:
        Deprecated compatibility field. A string without a matching
        ``candidate_trials`` row is not fresh-agent evidence.
    training_fixture_ids:
        Fixture IDs used during training.  Any overlap with
        ``held_out_fixture_ids`` disqualifies promotion (data leakage).
    held_out_fixture_ids:
        Fixture IDs used during held-out validation.
    candidate_overlay_path:
        Path to the temporary candidate overlay created by
        :func:`create_candidate_overlay`. Required for candidate promotion.
    """
    training_fixture_ids = training_fixture_ids or []
    held_out_fixture_ids = held_out_fixture_ids or []
    candidate_trials = candidate_trials or []
    issues: list[str] = []
    scenario_results: list[dict] = []
    all_pass = True

    # ── Check candidate identity ───────────────────────────────
    has_candidate = bool(candidate_id)
    has_fresh_run = bool(candidate_trials)

    if not has_candidate:
        issues.append(
            "candidate_id is empty — command-only validation, not promotion-eligible"
        )

    if not has_fresh_run:
        issues.append(
            "no fresh candidate SkillTrial evidence with agent_run_id was supplied"
        )
        if agent_run_id:
            issues.append(
                "agent_run_id without a matching candidate SkillTrial is not evidence"
            )

    overlay_metadata: dict = {}
    overlay_issues: list[str] = []
    if has_candidate:
        overlay_metadata, overlay_issues = validate_candidate_overlay(
            candidate_overlay_path,
            skill_name=skill_name,
            candidate_id=candidate_id,
        )
        issues.extend(overlay_issues)

    # Preserve the explicit caller overlap check for early diagnostics. The
    # suite-derived check below remains authoritative for promotion.
    declared_overlap = set(training_fixture_ids) & set(held_out_fixture_ids)
    if declared_overlap:
        issues.append(
            f"training fixture reused as held-out: {sorted(declared_overlap)}"
        )
        all_pass = False

    # ── Check training / held-out fixture overlap (data leakage) ──
    # ── Run held-out suite validation commands ─────────────────
    suite_dir = HELD_OUT_DIR / skill_name
    suite_file = suite_dir / "suite.json"
    scenario_ids: list[str] = []
    if suite_file.exists():
        suite = json.loads(suite_file.read_text(encoding="utf-8"))
        scenarios = suite.get("scenarios", [])
        if not scenarios:
            issues.append("held-out suite contains no scenarios")
            all_pass = False
        scenario_ids = [scenario.get("id", "") for scenario in scenarios]
        command_env = os.environ.copy()
        if candidate_overlay_path:
            command_env["RTS_SKILL_OVERLAY"] = str(Path(candidate_overlay_path).resolve())
            command_env["RTS_CANDIDATE_ID"] = candidate_id
        for scenario in scenarios:
            scenario_id = scenario["id"]
            scenario_pass = True
            for cmd in scenario.get("validation_commands", []):
                logger.info("  held-out %s: %s", scenario_id, cmd)
                try:
                    result = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True, timeout=15,
                        cwd=str(REPO_ROOT),
                        env=command_env,
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
        logger.warning("No held-out suite for %s", skill_name)
        issues.append(f"held-out suite missing for skill: {skill_name}")
        all_pass = False

    # The suite itself is the source of held-out fixture identity. Caller input
    # may only confirm it; it cannot replace or narrow the suite.
    suite_fixture_ids = set(scenario_ids)
    scenarios_by_id = {
        scenario.get("id", ""): scenario
        for scenario in scenarios
    } if suite_file.exists() else {}
    if held_out_fixture_ids and set(held_out_fixture_ids) != suite_fixture_ids:
        issues.append("held_out_fixture_ids do not exactly match the suite scenarios")
    effective_held_out_ids = suite_fixture_ids
    overlap = declared_overlap | (set(training_fixture_ids) & effective_held_out_ids)
    if overlap:
        issues.append(f"training fixture reused as held-out: {sorted(overlap)}")
        all_pass = False

    evidence_ok = has_candidate and has_fresh_run and not overlay_issues
    valid_fixtures: set[str] = set()
    agent_run_ids: list[str] = []
    overlay_skill_hash = overlay_metadata.get("skill_md_sha256", "")
    expected_overlay_skill_path = ""
    if candidate_overlay_path:
        expected_overlay_skill_path = str(
            (Path(candidate_overlay_path) / skill_name / "SKILL.md").resolve()
        )
    for trial in candidate_trials:
        trial_issues = validate_candidate_trial(trial)
        if trial.skill_name != skill_name:
            trial_issues.append(
                f"candidate trial skill_name mismatch: {trial.skill_name!r}"
            )
        if trial.candidate_id != candidate_id:
            trial_issues.append(
                f"candidate trial candidate_id mismatch: {trial.candidate_id!r}"
            )
        if trial.task_fixture_id not in suite_fixture_ids:
            trial_issues.append(
                f"candidate trial fixture is not in held-out suite: {trial.task_fixture_id!r}"
            )
        if trial.skill_md_sha256 != overlay_skill_hash:
            trial_issues.append("candidate trial skill_md_sha256 does not match overlay")
        if not trial.tool_calls:
            trial_issues.append("candidate trial recorded no tool calls")
        else:
            first_call = trial.tool_calls[0]
            args_summary = str(first_call.get("args_summary", ""))
            if expected_overlay_skill_path not in args_summary:
                trial_issues.append(
                    "candidate trial first tool call did not read the exact overlay SKILL.md"
                )
        scenario = scenarios_by_id.get(trial.task_fixture_id, {})
        for expected in scenario.get("expected_findings", []):
            expected_axis = str(expected.get("axis", ""))
            allowed_verdicts = {
                str(verdict).upper()
                for verdict in expected.get("allowed_verdicts", [])
            }
            matching_findings = [
                finding
                for finding in trial.findings
                if str(finding.get("axis", "")).casefold()
                == expected_axis.casefold()
            ]
            if not any(
                str(finding.get("verdict", "")).upper() in allowed_verdicts
                for finding in matching_findings
            ):
                trial_issues.append(
                    f"expected {expected_axis} verdict in "
                    f"{sorted(allowed_verdicts)}"
                )
        if trial_issues:
            evidence_ok = False
            issues.extend(
                f"trial {trial.agent_run_id or '<missing-run-id>'}: {issue}"
                for issue in trial_issues
            )
        else:
            valid_fixtures.add(trial.task_fixture_id)
        agent_run_ids.append(trial.agent_run_id)

    nonempty_run_ids = [run_id for run_id in agent_run_ids if run_id]
    if len(nonempty_run_ids) != len(set(nonempty_run_ids)):
        issues.append("candidate trials must use unique agent_run_id values")
        evidence_ok = False

    missing_fixtures = suite_fixture_ids - valid_fixtures
    if missing_fixtures:
        issues.extend(
            f"missing valid fresh-agent evidence for held-out fixture: {fixture_id}"
            for fixture_id in sorted(missing_fixtures)
        )
        evidence_ok = False

    promotion_eligible = (
        all_pass
        and evidence_ok
        and not overlap
        and (not held_out_fixture_ids or set(held_out_fixture_ids) == suite_fixture_ids)
    )

    return HeldOutResult(
        passed=all_pass,
        promotion_eligible=promotion_eligible,
        skill_name=skill_name,
        candidate_id=candidate_id,
        scenario_results=scenario_results,
        issues=issues,
        agent_run_ids=agent_run_ids,
        held_out_fixture_ids=sorted(suite_fixture_ids),
        candidate_overlay_path=candidate_overlay_path or "",
        candidate_patch_sha256=overlay_metadata.get("patch_sha256", ""),
        candidate_trials=list(candidate_trials),
        training_fixture_ids=list(training_fixture_ids),
    )


def create_candidate_overlay(
    skill_name: str,
    candidate_patch: str,
    candidate_id: str | None = None,
) -> str:
    """Create a temporary skill overlay with the candidate patch applied.

    The overlay is a copy of the skill's ``SKILL.md`` with the candidate
    patch appended under a ``## Candidate Patch`` heading.  It lives in a
    temporary directory and must **never** be committed to the repository.

    Returns the path to the temporary overlay directory.
    """
    skill_dir = SKILLS_DIR / skill_name
    if not skill_dir.exists():
        raise FileNotFoundError(f"Skill directory not found: {skill_dir}")

    original_md = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
    derived_candidate_id = candidate_id_for_patch(skill_name, candidate_patch)
    if candidate_id is not None and candidate_id != derived_candidate_id:
        raise ValueError(
            "candidate_id does not match the skill name and candidate patch"
        )
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

    (overlay_skill_dir / "SKILL.md").write_text(overlay_content, encoding="utf-8")
    metadata = {
        "schema_version": 1,
        "candidate_id": derived_candidate_id,
        "skill_name": skill_name,
        "patch_sha256": _sha256_text(candidate_patch),
        "base_skill_md_sha256": _sha256_text(original_md),
        "skill_md_sha256": _sha256_text(overlay_content),
    }
    (overlay_dir / ".candidate.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info("Created candidate overlay for %s at %s", skill_name, overlay_dir)
    return str(overlay_dir)
