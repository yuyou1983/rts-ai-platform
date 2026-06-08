"""skill_evolver.py — Skill Evolution 最小闭环。

Explore -> Contrast -> Patch Candidate -> Audit -> Held-Out -> Promote/Rollback

论文核心思想：
- 同一任务用多个高层策略并行试 (Phase 3)
- 对比成功/失败轨迹，生成局部 skill patch (Phase 4)
- 独立 Auditor 审核 patch (Phase 5)
- Held-out validation 防止过拟合 (Phase 6)
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from harness.evolve.auditor import audit_candidate_patch
from harness.trace.schema import SkillTrial, load_trials, record_trial

logger = logging.getLogger(__name__)

# ─── 路径常量 ─────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
REGISTRY_PATH = REPO_ROOT / "harness" / "skills" / "registry.json"
SCHEMA_PATH = REPO_ROOT / "harness" / "skills" / "schema.json"
CANDIDATES_DIR = REPO_ROOT / "harness" / "skills" / "candidates"
HELD_OUT_DIR = REPO_ROOT / "harness" / "skills" / "held_out"
TRIALS_DIR = REPO_ROOT / "harness" / "trace" / "trials"
BACKUP_DIR = REPO_ROOT / "harness" / "skills" / "backups"


def _load_registry() -> list[dict]:
    if REGISTRY_PATH.exists():
        return json.loads(REGISTRY_PATH.read_text())
    return []


def _save_registry(entries: list[dict]) -> None:
    REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY_PATH.write_text(json.dumps(entries, indent=2, ensure_ascii=False))


# ─── Phase 3: Strategy-Diversified Exploration ──────────────────

@dataclass
class ExplorationStrategy:
    """一个高层策略定义。"""
    label: str               # A, B, C, D
    description: str
    focus_files: list[str]
    extra_rules: list[str]
    priority: int = 0


STRATEGY_TEMPLATES: dict[str, list[ExplorationStrategy]] = {
    "godot-vfx": [
        ExplorationStrategy("A", "资源 manifest 优先",
                           ["godot/resources/", "godot/scripts/sprite_loader.gd"],
                           ["先检查 presentation_manifest.json 是否存在",
                            "对比 manifest 列出的资源与实际文件"]),
        ExplorationStrategy("B", "SpriteLoader 裁剪优先",
                           ["godot/scripts/sprite_loader.gd", "godot/scripts/game_view.gd"],
                           ["先看 SpriteLoader._load_atlas 的裁剪逻辑",
                            "检查 atlas_rects 与 manifest 尺寸是否一致"]),
        ExplorationStrategy("C", "场景/相机/选择圈校验优先",
                           ["godot/scenes/game_view.tscn", "godot/scripts/camera_controller.gd"],
                           ["先检查 Camera2D zoom 和 limits",
                            "检查选择圈 radius 与 sprite size 是否匹配"]),
        ExplorationStrategy("D", "截图回归测试优先",
                           ["tests/godot/", "scripts/"],
                           ["先运行截图回归基线",
                            "diff 当前截图与 baseline"]),
    ],
    "simcore-replay": [
        ExplorationStrategy("A", "Replay hash 一致性优先",
                           ["simcore/engine.py", "simcore/replay.py"],
                           ["先跑 determinism smoke test", "对比 replay hash"]),
        ExplorationStrategy("B", "规则逻辑优先",
                           ["simcore/rules.py", "simcore/state.py"],
                           ["先检查 rules 中状态转移逻辑",
                            "验证 fog_of_war 更新时机"]),
        ExplorationStrategy("C", "gRPC 边界优先",
                           ["simcore/grpc_server.py", "simcore/grpc_client.py"],
                           ["先检查 proto 字段完整性",
                            "验证 server 返回的 map_width/height"]),
    ],
}


def get_strategies(task_type: str) -> list[ExplorationStrategy]:
    return STRATEGY_TEMPLATES.get(task_type, [
        ExplorationStrategy("A", "默认策略", [], [], 0),
    ])


# ─── Phase 4: Contrastive Skill Update ─────────────────────────

@dataclass
class SkillPatch:
    """一个 skill patch 候选。"""
    skill_name: str
    timestamp: str
    patch_content: str
    rationale: str
    evidence_pass: list[str] = field(default_factory=list)
    evidence_fail: list[str] = field(default_factory=list)
    audit_result: str = "pending"
    audit_details: str = ""


def contrast_trials(skill_name: str) -> list[SkillPatch]:
    """对比成功/失败轨迹，生成 skill patch 候选。"""
    pass_trials = load_trials(skill_name=skill_name, outcome="pass")
    fail_trials = load_trials(skill_name=skill_name, outcome="fail")

    if not fail_trials:
        logger.info("No failed trials for %s -- nothing to patch", skill_name)
        return []

    patches: list[SkillPatch] = []
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # silent-bypass 失败
    bypass_fails = [t for t in fail_trials if t.silent_bypass_detected]
    if bypass_fails:
        check_only_clause = (
            "\nRun `godot --headless --check-only` before marking task complete.\n"
            if "godot" in skill_name.lower() else ""
        )
        patches.append(SkillPatch(
            skill_name=skill_name, timestamp=ts,
            patch_content=(
                f"## Silent-Bypass 修复\n\n"
                f"在 {len(bypass_fails)} 次失败中检测到 silent-bypass。\n"
                f"将以下规则从 '应该' 升级为 '必须'，并添加对应的 "
                f"validation_commands：\n"
                f"- primary_action: must be invoked in every task execution\n"
                f"- Read SKILL.md: must be the first tool call{check_only_clause}"
            ),
            rationale="silent-bypass 是 skill 被加载但核心规则被忽略的情况。",
            evidence_pass=[t.task_id for t in pass_trials[:5]],
            evidence_fail=[t.task_id for t in bypass_fails[:5]],
        ))

    # SKILL.md 未读取
    unread_fails = [t for t in fail_trials if not t.skill_md_read]
    if unread_fails:
        check_only_clause = (
            "\nRun `godot --headless --check-only` before marking task complete.\n"
            if "godot" in skill_name.lower() else ""
        )
        patches.append(SkillPatch(
            skill_name=skill_name, timestamp=ts,
            patch_content=(
                f"## SKILL.md 读取强制化\n\n"
                f"在 {len(unread_fails)} 次失败中，SKILL.md 未被读取。\n"
                f"在 SKILL.md 开头添加强制性读取检查指令。\n"
                f"- primary_action: invoke the declared primary_action first\n"
                f"- Read SKILL.md: required as first tool call{check_only_clause}"
            ),
            rationale="如果 SKILL.md 没被读取，skill 中的规则不可能被遵循。",
            evidence_pass=[t.task_id for t in pass_trials[:5]],
            evidence_fail=[t.task_id for t in unread_fails[:5]],
        ))

    # primary_action 未调用
    no_action_fails = [t for t in fail_trials if not t.primary_action_invoked]
    if no_action_fails:
        check_only_clause = (
            "\nRun `godot --headless --check-only` before marking task complete.\n"
            if "godot" in skill_name.lower() else ""
        )
        patches.append(SkillPatch(
            skill_name=skill_name, timestamp=ts,
            patch_content=(
                f"## Primary Action 强制化\n\n"
                f"在 {len(no_action_fails)} 次失败中，primary_action 未被调用。\n"
                f"将 primary_action 作为 SKILL.md 第一条显式指令。\n"
                f"- primary_action: invoke declared primary_action as first code action\n"
                f"- validation: run --check-only before commit{check_only_clause}"
            ),
            rationale="primary-action hoisting：将核心动作提到最显眼位置。",
            evidence_pass=[t.task_id for t in pass_trials[:5]],
            evidence_fail=[t.task_id for t in no_action_fails[:5]],
        ))

    return patches


def save_patch_candidate(patch: SkillPatch) -> Path:
    """保存 patch 候选到文件系统。"""
    dir_path = CANDIDATES_DIR / patch.skill_name / patch.timestamp
    dir_path.mkdir(parents=True, exist_ok=True)

    (dir_path / "patch.md").write_text(patch.patch_content)
    (dir_path / "rationale.json").write_text(json.dumps({
        "skill": patch.skill_name,
        "rationale": patch.rationale,
        "evidence_pass": patch.evidence_pass,
        "evidence_fail": patch.evidence_fail,
        "audit_result": patch.audit_result,
        "audit_details": patch.audit_details,
    }, indent=2, ensure_ascii=False))
    (dir_path / "evidence.json").write_text(json.dumps({
        "pass_trial_ids": patch.evidence_pass,
        "fail_trial_ids": patch.evidence_fail,
    }, indent=2))

    return dir_path


# ─── Phase 5: Independent Auditor ───────────────────────────────

@dataclass
class AuditResult:
    """Auditor 审核结果。"""
    patch_path: str
    accepted: bool
    issues: list[str] = field(default_factory=list)


def audit_patch(patch: SkillPatch, skill_md_content: str) -> AuditResult:
    """独立审核一个 patch 候选。"""
    issues: list[str] = []
    patch_lower = patch.patch_content.lower()
    content = skill_md_content.lower()

    # Check registry for primary_action as fallback
    registry = _load_registry()
    reg_entry = next((e for e in registry if e.get("name") == patch.skill_name), None)
    has_primary_in_registry = bool(reg_entry and reg_entry.get("primary_action"))

    # ── 通用检查 ──
    hardcoded = re.findall(r'seed\s*[=:]\s*\d+', patch_lower)
    hardcoded += re.findall(r'/tmp/[a-z0-9_/-]+', patch_lower)
    hardcoded += re.findall(r'entity_[a-z]+_\d+', patch_lower)
    if hardcoded:
        issues.append(f"hardcoded_seed_or_path: {hardcoded[:5]}")

    if any(kw in patch_lower for kw in ["seed42", "test_fix", "debug_"]):
        issues.append("references_training_instance_filename")

    if len(patch.patch_content) > 8000:
        issues.append(f"script_too_long: {len(patch.patch_content)} chars")

    if "primary_script" not in content and "primary_action" not in content and not has_primary_in_registry:
        issues.append("missing_primary_script_or_action")

    if any(kw in patch_lower for kw in ["必须", "永远", "不要", "never", "always", "must"]):
        has_evidence = (
            "validation_commands" in content
            or "expected_tool_calls" in content
            or (reg_entry and reg_entry.get("validation_commands"))
            or (reg_entry and reg_entry.get("expected_tool_calls"))
        )
        if not has_evidence:
            issues.append("unsupported_must_never_without_evidence")

    # ── 项目专属检查 ──
    if "simcore" in patch_lower and ("llm" in patch_lower or "chat.completions" in patch_lower):
        issues.append("llm_in_simcore_highfreq_loop")

    if "godot" in patch.skill_name.lower():
        if "--check-only" not in patch_lower and "check-only" not in patch_lower:
            issues.append("godot_task_missing_check_only")

    if "simcore" in patch.skill_name.lower():
        if "determinism" not in patch_lower and "replay hash" not in patch_lower:
            issues.append("simcore_task_missing_determinism_test")

    # ── Structured auditor layer ────────────────────────────────
    structured = audit_candidate_patch(
        skill_name=patch.skill_name,
        patch_content=patch.patch_content,
        skill_md_content=skill_md_content,
        evidence={
            "touched_files": getattr(patch, "touched_files", []),
        },
    )
    # De-duplicate: the legacy check above already handles
    # must/never with registry fallback, so drop the
    # unsupported_must_without_validation_evidence from the
    # structured result when the legacy check already passed.
    must_issue = "unsupported_must_without_validation_evidence"
    if must_issue not in issues and must_issue in structured.issues:
        structured.issues.remove(must_issue)
    issues.extend(structured.issues)

    return AuditResult(
        patch_path=f"{patch.skill_name}/{patch.timestamp}",
        accepted=len(issues) == 0,
        issues=issues,
    )


# ─── Phase 6: Held-Out Validation (真实执行) ────────────────────

def validate_held_out(skill_name: str) -> bool:
    """在 held-out suite 上验证当前 SKILL.md。真实执行 validation_commands。"""
    suite_dir = HELD_OUT_DIR / skill_name
    suite_file = suite_dir / "suite.json"
    if not suite_file.exists():
        logger.warning("No held-out suite for %s -- skipping", skill_name)
        return True

    suite = json.loads(suite_file.read_text())
    all_pass = True
    for scenario in suite.get("scenarios", []):
        scenario_id = scenario["id"]
        for cmd in scenario.get("validation_commands", []):
            logger.info("  held-out %s: %s", scenario_id, cmd)
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=15,
                    cwd=str(REPO_ROOT),
                )
                if result.returncode != 0:
                    logger.error("  FAIL: %s (exit %d)\n  stderr: %s",
                                 cmd, result.returncode, result.stderr[:200])
                    all_pass = False
            except subprocess.TimeoutExpired:
                logger.error("  TIMEOUT: %s", cmd)
                all_pass = False
            except Exception as exc:
                logger.error("  ERROR: %s: %s", cmd, exc)
                all_pass = False

    return all_pass


# ─── Phase 6: Promotion (备份 + rollback) ────────────────────────

def _backup_skill_md(skill_name: str) -> Path | None:
    """备份当前 SKILL.md，返回备份路径。"""
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    if not skill_md.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = BACKUP_DIR / f"{skill_name}_{ts}.md"
    shutil.copy2(skill_md, backup)
    logger.info("Backed up %s -> %s", skill_md, backup)
    return backup


def rollback_skill_md(skill_name: str, backup_path: Path) -> None:
    """从备份恢复 SKILL.md。"""
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    shutil.copy2(backup_path, skill_md)
    logger.info("Rolled back %s from %s", skill_md, backup_path)


def promote_patch(patch: SkillPatch, audit: AuditResult, held_out_pass: bool) -> bool:
    """audit pass + held-out pass -> 更新 SKILL.md + 更新 registry。"""
    if not audit.accepted:
        logger.warning("Patch %s rejected by auditor: %s", audit.patch_path, audit.issues)
        return False

    if not held_out_pass:
        logger.warning("Patch %s failed held-out validation", audit.patch_path)
        return False

    # 备份
    backup = _backup_skill_md(patch.skill_name)
    if backup is None:
        logger.error("Cannot backup SKILL.md for %s", patch.skill_name)
        return False

    # 应用 patch
    skill_md = SKILLS_DIR / patch.skill_name / "SKILL.md"
    original = skill_md.read_text()
    updated = original.rstrip() + "\n\n---\n\n## Evolved Rules\n" + patch.patch_content + "\n"
    skill_md.write_text(updated)

    # 更新 registry
    registry = _load_registry()
    for entry in registry:
        if entry.get("name") == patch.skill_name:
            entry["last_evolved"] = datetime.now(timezone.utc).isoformat()
            # bump patch version
            v = entry.get("version", "0.1.0")
            parts = v.split(".")
            parts[-1] = str(int(parts[-1]) + 1)
            entry["version"] = ".".join(parts)
            break
    _save_registry(registry)

    logger.info("Patch promoted: %s (backup at %s)", audit.patch_path, backup)
    return True


# ─── Main: 单 skill 完整闭环 ───────────────────────────────────

def evolve_skill(skill_name: str) -> bool:
    """对单个 skill 执行完整 evolve 闭环，返回是否成功 promote。"""
    print(f"=== SkillEvolver: {skill_name} ===\n")

    # Phase 4: Contrast
    print("[1/4] Contrasting pass/fail trials...")
    patches = contrast_trials(skill_name)
    if not patches:
        print("  No patches generated -- nothing to evolve.")
        return False
    print(f"  Generated {len(patches)} patch candidate(s)")

    # Phase 5: Audit
    print("\n[2/4] Auditing patches...")
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    skill_content = skill_md.read_text() if skill_md.exists() else ""

    accepted: list[tuple[SkillPatch, AuditResult]] = []
    for patch in patches:
        audit = audit_patch(patch, skill_content)
        status = "ACCEPTED" if audit.accepted else f"REJECTED ({len(audit.issues)} issues)"
        print(f"  {patch.timestamp}: {status}")
        for issue in audit.issues:
            print(f"    - {issue}")
        if audit.accepted:
            accepted.append((patch, audit))
        else:
            patch.audit_result = "rejected"
            patch.audit_details = "; ".join(audit.issues)
            save_patch_candidate(patch)

    if not accepted:
        print("\n  All patches rejected by auditor.")
        return False

    # Phase 6: Held-Out + Promote/Rollback
    print(f"\n[3/4] Held-out validation for {len(accepted)} accepted patches...")
    promoted_any = False
    for patch, audit in accepted:
        held_out_pass = validate_held_out(skill_name)
        promoted = promote_patch(patch, audit, held_out_pass)
        if promoted:
            print(f"  Patch {patch.timestamp} PROMOTED")
            promoted_any = True
        else:
            print(f"  Patch {patch.timestamp} NOT promoted (held-out={held_out_pass})")
        patch.audit_result = "promoted" if promoted else "rejected_held_out"
        save_patch_candidate(patch)

    # Phase 6b: 如果全部失败，确保 rollback
    if not promoted_any:
        print("\n[4/4] No patches promoted -- ensuring SKILL.md unchanged")
    else:
        print(f"\n[4/4] Done: {skill_name} evolved successfully")

    return promoted_any


def evolve_skill_dry(skill_name: str) -> bool:
    """Dry-run: 只生成 candidate，不写 SKILL.md，不更新 registry。"""
    print(f"=== SkillEvolver (dry-run): {skill_name} ===\n")

    # Phase 4: Contrast
    print("[1/3] Contrasting pass/fail trials...")
    patches = contrast_trials(skill_name)
    if not patches:
        print("  No patches generated -- nothing to evolve.")
        return False
    print(f"  Generated {len(patches)} patch candidate(s)")

    # Phase 5: Audit
    print("\n[2/3] Auditing patches...")
    skill_md = SKILLS_DIR / skill_name / "SKILL.md"
    skill_content = skill_md.read_text() if skill_md.exists() else ""

    for patch in patches:
        audit = audit_patch(patch, skill_content)
        status = "WOULD ACCEPT" if audit.accepted else f"WOULD REJECT ({len(audit.issues)} issues)"
        print(f"  {patch.timestamp}: {status}")
        for issue in audit.issues:
            print(f"    - {issue}")
        patch.audit_result = "dry_run_accepted" if audit.accepted else "dry_run_rejected"
        patch.audit_details = "; ".join(audit.issues) if audit.issues else ""
        save_patch_candidate(patch)

    # Phase 6: Held-Out (只验证，不 promote)
    accepted = [(p, a) for p in patches for a in [audit_patch(p, skill_content)] if a.accepted]
    if accepted:
        print(f"\n[3/3] Held-out validation (dry-run, no promotion) for {len(accepted)} accepted patches...")
        for patch, audit in accepted:
            held_out_pass = validate_held_out(skill_name)
            print(f"  Patch {patch.timestamp}: held-out={'PASS' if held_out_pass else 'FAIL'} (not promoted)")
    else:
        print("\n[3/3] No accepted patches to validate.")

    print(f"\n  DRY-RUN: no files modified in .agents/skills/")
    return True  # 有 candidate 生成就算成功


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="SkillEvolver — evolve a skill from trace data")
    parser.add_argument("skill_name", help="e.g. godot-specialist")
    parser.add_argument("--apply", action="store_true",
                        help="Allow writing SKILL.md and registry (default: dry-run)")
    args = parser.parse_args()

    if args.apply:
        ok = evolve_skill(args.skill_name)
    else:
        ok = evolve_skill_dry(args.skill_name)
    sys.exit(0 if ok else 1)
