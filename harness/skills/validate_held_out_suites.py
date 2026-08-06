#!/usr/bin/env python3
"""Validate every held-out suite.json under harness/skills/held_out/.

Checks performed:
  1. Each suite.json validates against held_out/schema.json.
  2. Each suite has at least two scenarios.
  3. Every scenario id starts with "held-out/".
  4. Scenario ids are unique within each suite.
  5. Every scenario has at least one validation command and pass_criteria.
  6. No scenario relies SOLELY on file-existence or import-only checks
     (those are not behavioral and would silently bypass the skill).

Usage: python3 harness/skills/validate_held_out_suites.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
HELD_OUT_DIR = REPO_ROOT / "harness" / "skills" / "held_out"
SCHEMA_PATH = HELD_OUT_DIR / "schema.json"


# ─── command classification ──────────────────────────────────────
def _is_existence_only(cmd: str) -> bool:
    """True for file-existence or directory-listing commands."""
    c = cmd.strip().lower()
    return c.startswith("test -f") or c.startswith("test -d") or c.startswith("ls ")


def _is_import_only(cmd: str) -> bool:
    """True for ``python3 -c "import X"`` / ``from X import Y; print(...)``.

    A command is import-only when it executes a ``python3 -c`` snippet whose
    body does nothing beyond importing modules and printing a literal — i.e.
    no ``assert``, no instantiation/call that exercises behavior, and no
    subprocess/file interaction.
    """
    c = cmd.strip()
    if not (c.startswith("python3") or c.startswith("python")):
        return False
    # Pull out the -c argument (single or double quoted).
    m = re.search(r"""-c\s+(?:"([^"]*)"|'([^']*)')""", c)
    if not m:
        return False
    snippet = (m.group(1) or m.group(2) or "").strip()
    if not snippet:
        return False
    # Any assert counts as behavioral.
    if "assert" in snippet:
        return False
    # Strip import statements entirely (from X import Y / import X).
    body = re.sub(r"\bfrom\s+\S+\s+import\s+[^\n;]+", "", snippet)
    body = re.sub(r"\bimport\s+[^\n;]+", "", body)
    # Strip print(...) calls and pass / literals.
    body = re.sub(r"\bprint\([^)]*\)", "", body)
    body = re.sub(r"['\"][^'\"]*['\"]", "", body)
    body = re.sub(r"\b\d+(?:\.\d+)?\b", "", body)
    body = re.sub(r"\bpass\b", "", body)
    # Remove punctuation / whitespace.
    for ch in (" ", "\t", "\n", ";", ",", ".", "=", "(", ")", "[", "]", "{", "}"):
        body = body.replace(ch, "")
    # If nothing meaningful remains, it was import/print only.
    return body == ""


def _is_weak_command(cmd: str) -> bool:
    """A command is 'weak' if it only proves existence or importability."""
    return _is_existence_only(cmd) or _is_import_only(cmd)


def _suite_is_weak(scenario: dict) -> bool:
    cmds = scenario.get("validation_commands", [])
    if not cmds:
        return False  # handled by schema
    return all(_is_weak_command(c) for c in cmds)


# ─── validation ──────────────────────────────────────────────────
def _load_suites() -> list[tuple[Path, dict]]:
    suites: list[tuple[Path, dict]] = []
    for path in sorted(HELD_OUT_DIR.rglob("suite.json")):
        if path.parent.name == "held_out":
            continue  # skip the schema dir itself if any
        suites.append((path, json.loads(path.read_text())))
    return suites


def validate() -> list[str]:
    """Return a list of issue strings; empty list means all suites pass."""
    issues: list[str] = []

    if not SCHEMA_PATH.exists():
        return [f"schema.json not found: {SCHEMA_PATH}"]
    if not HELD_OUT_DIR.exists():
        return [f"held_out directory not found: {HELD_OUT_DIR}"]

    schema = json.loads(SCHEMA_PATH.read_text())

    try:
        import jsonschema
    except ImportError:
        issues.append(
            "jsonschema not installed — skipping schema validation "
            "(pip install jsonschema)"
        )
        jsonschema = None

    suites = _load_suites()
    if not suites:
        return ["no suite.json files found under harness/skills/held_out/"]

    for path, suite in suites:
        rel = path.relative_to(REPO_ROOT)

        # 1. Schema validation.
        if jsonschema is not None:
            try:
                jsonschema.validate(suite, schema)
            except jsonschema.ValidationError as e:
                issues.append(f"{rel}: schema violation: {e.message}")
                continue

        # 2. At least two scenarios (also enforced by schema, but be explicit).
        scenarios = suite.get("scenarios", [])
        if len(scenarios) < 2:
            issues.append(
                f"{rel}: needs >= 2 scenarios (found {len(scenarios)})"
            )

        # 3. + 4. ID prefix and uniqueness.
        ids = [s.get("id", "") for s in scenarios]
        for sid in ids:
            if not sid.startswith("held-out/"):
                issues.append(
                    f"{rel}/{sid}: scenario id must start with 'held-out/'"
                )
        if len(ids) != len(set(ids)):
            dupes = [i for i in ids if ids.count(i) > 1]
            issues.append(f"{rel}: duplicate scenario ids: {sorted(set(dupes))}")

        # 5. validation_commands + pass_criteria presence (schema-enforced
        #    but emit a clearer message).
        for s in scenarios:
            sid = s.get("id", "?")
            if not s.get("validation_commands"):
                issues.append(
                    f"{rel}/{sid}: needs at least one validation command"
                )
            if not s.get("pass_criteria"):
                issues.append(f"{rel}/{sid}: needs pass_criteria")
            for fixture_file in s.get("fixture_files", []):
                fixture_path = (REPO_ROOT / fixture_file).resolve()
                if (
                    Path(fixture_file).is_absolute()
                    or not fixture_path.is_relative_to(REPO_ROOT.resolve())
                    or not fixture_path.is_file()
                ):
                    issues.append(
                        f"{rel}/{sid}: fixture file missing or not repository-relative: "
                        f"{fixture_file}"
                    )
            expected_files = [
                REPO_ROOT / fixture_file
                for fixture_file in s.get("fixture_files", [])
                if fixture_file.endswith("/expected.json")
            ]
            if expected_files and s.get("expected_findings"):
                expected = json.loads(expected_files[0].read_text(encoding="utf-8"))
                declared = {
                    item["axis"]: item["allowed_verdicts"]
                    for item in s["expected_findings"]
                }
                if declared != expected:
                    issues.append(
                        f"{rel}/{sid}: expected_findings drift from "
                        f"{expected_files[0].relative_to(REPO_ROOT)}"
                    )

        # 6. No sole existence/import checks.
        for s in scenarios:
            sid = s.get("id", "?")
            cmds = s.get("validation_commands", [])
            if cmds and all(_is_weak_command(c) for c in cmds):
                weak = [c for c in cmds if _is_weak_command(c)]
                issues.append(
                    f"{rel}/{sid}: relies solely on existence/import check(s) "
                    f"{weak} — add a behavioral command"
                )

    return issues


def main() -> int:
    issues = validate()
    if issues:
        print(f"FAIL — {len(issues)} issue(s):")
        for i in issues:
            print(f"  - {i}")
        return 1
    print("OK — all held-out suites pass validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
