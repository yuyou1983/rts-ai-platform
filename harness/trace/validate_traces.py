#!/usr/bin/env python3
"""校验 harness/trace/trials/ 下的 JSONL 文件是否符合 SkillTrial schema。

用法: python3 harness/trace/validate_traces.py [--strict]
  --strict: 也检查 silent_bypass_detected 字段一致性
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TRIALS_DIR = REPO_ROOT / "harness" / "trace" / "trials"

REQUIRED_FIELDS = [
    "task_id", "task_description", "skill_name", "outcome",
    "skill_md_read", "primary_action_invoked",
    "tool_calls", "validation_commands_run", "validation_results",
    "token_count", "turn_count", "duration_seconds",
    "touched_files", "silent_bypass_detected", "timestamp",
    # v2 required fields
    "schema_version",
    "skill_version",
    "candidate_id",
    "agent_run_id",
    "task_fixture_id",
    "baseline_or_candidate",
    "primary_script_called",
    "functional_verification",
    "failure_log_summary",
    "validation_exit_codes",
    "validation_stdout_hashes",
    "validation_stderr_summaries",
    "silent_bypass_details",
]

VALID_OUTCOMES = {"pass", "fail", "error", "timeout"}


def infer_silent_bypass(d: dict) -> list[str]:
    """Infer silent-bypass signals from a trial record."""
    details: list[str] = []
    if not d.get("skill_md_read", False):
        details.append("skill_md_read false")
    if not d.get("primary_action_invoked", False):
        details.append("primary_action_invoked false")
    if not d.get("validation_commands_run", []):
        details.append("validation_commands_run empty")
    if d.get("outcome") == "pass" and d.get("functional_verification") == "skip":
        details.append("pass outcome with skipped functional_verification")
    return details


def validate_file(path: Path, strict: bool = False) -> list[str]:
    """校验单个 JSONL 文件，返回问题列表。"""
    issues: list[str] = []
    lines = path.read_text().splitlines()
    for line_no, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError as e:
            issues.append(f"{path.name}:{line_no}: invalid JSON: {e}")
            continue

        # Treat missing schema_version as v1; relax required fields for v1
        schema_ver = d.get("schema_version", 1)
        if schema_ver < 2:
            # Only check v1 required fields for v1 records
            v1_fields = [
                "task_id", "task_description", "skill_name", "outcome",
                "skill_md_read", "primary_action_invoked",
                "tool_calls", "validation_commands_run", "validation_results",
                "token_count", "turn_count", "duration_seconds",
                "touched_files", "silent_bypass_detected", "timestamp",
            ]
            for f in v1_fields:
                if f not in d:
                    issues.append(f"{path.name}:{line_no}: missing '{f}' (v1 record)")
        else:
            # Full v2 required-field check
            for f in REQUIRED_FIELDS:
                if f not in d:
                    issues.append(f"{path.name}:{line_no}: missing '{f}'")

        # 检查 outcome 值
        outcome = d.get("outcome", "")
        if outcome and outcome not in VALID_OUTCOMES:
            issues.append(f"{path.name}:{line_no}: invalid outcome '{outcome}'")

        # 检查 task_description 非空
        desc = d.get("task_description", "")
        if not desc:
            issues.append(f"{path.name}:{line_no}: empty task_description")

        # strict 模式: 检查 silent_bypass 一致性
        if strict and "silent_bypass_details" in d:
            if not d.get("silent_bypass_detected") and d["silent_bypass_details"]:
                issues.append(
                    f"{path.name}:{line_no}: silent_bypass_detected=False but has details"
                )

        # strict 模式: 推断 silent_bypass
        if strict:
            inferred = infer_silent_bypass(d)
            if inferred and not d.get("silent_bypass_detected", False):
                issues.append(
                    f"{path.name}:{line_no}: silent_bypass_inferred but field is false: {inferred}"
                )

    return issues


def validate_all(strict: bool = False) -> list[str]:
    """校验所有 trial 文件。"""
    if not TRIALS_DIR.exists():
        return []  # 无 trial 文件不算错

    issues: list[str] = []
    for f in sorted(TRIALS_DIR.glob("*.jsonl")):
        issues.extend(validate_file(f, strict))
    return issues


def main() -> int:
    strict = "--strict" in sys.argv
    issues = validate_all(strict)
    if issues:
        print(f"FAIL — {len(issues)} issue(s):")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("OK — all trace files pass validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
