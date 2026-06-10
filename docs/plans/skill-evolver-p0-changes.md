# SkillEvolver P0 变更清单

> 生成时间: 2026-05-30
> 分支: 未提交 (所有变更在本地工作区)

---

## 新增文件

### 1. 架构决策记录
| 文件 | 说明 |
|------|------|
| `docs/architecture/adr-skill-evolver-harness.md` | SkillEvolver 作用域边界定义：允许/禁止/间接三类 |

### 2. Skill Registry + Schema
| 文件 | 说明 |
|------|------|
| `harness/skills/schema.json` | Skill 元数据 JSON Schema (draft-07)，required: name, description, primary_action, expected_tool_calls, validation_commands, owner_domain, layer_constraints, known_failure_modes |
| `harness/skills/registry.json` | 4个核心 skill 注册条目：godot-specialist, harness-run, team-simcore, team-ai |

### 3. Trace Schema
| 文件 | 说明 |
|------|------|
| `harness/trace/schema.py` | SkillTrial 数据类 + record_trial() + load_trials()，写入 harness/trace/trials/YYYYMMDD.jsonl + skill_usage.jsonl |
| `harness/trace/__init__.py` | 空 |

### 4. Skill Evolver 核心
| 文件 | 说明 |
|------|------|
| `harness/evolve/skill_evolver.py` | 完整闭环: contrast_trials → audit_patch → validate_held_out → promote_patch / rollback_skill_md；STRATEGY_TEMPLATES (godot-vfx 4策略, simcore-replay 3策略)；_backup_skill_md + rollback |
| `harness/evolve/__init__.py` | 空 |

### 5. 校验脚本
| 文件 | 说明 |
|------|------|
| `harness/skills/validate_registry.py` | 校验 registry.json 是否符合 schema + 项目级检查(layer命名、owner_domain、expected_tool_calls非空、validation_commands非空、skill目录存在、held_out_suite路径存在、无重复name)；支持 --fix 自动补全可选字段 |
| `harness/trace/validate_traces.py` | 校验 trials/*.jsonl 是否符合 SkillTrial required 字段 + outcome 枚举 + task_description 非空；--strict 模式检查 silent_bypass 一致性 |

### 6. Held-Out Suite
| 文件 | 说明 |
|------|------|
| `harness/skills/held_out/godot-specialist/suite.json` | 3场景: VFX对齐、HUD布局、fog渲染 |
| `harness/skills/held_out/team-simcore/suite.json` | 4场景: 移动、战斗、经济、replay |
| `harness/skills/held_out/team-ai/suite.json` | 3场景: build order、combat micro、scouting |
| `harness/skills/held_out/harness-run/suite.json` | 4场景: 前端bug、后端bug、测试失败、架构修复 |

### 7. 测试
| 文件 | 说明 |
|------|------|
| `tests/harness/test_skill_evolver.py` | 27 个测试：Path正确性(5)、Registry Schema(5)、Trace Roundtrip(2)、Auditor拦截(7)、Strategy模板(4)、Promotion+Rollback(3) |

### 8. 计划文档
| 文件 | 说明 |
|------|------|
| `docs/plans/skill-evolver-breakdown.md` | Phase 0-7 全量分解，50+子任务，依赖图，优先级 |

---

## 修改文件

### 1. Executor — 接入真实 Trace
| 文件 | 改动说明 |
|------|----------|
| `harness/devops_harness/executor/scripts/task_state.py` | 新增 `_record_skill_trial()` 函数(47行)；在 `complete_task()` 中调用，自动写 SkillTrial 到 harness/trace/trials/；通过 `args.skill_name`, `args.strategy_label` 等参数传递 |

### 2. Godot — Fog 闪烁修复
| 文件 | 改动说明 |
|------|----------|
| `godot/scripts/game_view.gd` | (1) 新增 `_fog_alpha`(PackedFloat32Array) + `_fog_prev_tiles`(PackedInt32Array) + `FOG_FADE_FRAMES=10`；(2) `_parse()` fog 段加入平滑：state 2→1 触发淡出，state 2→0 或 1→0 立即重置；(3) `_draw_fog_of_war()` 使用 `_fog_alpha` 替代 raw state lookup；(4) `_is_in_fog()` 使用 `_fog_alpha < 0.15` 判断；(5) `_get_state_for_minimap()` 传 `fog_alpha`；(6) `_on_start()` 对 `map_width <= 0` 做 fallback 到 64；(7) `_draw()` 中 elevation 默认关闭 (`_show_elevation=false`)；(8) 新增 `_elev_btn` 按钮 + `_toggle_elevation()` |
| `godot/scripts/minimap_rect.gd` | fog 渲染使用 `fog_alpha`(PackedFloat32Array) 替代 raw `fog_tiles` state；entity visibility 用 `fog_alpha < 0.15` |

### 3. SimCore — gRPC Server map_width=0 修复
| 文件 | 改动说明 |
|------|----------|
| `simcore/grpc_server.py` | `_state_to_snapshot()`: 新增 `snap.config.map_width = state.map_width` + `snap.config.map_height = state.map_height`；`_snapshot_dict_to_proto()`: 同样新增 `proto.config.map_width/height` |

### 4. Proto 生成文件 — import 路径修复
| 文件 | 改动说明 |
|------|----------|
| `simcore/proto_out/proto/service_pb2.py` | `from proto import` → `from simcore.proto_out.proto import` |
| `simcore/proto_out/proto/service_pb2_grpc.py` | 同上 |

---

## 变更统计

| 类别 | 数量 |
|------|------|
| 新增文件 | 13 |
| 修改文件 | 6 |
| 新增 Python 代码 | ~1200 行 |
| 新增测试 | 27 个 |
| 项目全量测试 | 602 passed, 1 skipped, 0 failed |

---

## 修正记录 (第二轮)

| # | 问题 | 修正 |
|---|------|------|
| 1 | skill_evolver 默认直接写 SKILL.md，PermissionError 且太激进 | 改为默认 `--dry-run`，只有 `--apply` 才允许写 SKILL.md / registry；新增 `evolve_skill_dry()` |
| 2 | task_state.py complete_parser 缺 trace CLI 参数 | 新增 `--skill-name` `--strategy-label` `--skill-md-read` `--primary-action-invoked` `--validation-commands-run` `--validation-results` `--token-count` `--turn-count` `--duration-seconds` |
| 3 | held-out godot-fog-003 有 `|| true`，吞掉失败 | 改为 `python3 -m pytest tests/simcore/test_fog.py -q -x`（无 `|| true`） |
| 4 | 文档 proto import 描述有误 `from simcore.proto_out.proto.import` | 修正为 `from simcore.proto_out.proto import` |
| 5 | 运行产物 (backups/candidates/trials) 混入仓库 | 新增 `.gitignore`: `harness/skills/.gitignore` + `harness/trace/.gitignore` + `harness/evolve/.gitignore` |

---

## 需要人工校验的重点

1. **`task_state.py` 修改** — `_record_skill_trial()` 在 `complete_task()` 中的调用时机和参数传递是否合理
2. **`game_view.gd` fog 平滑逻辑** — `_fog_alpha` 的初始化和 `_process()` 中 `queue_redraw()` 是否会导致性能问题
3. **`grpc_server.py` map_width/height** — 确认 `GameState` 实例在 `_state_to_snapshot()` 调用时 `map_width`/`map_height` 已被赋值
4. **held-out suite** — `validation_commands` 在你的环境中是否都能执行（依赖 PATH 中的 python3）
5. **proto import 路径** — 确认 `from simcore.proto_out.proto.import` 在所有运行环境下都能正常工作
