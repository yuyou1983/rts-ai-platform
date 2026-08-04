#!/usr/bin/env python3
"""校验 harness/skills/registry.json 是否符合 schema.json。

用法: python3 harness/skills/validate_registry.py [--fix]
  --fix: 自动补全缺失的可选字段 (version, last_evolved, held_out_suite)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA_PATH = REPO_ROOT / "harness" / "skills" / "schema.json"
REGISTRY_PATH = REPO_ROOT / "harness" / "skills" / "registry.json"
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"

# 额外的项目级校验（schema 无法表达的）
LAYER_NAMES = {"proto", "simcore", "agents", "frontend-godot", "dev-harness"}
OWNER_DOMAINS = {
    "team-simcore", "team-ai", "team-balance", "team-release",
    "godot-specialist", "harness-executor", "cross-cutting",
}


def validate() -> list[str]:
    """返回问题列表，空 = 全部通过。"""
    issues: list[str] = []

    if not SCHEMA_PATH.exists():
        return [f"schema.json not found: {SCHEMA_PATH}"]
    if not REGISTRY_PATH.exists():
        return [f"registry.json not found: {REGISTRY_PATH}"]

    schema = json.loads(SCHEMA_PATH.read_text())
    registry = json.loads(REGISTRY_PATH.read_text())

    # 1. jsonschema 校验
    try:
        import jsonschema
    except ImportError:
        issues.append("jsonschema not installed — skipping schema validation (pip install jsonschema)")
        jsonschema = None

    if jsonschema:
        for i, entry in enumerate(registry):
            try:
                jsonschema.validate(entry, schema)
            except jsonschema.ValidationError as e:
                issues.append(f"registry[{i}] ({entry.get('name', '?')}): {e.message}")

    # 2. 检查 layer_constraints 中的值是否合法
    for entry in registry:
        name = entry.get("name", "?")
        for layer in entry.get("layer_constraints", []):
            if layer not in LAYER_NAMES:
                issues.append(f"{name}: invalid layer '{layer}', must be one of {LAYER_NAMES}")

        # 3. 检查 owner_domain
        if entry.get("owner_domain") not in OWNER_DOMAINS:
            issues.append(f"{name}: invalid owner_domain '{entry.get('owner_domain')}'")

        # 4. 检查 expected_tool_calls 非空
        if not entry.get("expected_tool_calls"):
            issues.append(f"{name}: expected_tool_calls is empty (silent-bypass risk)")

        # 5. 检查 validation_commands 非空
        if not entry.get("validation_commands"):
            issues.append(f"{name}: validation_commands is empty (no verification)")

        # 6. 检查 known_failure_modes 非空
        if not entry.get("known_failure_modes"):
            issues.append(f"{name}: known_failure_modes is empty")

        # 7. 检查 skill 目录存在
        skill_dir = SKILLS_DIR / name
        if not skill_dir.exists():
            issues.append(f"{name}: directory {skill_dir} does not exist")
        elif not (skill_dir / "SKILL.md").exists():
            issues.append(f"{name}: SKILL.md not found in {skill_dir}")

        # 8. 检查 held_out_suite 路径存在（如果指定了）
        suite = entry.get("held_out_suite")
        if suite:
            suite_path = REPO_ROOT / suite
            if not suite_path.exists():
                issues.append(f"{name}: held_out_suite path '{suite}' does not exist")

    # 9. 检查无重复 name
    names = [e.get("name") for e in registry]
    dupes = [n for n in names if names.count(n) > 1]
    if dupes:
        issues.append(f"Duplicate skill names: {set(dupes)}")

    # 10. 检查本地 skill 目录是否都有 registry 条目
    registered = {entry.get("name") for entry in registry}
    local = {p.parent.name for p in SKILLS_DIR.glob("*/SKILL.md")}
    missing = sorted(local - registered)
    if missing:
        issues.append(f"Missing registry entries for local skills: {missing}")

    # 11. 组合语义校验：composes 目标存在、仅 orchestrator 可组合、
    #     model orchestrator 不能依赖 user-only child、无环、无自组合
    issues.extend(validate_composition(registry))

    return issues


def validate_composition(registry: list[dict]) -> list[str]:
    """Validate composes target existence, kind restrictions, invocation
    compatibility, and graph acyclicity.

    Rules:
      1. Every ``composes`` target must exist in the registry.
      2. Only ``orchestrator`` entries may carry a non-empty ``composes``.
      3. A ``model`` orchestrator cannot require a ``user``-only child.
      4. The directed composition graph must be acyclic.
      5. A skill cannot compose itself.

    Returned issue strings are deterministic and always contain the offending
    skill name and, where relevant, the offending edge target.
    """
    issues: list[str] = []
    names = {entry.get("name") for entry in registry}
    by_name: dict[str, dict] = {entry.get("name"): entry for entry in registry}

    for entry in registry:
        name = entry.get("name", "?")
        composes = entry.get("composes") or []
        kind = entry.get("skill_kind")
        mode = entry.get("invocation_mode")

        # Rule 5: a skill cannot compose itself.
        if name in composes:
            issues.append(f"{name}: skill cannot compose itself")

        # Rule 1: every composes target must exist.
        for target in composes:
            if target == name:
                continue  # already reported by Rule 5
            if target not in names:
                issues.append(f"{name}: composes target '{target}' does not exist")

        # Rule 2: only orchestrators may compose.
        if composes and kind != "orchestrator":
            issues.append(
                f"{name}: non-orchestrator skill_kind '{kind}' cannot have composes"
            )

        # Rule 3: a model orchestrator cannot require a user-only child.
        if mode == "model" and kind == "orchestrator":
            for target in composes:
                child = by_name.get(target)
                if child and child.get("invocation_mode") == "user":
                    issues.append(
                        f"{name}: model orchestrator cannot require "
                        f"user-only child '{target}'"
                    )

    # Rule 4: the directed composition graph must be acyclic (DFS).
    issues.extend(_detect_composition_cycles(by_name))

    return issues


def _detect_composition_cycles(by_name: dict[str, dict]) -> list[str]:
    """Return cycle descriptions found via DFS on the composes graph.

    Self-loops are reported by ``validate_composition`` (Rule 5) and skipped
    here to avoid duplicate messages.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {name: WHITE for name in by_name}
    cycles: list[str] = []

    def dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        path.append(node)
        for target in by_name.get(node, {}).get("composes") or []:
            if target == node:
                continue  # self-loop handled by Rule 5
            if target not in color:
                continue  # missing target handled by Rule 1
            if color[target] == GRAY:
                start = path.index(target)
                cycle = path[start:] + [target]
                cycles.append(
                    "cycle detected in composition graph: " + " -> ".join(cycle)
                )
            elif color[target] == WHITE:
                dfs(target, path)
        path.pop()
        color[node] = BLACK

    for name in by_name:
        if color[name] == WHITE:
            dfs(name, [])
    return cycles


def fix() -> None:
    """自动补全缺失的可选字段。"""
    if not REGISTRY_PATH.exists():
        return
    registry = json.loads(REGISTRY_PATH.read_text())
    changed = False
    for entry in registry:
        if "version" not in entry:
            entry["version"] = "0.1.0"
            changed = True
        if "last_evolved" not in entry:
            entry["last_evolved"] = None
            changed = True
        if "held_out_suite" not in entry:
            name = entry.get("name", "unknown")
            suite_dir = REPO_ROOT / "harness" / "skills" / "held_out" / name
            entry["held_out_suite"] = f"harness/skills/held_out/{name}" if suite_dir.exists() else None
            changed = True
    if changed:
        REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False))
        print("Fixed registry.json")


def main() -> int:
    fix_mode = "--fix" in sys.argv
    if fix_mode:
        fix()

    issues = validate()
    if issues:
        print(f"FAIL — {len(issues)} issue(s):")
        for i in issues:
            print(f"  - {i}")
        return 1

    print("OK — all registry entries pass validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
