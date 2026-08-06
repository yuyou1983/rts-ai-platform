# Agent Skills Workflow Alignment — 变更对比与验证说明

> **基线**: `1203b28` (SC1 Combat Remediation 完成点)
> **终点**: `9e113ee` (原始 Agent 提交点；复核后不等于最终验收完成)
> **变更范围**: 55 files, +6486 / -178 lines
> **日期**: 2026-08-04 ~ 2026-08-05

> **2026-08-05 校验修正**: 本文记录的固定点统计仍然有效，但原文将
> command-only suite、未纳入提交的 baseline trace 和 caller-supplied ID
> 解释成了完整 candidate 闭环。修复后的门禁状态以本文“最终门禁”和
> “已知限制”为准：A6-A8 均需真实 fresh-agent candidate trace 才能关闭。

---

## 一、变更总览

### 1.1 提交链

| # | Commit | Task | 描述 |
|---|--------|------|------|
| 1 | `f1c8b73` | Task 0 | 记录对齐基线 + 外部源引用 |
| 2 | `f233912` | Task 1 | 添加 skill 调用与组合语义 |
| 3 | `3e5c77b` | Task 2 | 建立 RTS 领域语言与领域建模 |
| 4 | `324ab23` | Task 3 | 升级 code-review 为三轴评审 |
| 5 | `aca0f3b` | Task 4 | 添加垂直票单语义到任务 fixture |
| 6 | `4f7a275` | Task 5 | 对齐 sprint 规划与 harness 执行 |
| 7 | `b5ee000` | Task 6 | 添加结构化 agent 交接 skill |
| 8 | `1aa2dfc` | Task 7 | 使 held-out 验证候选感知 |
| 9 | `109bae6` | Task 8 | 扩展和加强 held-out 覆盖 |
| 10 | `523ae80` | Task 9 | 运行真实 code-review skill 改进试点 |
| 11 | `9e113ee` | Task 10 | 原始 Agent 声明的最终集成；复核状态 BLOCKED |

### 1.2 文件变更统计

| 类别 | 文件数 | 新增行 | 删除行 | 说明 |
|------|--------|--------|--------|------|
| Skills (`.agents/skills/`) | 5 | +654 | -186 | 5 个 SKILL.md 新增或重写 |
| 领域文档 (`docs/domain/`, `CONTEXT-MAP.md`) | 5 | +544 | 0 | 4 个 bounded-context 词汇表 + 全局映射 |
| Harness 核心 (`harness/`) | 12 | +2,148 | -178 | schema, validator, evolver, held_out, strategy_runner |
| Held-out suites (`harness/skills/held_out/`) | 12 | +377 | -42 | 8 个新 suite + 4 个现有 suite 加强 + schema |
| Task fixtures (`harness/skills/tasks/`) | 3 | +313 | 0 | schema 扩展 + 2 个 fixture |
| 测试 (`tests/harness/`) | 11 | +1,052 | 0 | 11 个新测试文件 |
| 报告与计划 (`docs/`) | 5 | +1,552 | 0 | 执行计划 + QA 报告 + 操作手册 + 模板 + 源引用 |
| Trace schema | 2 | +98 | -2 | SkillTrial 扩展 + 严格验证 |
| **合计** | **55** | **+6,486** | **-178** | |

### 1.3 运行时业务代码修改

```
simcore/   — 0 文件
agents/    — 0 文件
godot/     — 0 文件
proto/     — 0 文件
```

**全部变更限定在 harness、docs、tests、.agents 范围内。**

---

## 二、逐 Task 对比：Before → After

### Task 1: Skill 调用与组合语义

#### Before
```json
// harness/skills/schema.json — 仅 name, description, version
// registry.json 22 entries — 无 invocation_mode, skill_kind, composes
// 无组合图验证
// validate_registry.py — 仅检查 name/description 非空
```

#### After
```json
// schema.json 新增字段:
{
  "invocation_mode": "user | model | both",
  "skill_kind": "domain | orchestrator | gate | discipline",
  "composes": ["skill-name", ...],
  "completion_criteria": ["...", ...],
  "last_evolved": "ISO8601 or null"
}

// registry.json 24 entries — 全部带 invocation_mode + skill_kind + composes
// validate_registry.py — 检查组合图无环、 invocation_mode 合法、 skill_kind 合法
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| 调用方式 | 隐式，agent 自行猜测 | 显式声明 `user/model/both` |
| Skill 分类 | 无 | 4 类 (`domain/orchestrator/gate/discipline`) |
| 组合关系 | 不可见 | 有向无环图，validator 检测环 |
| 完成标准 | 无 | `completion_criteria` 列表 |
| 注册数 | 22 | 24 (+domain-modeling, +handoff) |
| 测试 | 0 | 11 (test_skill_registry_semantics.py) |

**验证命令**:
```bash
python3 harness/skills/validate_registry.py
python3 -m pytest tests/harness/test_skill_registry_semantics.py -q
```

---

### Task 2: RTS 领域语言与领域建模

#### Before
```
// 无 CONTEXT-MAP.md
// 无 docs/domain/ 目录
// 无 domain-modeling skill
// 术语跨上下文冲突未被发现 (e.g. "unit" 在 SimCore=战斗实体, 在 Godot=视觉精灵)
```

#### After
```
CONTEXT-MAP.md                    — 全局上下文映射 (4 bounded contexts)
docs/domain/simcore-context.md    — SimCore 领域词汇 (entity, tick, combat_event, ...)
docs/domain/godot-presentation-context.md — Godot 呈现词汇 (sprite, atlas, VFX, ...)
docs/domain/sc1-source-truth-context.md   — SC1 源数据词汇 (DAT, weapon_id, ...)
docs/domain/skill-harness-context.md      — Harness 工具词汇 (trial, patch, held_out, ...)
.agents/skills/domain-modeling/SKILL.md   — 领域建模 skill (#23)
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| 术语冲突检测 | 不可行 | 4 个词汇表交叉比对 |
| 上下文边界 | 隐式 | 显式声明 + CONTEXT-MAP.md |
| 领域建模 skill | 不存在 | domain-modeling (#23), brainstorm.composes 引用 |
| 测试 | 0 | 14 (test_domain_contexts.py) |

**验证命令**:
```bash
test -f CONTEXT-MAP.md && test -f docs/domain/simcore-context.md
python3 -m pytest tests/harness/test_domain_contexts.py -q
```

---

### Task 3: 三轴 Code Review

#### Before
```
// .agents/skills/code-review/SKILL.md — 通用 review 指导
// 无 Standards / Specification / Source Truth 轴
// 无 combat-remediation-review fixture
// 测试: 0
```

#### After
```
// SKILL.md — 三轴评审协议:
//   1. Standards: 架构边界、编码规范、AGENTS.md 合规
//   2. Specification: 计划/QA drift 检测 (missing, partial, incorrect, out-of-scope)
//   3. Source Truth: DAT/源数据一致性验证

// harness/skills/tasks/code-review/combat-remediation-review.json
//   — 真实 fixture: git diff e201355...2dbcf66, fixed_point, forbidden_paths
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| 评审维度 | 单维度 (通用) | 三轴 (Standards/Spec/Source Truth) |
| Drift 检测 | 无 | QA 报告 vs 实现 diff 对比 |
| 源真验证 | 无 | SC1 DAT weapon_id 确认 |
| Fixture | 无 | combat-remediation-review (真实 diff) |
| 输出格式 | 自由文本 | 结构化: PASS/CONCERNS/FAIL per axis |
| 测试 | 0 | 8 (test_code_review_skill_contract.py) |

**验证命令**:
```bash
python3 -m pytest tests/harness/test_code_review_skill_contract.py -q
```

---

### Task 4: 垂直票单语义

#### Before
```json
// harness/skills/tasks/schema.json — 仅 id, name, skill_name, description
// 无 blocked_by, source_spec, acceptance_criteria, verification_seams, evidence_outputs
// 无依赖图验证
// validate_tasks.py 不存在
```

#### After
```json
// schema.json 新增必填字段:
{
  "source_spec": "docs/plans/...md",      // 规范来源
  "blocked_by": ["task-id", ...],          // 依赖图
  "acceptance_criteria": ["...", ...],     // 验收标准
  "verification_seams": ["cmd", ...],      // 验证命令
  "evidence_outputs": ["path", ...],       // 证据输出
  "status": "ready | blocked | in_progress | done"  // 状态
}

// validate_tasks.py — 验证字段完整性 + 依赖图无环 + status 合法
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| 任务依赖 | 隐式 | `blocked_by` 有向图，validator 检测环 |
| 规范追溯 | 无 | `source_spec` 指向计划文档 |
| 验收标准 | 无 | `acceptance_criteria` 列表 |
| 验证接缝 | 无 | `verification_seams` 命令列表 |
| 证据输出 | 无 | `evidence_outputs` 路径列表 |
| 状态管理 | 无 | `ready/blocked/in_progress/done` |
| 测试 | 0 | 10 (test_task_graph.py) |

**验证命令**:
```bash
python3 harness/skills/validate_tasks.py
python3 -m pytest tests/harness/test_task_graph.py -q
```

---

### Task 5: Sprint 规划与 Harness 执行对齐

#### Before
```
// .agents/skills/sprint-plan/SKILL.md — 通用 sprint 指导
// .agents/skills/harness-run/SKILL.md — 通用 harness 指导
// 无垂直切片要求
// 无紧反馈循环 (10 步)
```

#### After
```
// sprint-plan SKILL.md — 垂直切片要求:
//   1. 每个 ticket 必须 source_spec + blocked_by + acceptance_criteria
//   2. 独立可验证 (不依赖其他未完成 ticket)
//   3. strategy_runner 生成多策略 packet (A/B/C/D)

// harness-run SKILL.md — 10 步紧反馈循环:
//   1. Read SKILL.md → 2. Read fixture → 3. Run validation baseline
//   4. Execute task → 5. Run validation → 6. Record trace
//   7. Check evidence → 8. Run verification seams → 9. Update report → 10. Commit
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| Sprint 切片 | 水平 (按层) | 垂直 (端到端可验证) |
| Harness 循环 | 无结构 | 10 步强制序列 |
| Strategy packet | 无 | A/B/C/D 多策略对比 |
| Trace 记录 | 可选 | 强制 SkillTrial v2 |
| 测试 | 0 | 13 (test_execution_skill_contracts.py) |

**验证命令**:
```bash
python3 -m pytest tests/harness/test_execution_skill_contracts.py -q
```

---

### Task 6: 结构化 Agent 交接

#### Before
```
// 无 handoff skill
// agent 交接靠自由文本，经常遗漏关键信息
// 无模板
```

#### After
```
// .agents/skills/handoff/SKILL.md (#24):
//   - 必须包含一个 active task
//   - 必须包含一个 next command
//   - 输出到临时目录 (rts-agent-handoff-<task-id>.md)
//   - 凭证脱敏
//   - 拒绝 "Conversation Dump" 标题

// docs/agents/templates/agent-handoff-template.md:
//   10 个必填节: Context, Active Task, Next Command, Blockers,
//   Evidence, Decisions, Files Changed, Verification, Gate Status, Notes
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| 交接格式 | 自由文本 | 10 节结构化模板 |
| Active task | 经常遗漏 | 强制必填 |
| Next command | 经常遗漏 | 强制必填 |
| 凭证安全 | 无保护 | 强制脱敏 |
| 测试 | 0 | 12 (test_handoff_skill_contract.py) |

**验证命令**:
```bash
python3 -m pytest tests/harness/test_handoff_skill_contract.py -q
```

---

### Task 7: 候选感知 Held-Out 验证

#### Before
```python
# skill_evolver.py:
def validate_held_out(skill_name) -> bool:
    # 运行 suite.json 中的命令，返回 True/False
    # 不区分 baseline 和 candidate

def promote_patch(patch, audit, held_out_pass: bool) -> bool:
    # held_out_pass 只是 bool
    # 命令通过即可 promote
```

#### After
```python
# harness/evolve/held_out.py (新文件):
@dataclass
class HeldOutResult:
    passed: bool                    # 命令是否通过
    promotion_eligible: bool        # 是否有资格 promote
    skill_name: str
    candidate_id: str               # 候选 ID (空=命令行验证)
    scenario_results: list[dict]    # 逐场景结果
    issues: list[str]              # 问题列表

def validate_held_out_candidate(
    skill_name, candidate_id, candidate_overlay_path,
    candidate_trials, training_fixture_ids, held_out_fixture_ids
) -> HeldOutResult:
    # candidate_id 必须由 patch 派生，不能由调用者自报
    # 每个 suite 场景必须有唯一 fresh-agent candidate trial
    # trial 必须绑定 overlay SKILL.md hash 和首次读取路径
    # 训练 fixture 不能复用为 held-out

# skill_evolver.py:
def promote_patch(patch, audit, held_out, manual_approval=False) -> bool:
    # 写入前重新运行 held-out 校验
    # 需要 audit + verified evidence + explicit manual approval
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| Promotion 证据 | `bool` (命令通过即可) | patch-derived ID + overlay hash + per-scenario traces + manual approval |
| 候选覆盖层 | 无 | `create_candidate_overlay()` 临时目录和 `.candidate.json` |
| 训练/Held-out 隔离 | 无 | fixture ID 交叉检测 |
| Trace 严格验证 | 无 | 身份、来源、非零指标、命令哈希、runtime 边界和场景覆盖 |
| Silent bypass | 不可检测 | `skill_md_read` + `primary_action_invoked` 检查 |
| 测试 | 0 | 15 candidate held-out + 55 evolver/trace tests |

**验证命令**:
```bash
python3 -m pytest tests/harness/test_candidate_held_out.py -q
python3 harness/trace/validate_traces.py --strict
```

---

### Task 8: Held-Out 覆盖扩展

#### Before
```
// 4 个 held-out suite (godot-specialist, harness-run, team-ai, team-simcore)
// 4/22 skills covered (18%)
// 无 suite schema
// 无 suite validator
// 场景 ID 不统一
// 部分场景仅检查文件存在
```

#### After
```
// 12 个 held-out suite (+8 新增):
//   code-review, gate-check, replay-analyze, balance-check,
//   sprint-plan, godot-gdscript-specialist, domain-modeling, handoff
// 12/24 skills covered (50%)
// harness/skills/held_out/schema.json — JSON Schema
// harness/skills/validate_held_out_suites.py — 验证器
// 所有场景 ID 以 "held-out/" 开头
// 每个场景至少有 1 个行为验证命令
// 每个 suite 至少有 2 个场景
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| 覆盖率 | 4/22 (18%) | 12/24 (50%) |
| Suite 总数 | 4 | 12 |
| 场景总数 | ~8 | ~24+ |
| Schema | 无 | JSON Schema (draft-07) |
| 验证器 | 无 | `validate_held_out_suites.py` |
| 场景 ID 规范 | 无 | `held-out/<skill>/<scenario>` |
| 行为检查 | 部分仅检查文件存在 | 全部行为命令 |
| 测试 | 0 | 10 (test_held_out_coverage.py) |

**验证命令**:
```bash
python3 harness/skills/validate_held_out_suites.py
python3 -m pytest tests/harness/test_held_out_coverage.py -q
```

---

### Task 9: Code-Review 改进试点

#### Before
```
// 无真实 agent 执行记录
// 无 baseline trial
// 无 strategy packet 生成
// skill_evolver 无数据可对比
```

#### After
```
// harness/skills/candidates/strategy_runs/code-review-alignment-baseline-001/
//   ├── run_manifest.json    — 运行清单
//   ├── strategy-A.md        — Standards-first review 策略
//   └── strategy-B.md        — Specification-drift review 策略

// harness/trace/trials/2026-08-04-baseline.jsonl — SkillTrial v2 trace:
//   skill_md_read: true
//   primary_action_invoked: true
//   validation_exit_codes: [0, 0]
//   outcome: pass
//   findings:
//     - Standards: PASS (架构边界合规)
//     - Specification: CONCERNS (QA drift: Task 8-9 标记 PARTIAL 但实现已完成)
//     - Source Truth: PASS (12 个 weapon DAT 身份匹配)
```

#### 优势

| 改进点 | Before | After |
|--------|--------|-------|
| 本地 trial artifact | 0 | 1 baseline（未纳入固定点提交，不能独立复现） |
| QA drift 检测 | 不可能 | 本地 trace 声称检测到，尚缺 runner provenance |
| 架构验证 | 不可能 | ✅ PASS (无禁止导入) |
| 源真验证 | 不可能 | ✅ PASS (12 weapon ID 匹配) |
| 运行时修改 | 不可控 | 0 文件修改 |
| 候选生成 | N/A | 0 (无失败 trial 可对比) |
| Gate | A8 = BLOCKED | A8 = BLOCKED（无可复现 baseline/candidate runner 证据） |

**验证命令**:
```bash
python3 harness/trace/validate_traces.py --strict
cat harness/trace/trials/2026-08-04-baseline.jsonl | python3 -m json.tool
```

---

### Task 10: 最终集成

#### SkillTrial Schema 扩展

```python
# 新增字段:
runtime_paths_changed: list[str]    # 运行时代码修改 (必须为空)
findings: list[dict]                # 评审发现 (axis, verdict, details)

# load_trials() 增强:
# 过滤未知字段，避免向后兼容问题
```

#### 最终门禁

| 门禁 | 状态 | 证据 |
|------|------|------|
| A0 基线 | ✅ PASS | 源引用记录, 基线报告 |
| A1 注册语义 | ✅ PASS | 24 skills, invocation_mode + skill_kind + composes |
| A2 领域语言 | ✅ PASS | 4 contexts, CONTEXT-MAP.md, domain-modeling skill |
| A3 Code Review | ✅ PASS | 三轴评审, combat-remediation-review fixture |
| A4 垂直票单 | ✅ PASS | task schema, validate_tasks.py, 依赖图无环 |
| A5 交接 | ✅ PASS | handoff skill (#24), 10 节模板 |
| A6 候选 Held-Out | ⛔ BLOCKED | 代码门已加固；尚无覆盖全部 suite 场景的真实 candidate traces |
| A7 覆盖 | ⚠️ CONCERNS | 12/24 通过结构校验；code-review 已有具体 spec/diff fixture，其余 suite 仍需逐项增强，行为有效性依赖 fresh-agent evidence |
| A8 试点 | ⛔ BLOCKED | baseline trace 不可从固定点复现，且 0 candidates |

---

## 三、测试覆盖对比

### Before (基线 `1203b28`)

| 测试文件 | 测试数 |
|----------|--------|
| (harness 测试已存在) | ~217 |

### After (`9e113ee`, 原始报告口径)

| 新增测试文件 | 测试数 | 覆盖内容 |
|-------------|--------|---------|
| test_skill_registry_semantics.py | 11 | 组合图无环, invocation_mode, skill_kind |
| test_domain_contexts.py | 14 | 4 个词汇表完整性, 术语冲突 |
| test_code_review_skill_contract.py | 8 | 三轴协议, fixture 格式 |
| test_task_graph.py | 10 | 依赖图无环, 字段必填, status 合法 |
| test_execution_skill_contracts.py | 13 | sprint-plan, harness-run 合约 |
| test_handoff_skill_contract.py | 12 | 交接模板 10 节, 凭证脱敏 |
| test_candidate_held_out.py | 8 | HeldOutResult, promotion_eligible |
| test_held_out_coverage.py | 10 | 覆盖率 ≥50%, 场景 ID 规范 |
| test_strategy_runner.py (扩展) | +5 | packet 生成, 6 个新 section |
| test_skill_evolver.py (扩展) | +15 | promote_patch 新签名, dry-run |
| test_trace_validation.py (扩展) | +8 | 候选 trial 严格验证 |
| **新增合计** | **~116** | |

### 最终测试统计

```
原报告记录 `324 passed`，首次复核实际收集为 `336`。候选证据加固后，
2026-08-05 全量验证为 `357 passed, 0 failed`。后续仍以 pytest 的实际
collected 数为准，不用旧报告数字作为门禁输入。
```

---

## 四、24 Skills 全景

| # | Skill | Kind | Invocation | Held-Out | Composes |
|---|-------|------|-----------|----------|----------|
| 1 | godot-specialist | orchestrator | both | ✅ | gdscript, gdextension, shader, code-review |
| 2 | harness-run | orchestrator | user | ✅ | test-matrix, replay-analyze, code-review |
| 3 | team-simcore | orchestrator | user | ✅ | test-matrix, replay-analyze, code-review |
| 4 | team-ai | orchestrator | user | ✅ | test-matrix, replay-analyze, balance-check, code-review |
| 5 | architecture-decision | discipline | both | — | — |
| 6 | balance-check | gate | model | ✅ | — |
| 7 | brainstorm | orchestrator | user | — | domain-modeling |
| 8 | code-review | discipline | both | ✅ | — |
| 9 | estimate | discipline | model | — | — |
| 10 | gate-check | gate | both | ✅ | — |
| 11 | godot-gdextension-specialist | domain | model | — | — |
| 12 | godot-gdscript-specialist | domain | model | ✅ | — |
| 13 | godot-shader-specialist | domain | model | — | — |
| 14 | milestone-review | gate | both | — | — |
| 15 | replay-analyze | domain | both | ✅ | — |
| 16 | scope-check | gate | model | — | — |
| 17 | setup-engine | orchestrator | user | — | architecture-decision |
| 18 | sprint-plan | orchestrator | user | ✅ | scope-check, estimate |
| 19 | team-balance | orchestrator | user | — | balance-check, test-matrix, replay-analyze, code-review |
| 20 | team-release | orchestrator | user | — | milestone-review, gate-check, code-review |
| 21 | tech-debt | discipline | both | — | — |
| 22 | test-matrix | discipline | model | — | — |
| 23 | domain-modeling **(新)** | discipline | both | ✅ | — |
| 24 | handoff **(新)** | discipline | user | ✅ | — |

---

## 五、验证清单

执行以下命令验证全部变更:

```bash
cd ~/code/rts-ai-platform

# 1. 注册验证 (24 skills, 组合图无环)
python3 harness/skills/validate_registry.py

# 2. Task fixture 验证 (字段完整, 依赖图无环)
python3 harness/skills/validate_tasks.py

# 3. Held-out suite 验证 (12 suites, 场景 ID 规范)
python3 harness/skills/validate_held_out_suites.py

# 4. Trace 严格验证
python3 harness/trace/validate_traces.py --strict

# 5. 全量 harness 测试（以 pytest 实际 collected 数为准）
python3 -m pytest tests/harness -q -p no:warnings

# 6. 运行时业务代码零修改验证
git diff --name-only 1203b28..9e113ee | grep -E "^(simcore|agents|godot|proto)/"
# 期望输出: 空

# 7. 变更范围验证
git diff --stat 1203b28..9e113ee | tail -1
# 期望输出: 55 files changed, 6486 insertions(+), 178 deletions(-)
```

---

## 六、已知限制

1. **Gate A6-A8 = BLOCKED**: candidate promotion 代码已改为 fail-closed，但还没有真实 runner 证据。任意 `candidate_id`/`agent_run_id` 字符串不再能授权 promotion。
2. **Held-out 结构覆盖 50%**: 12/24 skills 有 suite；code-review 已补两组具体 spec/diff/expected fixture，但还没有 fresh-agent trace。其余 suite 仍需逐项加入等价的行为 fixture。“结构覆盖”不能表述为“行为验证完成”。
3. **Readability PENDING**: SC1 combat 的密集可读性指标仍需在 Godot Test Mode 中人工评估。
4. **`make proto` pre-existing**: `service.proto` 找不到 `rts.state.GameStateSnapshot`，这是基线已存在的问题，本次变更未引入。

---

## 七、架构影响

```
                    ┌─────────────────────────────────────────┐
                    │           Agent Skills Layer             │
                    │  24 skills (domain/orchestrator/gate/    │
                    │  discipline) with invocation_mode +      │
                    │  composes graph                         │
                    └────────────┬────────────────────────────┘
                                 │
                    ┌────────────▼────────────────────────────┐
                    │          Harness Layer                   │
                    │  ┌──────────┐  ┌──────────┐            │
                    │  │ Task     │  │ Held-Out │            │
                    │  │ Schema   │  │ Suite    │            │
                    │  │ +Graph   │  │ +Schema  │            │
                    │  └────┬─────┘  └────┬─────┘            │
                    │       │              │                   │
                    │  ┌────▼──────────────▼─────┐           │
                    │  │   SkillEvolver           │           │
                    │  │   ├── HeldOutResult      │           │
                    │  │   ├── promote_patch()    │           │
                    │  │   └── candidate overlay  │           │
                    │  └────────────┬─────────────┘           │
                    └───────────────┼─────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────────────┐
                    │          Trace Layer                      │
                    │  SkillTrial v2:                           │
                    │    candidate_id, agent_run_id,            │
                    │    runtime_paths_changed, findings        │
                    │  validate_traces.py --strict              │
                    └───────────────────────────────────────────┘
                                   │
     ┌─────────────────────────────┼─────────────────────────────┐
     │         运行时业务代码 (零修改)                              │
     │  simcore/ | agents/ | godot/ | proto/                    │
     └───────────────────────────────────────────────────────────┘
```

**核心改进**: Skills → Harness → Trace 三层已结构化。Promotion 现在要求
patch 派生的 candidate ID、overlay 元数据和哈希、每场景唯一 agent run、
runner provenance、非零执行指标及 validation hashes 全部一致。没有真实
runner trace 时系统保持 BLOCKED，而不是把 command-only PASS 当作候选验证。

## 八、修复后的 Candidate 执行流程

1. `skill_evolver` 根据 `skill_name + patch_content` 派生 candidate ID，禁止调用者自报身份。
2. `create_candidate_overlay()` 写入候选 `SKILL.md` 和 `.candidate.json`，记录 base、patch、overlay 三个哈希。
3. `generate_held_out_candidate_packets()` 为 suite 中每个场景生成独立 packet 和唯一 `agent_run_id`。
4. Fresh Agent 必须先读取 overlay，而非仓库中的 base skill，并输出 SkillTrial JSONL。
5. 再次执行 `skill_evolver --apply --candidate-trace-file <trace.jsonl>`；只有全部场景证据匹配时才可 promotion。

旧参数 `--candidate-id` 和 `--agent-run-id` 只保留兼容提示，不能单独成为 promotion 证据。
