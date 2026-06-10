# SkillEvolver 实施计划 — 详细分解

> 论文: "Skill Evolution via Contrastive Trace Analysis"
> 核心价值: 把 Hermes 的一次性任务执行升级为可审计、可复用、可进化的开发技能系统

---

## 现状盘点

| 已有 | 缺失 |
|------|------|
| `.agents/skills/` 20个 skill (有 SKILL.md) | 无 `primary_action` / `validation_commands` / `known_failure_modes` 元数据 |
| `harness/devops_harness/executor` (SKILL.md) | 无执行轨迹记录 (trace) |
| `harness/memory/episodes/` (2条) | 无 skill_trial.jsonl / skill_usage.jsonl |
| `harness/telemetry.py` | 只有游戏指标，无 skill 使用审计 |
| `harness/promotion.py` | 只有 AI 版本晋升，无 skill 晋升 |
| `docs/architecture/four-layers.md` | 无 SkillEvolver 作用域 ADR |

---

## Phase 0: 边界定义

**目标**: 明确 SkillEvolver 只用于开发侧 agent skill，不直接改 runtime AI

### 产物
| 文件 | 状态 |
|------|------|
| `docs/architecture/adr-skill-evolver-harness.md` | ✅ 已创建 |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 0.1 | 编写 ADR，定义允许/禁止作用域 | ADR 包含 ✅允许/❌禁止/⚠️间接 三个分类 | 无 |
| 0.2 | ADR 中加入四层架构约束 (L0-L3) | 每层有明确的 skill 读写权限定义 | 0.1 |
| 0.3 | ADR 中加入 silent-bypass 检测规则 | 3 条检测规则，覆盖 SKILL.md 未读/primary_action 未调用/规则无证据 | 0.1 |
| 0.4 | 在 AGENTS.md 中加入 SkillEvolver 作用域引用 | AGENTS.md 开发指南章节引用 ADR | 0.1 |

---

## Phase 1: 补齐 Skill Registry

**目标**: 让每个 skill 有可审计元数据

### 产物
| 文件 | 状态 |
|------|------|
| `harness/skills/schema.json` | ✅ 已创建 |
| `harness/skills/registry.json` | ✅ 已创建 (4个 skill) |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 1.1 | 定义 schema.json (primary_action, primary_script, expected_tool_calls, validation_commands, owner_domain, layer_constraints, known_failure_modes, silent_bypass_risks) | JSON Schema draft-07, 通过 `jsonschema` 验证 | 0.2 |
| 1.2 | 填充 registry.json (先做 4 个核心 skill: godot-specialist, harness-executor, team-simcore, team-ai) | 4 条记录，每条通过 schema 验证 | 1.1 |
| 1.3 | 为剩余 ~16 个 skill 补齐 registry 条目 | 所有 skill 在 registry 中有完整条目 | 1.2 |
| 1.4 | 在每个 SKILL.md front matter 中加入 `primary_action` 字段 | `grep -r primary_action .agents/skills/*/SKILL.md` 全部有结果 | 1.1 |
| 1.5 | 在每个 SKILL.md 中加入 `validation_commands` 代码块 | 每个 SKILL.md 有 `## Validation` 章节 | 1.1 |
| 1.6 | 在每个 SKILL.md 中加入 `known_failure_modes` 章节 | 每个 SKILL.md 有 `## Known Failure Modes` 章节 | 1.1 |
| 1.7 | 写 registry 校验脚本 `harness/skills/validate_registry.py` | `python3 harness/skills/validate_registry.py` 返回 0 | 1.2, 1.3 |

---

## Phase 2: 升级 Trace Schema

**目标**: 把 Hermes/Codex 执行任务的轨迹记录成可对比数据

### 产物
| 文件 | 状态 |
|------|------|
| `harness/trace/schema.py` | ✅ 已创建 (SkillTrial + record_trial + load_trials) |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 2.1 | 定义 SkillTrial 数据类 (task_id, skill_name, skill_md_read, primary_script_called, primary_action_invoked, tool_calls, validation_commands_run, validation_results, functional_verification, failure_log_summary, token/turn/duration, touched_files, outcome, silent_bypass_detected, silent_bypass_details, strategy_label) | dataclass 字段完整，to_dict()/to_jsonl() 可用 | 1.1 |
| 2.2 | 实现 `record_trial()` — 写入 `harness/trace/trials/YYYYMMDD.jsonl` + `harness/trace/skill_usage.jsonl` | 两条记录文件存在且格式正确 | 2.1 |
| 2.3 | 实现 `load_trials(skill_name, outcome)` — 按 skill/outcome 过滤读取 | 返回正确过滤的 SkillTrial 列表 | 2.1 |
| 2.4 | 修改 `harness/devops_harness/executor` SKILL.md — 在 EXECUTE 步骤中加入轨迹记录指令 | executor trace 中包含 skill_md_read, primary_action_invoked, validation_commands_run | 2.1, 1.4 |
| 2.5 | 修改 `harness/devops_harness/executor/scripts/execute_task.py` — 自动提取 tool_calls, touched_files, token/turn | 执行后自动生成 SkillTrial JSON | 2.4 |
| 2.6 | 写 trace 校验脚本 `harness/trace/validate_traces.py` | 检查所有 trial 是否符合 schema | 2.1 |
| 2.7 | 集成到 CI: PR 合入时检查 trace 格式 | CI step 通过 | 2.6 |

---

## Phase 3: Strategy-Diversified Exploration

**目标**: 同一任务用 3-4 个高层策略并行试

### 产物
| 文件 | 状态 |
|------|------|
| `harness/evolve/skill_evolver.py` (STRATEGY_TEMPLATES) | ✅ 已创建 |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 3.1 | 定义 ExplorationStrategy 数据类 (label, description, focus_files, extra_rules, priority) | dataclass 可实例化 | 1.1 |
| 3.2 | 实现 godot-vfx 的 4 策略模板 (A:资源manifest, B:SpriteLoader裁剪, C:场景/相机/选择圈, D:截图回归) | STRATEGY_TEMPLATES["godot-vfx"] 有 4 条 | 3.1 |
| 3.3 | 实现 simcore-replay 的 3 策略模板 (A:replay hash, B:规则逻辑, C:gRPC边界) | STRATEGY_TEMPLATES["simcore-replay"] 有 3 条 | 3.1 |
| 3.4 | 实现 team-ai 的 3 策略模板 (A:build order, B:combat micro, C:scouting) | STRATEGY_TEMPLATES["team-ai"] 有 3 条 | 3.1 |
| 3.5 | 实现 `get_strategies(task_type)` 函数 | 输入任务类型返回策略列表，未知类型返回默认策略 | 3.2-3.4 |
| 3.6 | 实现 `inject_strategy_to_prompt(strategy, base_prompt)` — 将策略规则注入 Hermes 任务提示 | 返回增强后的 prompt | 3.5 |
| 3.7 | 修改 harness scheduler: 对同一任务并行派发多个策略 | 同一 task_id 产生多条 trial，strategy_label 不同 | 3.6, 2.4 |
| 3.8 | 验证: 手动对一个 Godot VFX 任务跑 4 策略对比 | 4 条 trial 记录在 skill_trial.jsonl 中 | 3.7 |

---

## Phase 4: Contrastive Skill Update

**目标**: 比较成功/失败轨迹，自动生成 skill patch

### 产物
| 文件 | 状态 |
|------|------|
| `harness/evolve/skill_evolver.py` (contrast_trials, save_patch_candidate) | ✅ 已创建 |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 4.1 | 实现 `contrast_trials(skill_name)` — 加载 pass/fail trials，分析失败模式 | 输入 skill_name，输出 list[SkillPatch] | 2.3, 2.1 |
| 4.2 | 实现 silent-bypass 检测分析 | bypass_fails 非空时生成对应 patch | 4.1, 1.1 |
| 4.3 | 实现 SKILL.md 未读取分析 | unread_fails 非空时生成对应 patch | 4.1 |
| 4.4 | 实现 primary_action 未调用分析 | no_action_fails 非空时生成对应 patch | 4.1 |
| 4.5 | 实现 `save_patch_candidate()` — 写 candidates/<skill>/<timestamp>/{patch.md, rationale.json, evidence.json} | 目录和文件存在 | 4.1 |
| 4.6 | 验证: 对已有 trial 数据跑 contrast，确认生成 patch | 至少生成 1 个 patch candidate | 4.5, 3.8 |

---

## Phase 5: Independent Auditor

**目标**: 实现论文里的 fresh-session Auditor

### 产物
| 文件 | 状态 |
|------|------|
| `harness/evolve/skill_evolver.py` (audit_patch, GENERIC_AUDIT_RULES, PROJECT_AUDIT_RULES) | ✅ 已创建 |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 5.1 | 实现通用检查: hardcoded seed/path/entity_id | regex 匹配出问题 | 4.5 |
| 5.2 | 实现通用检查: 引用训练实例文件名 | 关键词匹配 | 4.5 |
| 5.3 | 实现通用检查: 脚本长度 > 8000 chars | 长度检查 | 4.5 |
| 5.4 | 实现通用检查: missing primary_script | SKILL.md 内容检查 | 4.5 |
| 5.5 | 实现通用检查: silent-bypass 风险 | "必须/永远/不要" 无 validation_commands 证据 | 4.5 |
| 5.6 | 实现项目检查: 四层架构违反 | skill 跨层修改检测 | 5.5, 0.2 |
| 5.7 | 实现项目检查: LLM in SimCore high-freq loop | simcore + llm 关键词 | 5.5 |
| 5.8 | 实现项目检查: Godot 任务缺 --check-only | godot skill + 缺 check-only | 5.5 |
| 5.9 | 实现项目检查: SimCore 任务缺 determinism test | simcore skill + 缺 determinism | 5.5 |
| 5.10 | 实现项目检查: 训练任务缺 held-out seeds | training + 缺 held-out | 5.5 |
| 5.11 | 实现项目检查: VFX 任务缺截图或 manifest 证据 | vfx + 缺 screenshot/manifest | 5.5 |
| 5.12 | 实现 `audit_patch()` 统一入口 | 返回 AuditResult(accepted, issues) | 5.1-5.11 |
| 5.13 | 写 auditor 测试: 构造恶意 patch，确认被拦截 | `pytest tests/harness/test_auditor.py` 全绿 | 5.12 |

---

## Phase 6: Held-Out Validation 和 Promotion

**目标**: 避免 skill 只对当前任务有效

### 产物
| 文件 | 状态 |
|------|------|
| `harness/skills/held_out/` (4 个 suite) | ✅ 已创建 |
| `harness/evolve/skill_evolver.py` (validate_held_out, promote_patch) | ✅ 已创建 |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 6.1 | 创建 godot-specialist held-out suite (3 场景: VFX对齐, HUD布局, fog渲染) | suite.json 存在且格式正确 | 5.12 |
| 6.2 | 创建 team-simcore held-out suite (4 场景: 移动, 战斗, 经济, replay) | suite.json 存在 | 5.12 |
| 6.3 | 创建 team-ai held-out suite (3 场景: build order, combat micro, scouting) | suite.json 存在 | 5.12 |
| 6.4 | 创建 harness-executor held-out suite (4 场景: 前端bug, 后端bug, 测试失败, 架构修复) | suite.json 存在 | 5.12 |
| 6.5 | 实现 `validate_held_out()` — 执行 suite 中任务并收集结果 | 遍历 suite，执行 validation_commands | 6.1-6.4 |
| 6.6 | 实现 `promote_patch()` — audit pass + held-out pass 后更新 SKILL.md | SKILL.md 内容实际被修改 | 6.5, 5.12 |
| 6.7 | 实现晋升回滚: 如果 held-out 失败，恢复原 SKILL.md | 备份文件存在 | 6.6 |
| 6.8 | 验证: 对一个 patch 走完 audit → held-out → promote 全流程 | skill version 递增 | 6.6, 6.7 |

---

## Phase 7: 接入 RTS Runtime (策略知识库)

**目标**: 把学到的 procedural knowledge 供 L2 agent 使用

### 产物
| 文件 | 状态 |
|------|------|
| `agents/runtime/playbooks/*.json` | 待创建 |
| `agents/prompts/rts_decision_v2.md` | 待创建 |

### 任务分解
| # | 任务 | 验收标准 | 依赖 |
|---|------|----------|------|
| 7.1 | 定义 playbook JSON schema (trigger, action, priority, evidence_source) | JSON Schema 文件存在 | 6.8 |
| 7.2 | 从 team-ai evolved skill 中提取 build order templates | 至少 3 个 build order playbook | 7.1, 6.8 |
| 7.3 | 从 team-ai evolved skill 中提取 combat micro decision rules | 至少 3 个 micro playbook | 7.1, 6.8 |
| 7.4 | 从 team-ai evolved skill 中提取 failure recovery rules | 至少 2 个 recovery playbook | 7.1, 6.8 |
| 7.5 | 编写 rts_decision_v2.md — 整合 playbook 引用 | prompt 文件包含 playbook 引用格式 | 7.2-7.4 |
| 7.6 | 实现编译: 高频 playbook → 纯脚本 (减少 LLM 推理) | 至少 1 个 playbook 被编译为 Python 脚本 | 7.2-7.4 |
| 7.7 | 验证: runtime agent 使用 v2 prompt 的表现 >= baseline | 对比测试 10 局胜率不降 | 7.5 |
| 7.8 | 与 GRPO/league 训练打通: 失败 replay 作为 skill evolution evidence | 5 条 replay-derived evidence 进入 candidates | 7.7 |

---

## 优先级排序

### P0 (立即做)
| 编号 | 任务 | Phase | 预估 |
|------|------|-------|------|
| 0.1 | ADR 边界定义 | 0 | 30min |
| 1.1-1.2 | schema + 4核心skill registry | 1 | 1h |
| 2.1-2.3 | SkillTrial 数据类 + 读写 | 2 | 1.5h |
| 5.1-5.5 | 通用 Auditor 检查 | 5 | 1.5h |

### P1 (本周)
| 编号 | 任务 | Phase | 预估 |
|------|------|-------|------|
| 1.3-1.7 | 剩余skill registry + SKILL.md 补字段 | 1 | 2h |
| 2.4-2.7 | executor 集成 trace + CI | 2 | 2h |
| 3.1-3.8 | 策略多样化探索 | 3 | 3h |
| 4.1-4.6 | Contrastive Update | 4 | 2h |
| 5.6-5.13 | 项目专属 Auditor + 测试 | 5 | 2h |

### P2 (下周)
| 编号 | 任务 | Phase | 预估 |
|------|------|-------|------|
| 6.1-6.8 | Held-out suites + Promotion | 6 | 4h |
| 7.1-7.4 | Playbook schema + 提取 | 7 | 3h |

### P3 (后续)
| 编号 | 任务 | Phase | 预估 |
|------|------|-------|------|
| 7.5-7.8 | Runtime prompt 集成 + 训练打通 | 7 | 4h |

---

## 依赖关系图

```
Phase 0 ──→ Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4
  │              │           │           │           │
  │              │           │           │           │
  └──────────────┴───────────┴───────────┴──────→ Phase 5
                                                    │
                                               Phase 6
                                                    │
                                               Phase 7
```

Phase 5 的通用检查只依赖 Phase 4 的 patch 输出，
项目专属检查依赖 Phase 0 的架构定义。
Phase 6 和 7 可以在 Phase 5 完成后并行推进。
