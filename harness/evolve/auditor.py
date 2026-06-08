"""auditor.py — Independent Structured Auditor for skill patch candidates.

Runs a battery of deterministic checks against a proposed skill patch
before it is allowed to proceed to held-out validation.  This is the
Phase-5 "independent auditor" from the skill-evolution paper, extracted
into its own module so it can be unit-tested and extended independently.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


RUNTIME_BUSINESS_PREFIXES = ("simcore/", "agents/", "godot/scripts/")


@dataclass
class StructuredAuditResult:
    """Result of a structured audit check on a candidate patch."""

    accepted: bool
    issues: list[str] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)


def audit_candidate_patch(
    skill_name: str,
    patch_content: str,
    skill_md_content: str,
    evidence: dict[str, Any] | None = None,
) -> StructuredAuditResult:
    """Audit a candidate skill patch and return a structured result.

    Parameters
    ----------
    skill_name:
        Name of the skill being patched (e.g. ``"godot-specialist"``).
    patch_content:
        The proposed patch text that would be appended to SKILL.md.
    skill_md_content:
        The current content of the SKILL.md (used to check for
        validation_commands, expected_tool_calls, etc.).
    evidence:
        Optional dict of evidence from the trial run, e.g.
        ``{"touched_files": [...], "task_fixture_id": "..."}``.

    Returns
    -------
    StructuredAuditResult
        ``accepted`` is ``True`` only when *no* issues were found.
    """
    evidence = evidence or {}
    issues: list[str] = []
    patch_lower = patch_content.lower()
    skill_lower = skill_md_content.lower()

    # ── Runtime business code checks ────────────────────────────
    touched_files = evidence.get("touched_files", [])
    if any(str(path).startswith(RUNTIME_BUSINESS_PREFIXES) for path in touched_files):
        issues.append("runtime_business_code_target")

    if any(prefix in patch_content for prefix in RUNTIME_BUSINESS_PREFIXES):
        issues.append("runtime_business_code_instruction")

    # ── Hardcoded values ────────────────────────────────────────
    if re.search(r"seed\s*[=:]\s*\d+", patch_lower):
        issues.append("hardcoded_seed")

    if re.search(r"entity_[a-z]+_\d+", patch_lower):
        issues.append("hardcoded_entity_id")

    # ── Fixture-specific rules ──────────────────────────────────
    task_fixture_id = str(evidence.get("task_fixture_id", ""))
    if task_fixture_id and task_fixture_id.lower() in patch_lower:
        issues.append("fixture_specific_rule")

    # ── Must / Always without validation evidence ───────────────
    # NOTE: The legacy audit_patch() in skill_evolver.py already checks
    # must/never with a registry fallback.  To avoid double-reporting
    # the same issue without the registry context, the structured
    # auditor only flags this when called standalone (i.e. when
    # *not* invoked via audit_patch).  We detect this by checking
    # whether the caller passed a non-empty evidence dict with a
    # ``_from_audit_patch`` sentinel — but since we want the auditor
    # to be usable independently too, we keep the check here and
    # handle de-duplication at the wiring layer.
    if "always" in patch_lower or "must" in patch_lower or "必须" in patch_content:
        if "validation_commands" not in skill_lower and "expected_tool_calls" not in skill_lower:
            issues.append("unsupported_must_without_validation_evidence")

    # ── SimCore-specific: no LLM in high-frequency loop ─────────
    if "simcore" in skill_name and ("llm" in patch_lower or "chat.completions" in patch_lower):
        issues.append("llm_in_simcore_loop")

    # ── Godot-specific: must include static or manifest validation ─
    if "godot" in skill_name and "check-only" not in patch_lower and "verify_presentation_scene.py" not in patch_lower and "manifest validation" not in patch_lower:
        issues.append("godot_patch_missing_static_or_manifest_validation")

    return StructuredAuditResult(
        accepted=not issues,
        issues=issues,
        evidence=evidence,
    )
