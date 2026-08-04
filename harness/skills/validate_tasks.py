#!/usr/bin/env python3
"""Validate task fixtures under harness/skills/tasks against schema.json.

A "vertical ticket" is a self-contained fixture that carries its own source
specification, dependency graph (blocked_by), acceptance criteria, verification
seams, evidence outputs, and lifecycle status. This validator enforces both the
JSON schema and a set of cross-fixture graph invariants that the schema alone
cannot express:

  1. Each fixture validates against harness/skills/tasks/schema.json.
  2. Every ``blocked_by`` entry references a known fixture id.
  3. The ``blocked_by`` graph is acyclic (DFS).
  4. A fixture whose status is ``ready`` may only depend on ``done`` blockers.
  5. ``source_spec`` is a repository-relative path that exists on disk and does
     not escape the repository.
  6. No fixture lists a path under harness/skills/tasks in its own
     ``forbidden_paths`` (a ticket must not forbid the fixture graph itself).

Usage: python3 harness/skills/validate_tasks.py
Exit 0 on success (prints "OK - all task fixtures pass validation").
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TASKS_DIR = REPO_ROOT / "harness" / "skills" / "tasks"
SCHEMA_PATH = TASKS_DIR / "schema.json"


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _load_fixtures() -> list[tuple[Path, dict]]:
    """Load every *.json fixture below TASKS_DIR, excluding schema.json."""
    fixtures: list[tuple[Path, dict]] = []
    for path in sorted(TASKS_DIR.rglob("*.json")):
        if path.name == "schema.json":
            continue
        fixtures.append((path, json.loads(path.read_text())))
    return fixtures


def _validate_schema(fixtures: list[tuple[Path, dict]]) -> list[str]:
    issues: list[str] = []
    try:
        import jsonschema
    except ImportError:
        issues.append(
            "jsonschema not installed — schema validation skipped "
            "(pip install jsonschema)"
        )
        return issues

    schema = _load_schema()
    for path, fixture in fixtures:
        try:
            jsonschema.validate(fixture, schema)
        except jsonschema.ValidationError as e:
            issues.append(f"{path.name}: schema violation — {e.message}")
    return issues


def _fixture_id(fixture: dict, path: Path) -> str:
    """Canonical fixture identifier: the explicit ``id`` field when present,
    otherwise the file stem. Both are stable across the fixture graph."""
    fid = fixture.get("id")
    if isinstance(fid, str) and fid:
        return fid
    return path.stem


def _validate_blocker_references(fixtures: list[tuple[Path, dict]]) -> list[str]:
    issues: list[str] = []
    ids = {_fixture_id(fixture, path) for path, fixture in fixtures}
    for path, fixture in fixtures:
        fid = _fixture_id(fixture, path)
        for blocker in fixture.get("blocked_by", []):
            if blocker not in ids:
                issues.append(
                    f"{fid}: blocked_by references unknown ticket '{blocker}'"
                )
    return issues


def _detect_cycles(fixtures: list[tuple[Path, dict]]) -> list[str]:
    """DFS cycle detection over the blocked_by graph."""
    by_id: dict[str, dict] = {
        _fixture_id(fixture, path): fixture for path, fixture in fixtures
    }
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {fid: WHITE for fid in by_id}
    cycles: list[str] = []

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for target in by_id.get(node, {}).get("blocked_by", []):
            if target not in color:
                continue  # unknown blocker reported elsewhere
            if color[target] == GRAY:
                start = path.index(target)
                cycle = path[start:] + [target]
                cycles.append(
                    f"cycle detected in blocked_by graph: {' -> '.join(cycle)}"
                )
            elif color[target] == WHITE:
                dfs(target, path)
        path.pop()
        color[node] = BLACK

    for fid in by_id:
        if color[fid] == WHITE:
            dfs(fid, [])
    return cycles


def _validate_ready_blockers(fixtures: list[tuple[Path, dict]]) -> list[str]:
    issues: list[str] = []
    status_by_id: dict[str, str] = {
        _fixture_id(fixture, path): fixture.get("status", "")
        for path, fixture in fixtures
    }
    for path, fixture in fixtures:
        fid = _fixture_id(fixture, path)
        if fixture.get("status") == "ready":
            for blocker in fixture.get("blocked_by", []):
                if status_by_id.get(blocker) != "done":
                    issues.append(
                        f"{fid}: status is 'ready' but blocker '{blocker}' "
                        f"is not 'done' (status='{status_by_id.get(blocker)}')"
                    )
    return issues


def _validate_source_specs(fixtures: list[tuple[Path, dict]]) -> list[str]:
    issues: list[str] = []
    for path, fixture in fixtures:
        fid = _fixture_id(fixture, path)
        spec = fixture.get("source_spec", "")
        if not spec:
            # schema requires non-empty source_spec; this is surfaced there.
            continue
        # Reject absolute paths and parent-directory escapes.
        spec_path = Path(spec)
        if spec_path.is_absolute() or spec.startswith("/"):
            issues.append(f"{fid}: source_spec '{spec}' must be repository-relative")
            continue
        if any(part == ".." for part in spec_path.parts):
            issues.append(f"{fid}: source_spec '{spec}' escapes the repository")
            continue
        resolved = (REPO_ROOT / spec).resolve()
        try:
            resolved.relative_to(REPO_ROOT.resolve())
        except ValueError:
            issues.append(f"{fid}: source_spec '{spec}' escapes the repository")
            continue
        if not (REPO_ROOT / spec).exists():
            issues.append(f"{fid}: source_spec '{spec}' does not exist on disk")
    return issues


def _validate_forbidden_overlap(fixtures: list[tuple[Path, dict]]) -> list[str]:
    issues: list[str] = []
    fixture_prefix = "harness/skills/tasks"
    for path, fixture in fixtures:
        fid = _fixture_id(fixture, path)
        for forbidden in fixture.get("forbidden_paths", []):
            normalized = forbidden.rstrip("/")
            if normalized == fixture_prefix or normalized.startswith(
                fixture_prefix + "/"
            ):
                issues.append(
                    f"{fid}: forbidden_path '{forbidden}' overlaps the "
                    f"task fixture directory"
                )
    return issues


def validate() -> list[str]:
    """Return a list of issue strings; an empty list means all fixtures pass."""
    issues: list[str] = []

    if not SCHEMA_PATH.exists():
        return [f"schema.json not found: {SCHEMA_PATH}"]
    if not TASKS_DIR.exists():
        return [f"tasks directory not found: {TASKS_DIR}"]

    fixtures = _load_fixtures()
    if not fixtures:
        return ["no task fixtures found under harness/skills/tasks"]

    issues.extend(_validate_schema(fixtures))
    issues.extend(_validate_blocker_references(fixtures))
    issues.extend(_detect_cycles(fixtures))
    issues.extend(_validate_ready_blockers(fixtures))
    issues.extend(_validate_source_specs(fixtures))
    issues.extend(_validate_forbidden_overlap(fixtures))
    return issues


def main() -> int:
    issues = validate()
    if issues:
        print(f"FAIL - {len(issues)} issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        return 1
    print("OK - all task fixtures pass validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
