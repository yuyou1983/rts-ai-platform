"""Trace Schema — 定义 skill 执行轨迹的数据结构。

每次 Hermes/Codex 执行任务，harness-executor 记录一条 SkillTrial 记录。
SkillEvolver 对比 pass/fail 组生成 skill patch。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class ToolCallRecord:
    """单次 tool call 记录。"""
    tool: str                    # e.g. "Read", "Write", "Bash"
    args_summary: str            # 参数摘要（不记录完整内容，避免 token 泄漏）
    timestamp: str = ""          # ISO 8601

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


@dataclass
class SkillTrial:
    """一次 skill 使用的完整轨迹。"""
    # ─── 任务标识（无默认值） ───
    task_id: str                  # harness task ID
    task_description: str        # 任务描述（截断到 200 字）
    skill_name: str              # 使用的 skill

    # ─── Schema 版本 ───
    schema_version: int = 2

    # ─── 任务标识（v2 扩展） ───
    skill_version: str = ""      # skill 版本号
    candidate_id: str = ""       # 候选 patch ID
    agent_run_id: str = ""       # agent 运行 ID
    task_fixture_id: str = ""    # 任务 fixture ID
    baseline_or_candidate: str = "baseline"  # "baseline" / "candidate"
    strategy_label: str = ""     # Phase 3 策略标签 (A/B/C/D)

    # ─── Skill 读取 ───
    skill_md_read: bool = False  # 是否真的读取了 SKILL.md
    primary_script_called: bool = False  # primary_script 是否被调用
    primary_action_invoked: bool = False  # primary_action tool 是否被调用

    # ─── 执行轨迹 ───
    tool_calls: list[dict] = field(default_factory=list)  # [ToolCallRecord.asdict()]
    validation_commands_run: list[str] = field(default_factory=list)
    validation_results: list[str] = field(default_factory=list)  # "pass" / "fail: <reason>"

    # ─── 验证证据 ───
    validation_exit_codes: list[int] = field(default_factory=list)
    validation_stdout_hashes: list[str] = field(default_factory=list)
    validation_stderr_summaries: list[str] = field(default_factory=list)

    # ─── 验证结果 ───
    functional_verification: str = ""  # "pass" / "fail" / "skip"
    failure_log_summary: str = ""      # 失败日志截断到 500 字

    # ─── 资源消耗 ───
    token_count: int = 0
    turn_count: int = 0
    duration_seconds: float = 0.0

    # ─── 文件影响 ───
    touched_files: list[str] = field(default_factory=list)

    # ─── 最终结果 ───
    outcome: str = ""  # "pass" / "fail" / "error" / "timeout"

    # ─── Silent-bypass 检测 ───
    silent_bypass_detected: bool = False
    silent_bypass_details: list[str] = field(default_factory=list)

    # ─── 时间戳 ───
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    def to_jsonl(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ─── 持久化 ──────────────────────────────────────────────────────

TRIALS_DIR = Path(__file__).parent / "trials"
USAGE_FILE = Path(__file__).parent / "skill_usage.jsonl"


def record_trial(trial: SkillTrial) -> Path:
    """写入一条 trial 记录，返回文件路径。"""
    TRIALS_DIR.mkdir(parents=True, exist_ok=True)
    date_prefix = datetime.now(timezone.utc).strftime("%Y%m%d")
    trial_file = TRIALS_DIR / f"{date_prefix}.jsonl"
    with open(trial_file, "a") as f:
        f.write(trial.to_jsonl() + "\n")

    # 同时记录 skill_usage 摘要
    usage = {
        "skill": trial.skill_name,
        "task_id": trial.task_id,
        "outcome": trial.outcome,
        "timestamp": trial.timestamp,
    }
    with open(USAGE_FILE, "a") as f:
        f.write(json.dumps(usage, ensure_ascii=False) + "\n")

    return trial_file


def load_trials(skill_name: str | None = None, outcome: str | None = None) -> list[SkillTrial]:
    """读取所有 trial 记录，可选按 skill/outcome 过滤。"""
    trials: list[SkillTrial] = []
    if not TRIALS_DIR.exists():
        return trials
    for f in sorted(TRIALS_DIR.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Tolerate v1 records missing schema_version and other v2 fields
            d.setdefault("schema_version", 1)
            t = SkillTrial(**d)
            if skill_name and t.skill_name != skill_name:
                continue
            if outcome and t.outcome != outcome:
                continue
            trials.append(t)
    return trials
