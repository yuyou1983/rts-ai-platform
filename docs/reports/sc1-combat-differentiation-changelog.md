# SC1 战斗差异化更新日志

> **2026-08-03 校验更正**: 以下声明经 `docs/plans/2026-08-03-sc1-combat-differentiation-remediation-plan.md` 审查后撤回到待修复状态：
> - "12/12 正式闭环" — 实际未经过生产构造链路（R1: `_build_unit_entity()` 丢弃 semantic combat fields）
> - "Storm 自动测试" — 实际空命令 tick 不推进（R5）
> - "replay 确定" — E2E 测试直接调用 `resolve_combat()`，未经过 engine/construction/transport（R6）
> - "人工完成" — 30v30 与 10 matchup 未人工执行（R9）
>
> 自动测试通过只证明 fixture 自洽，不证明正式生产链路已贯通。下方原文保留供参考。
>
> **实际变更**: `git diff --shortstat 87ddbd8..HEAD` = 42 files changed, 14596 insertions(+), 356 deletions(-)（非 973 文件）。

**分支**: `codex/sc1-combat-differentiation`
**时间**: 2026-07-29 ~ 2026-07-31
**HEAD**: `5b8b925`
**总变更**: 42 files changed, +14,596 insertions(-), -356 deletions(-)

---

## 概述

为 RTS-AI 平台的 12 个 SC1 代表性单位实现了完整的战斗差异化系统，覆盖三族（Terran/Zerg/Protoss）的武器类型、伤害矩阵、视觉表现和诊断验证。

### 12 个代表单位

| 种族 | 单位 | 武器 ID | 武器类型 | 特殊机制 |
|------|------|---------|---------|---------|
| Terran | Marine | `terran_c10_rifle` | concussive | — |
| Terran | Firebat | `terran_flame_thrower` | concussive | 溅射 |
| Terran | Vulture | `terran_fragmentation_grenade` | concussive | — |
| Terran | Tank | `terran_arclite_cannon` | explosive | hit_count=2 |
| Zerg | Zergling | `zerg_claws` | normal | — |
| Zerg | Hydralisk | `zerg_needle_spines` | explosive | — |
| Zerg | Mutalisk | `zerg_glave_wurm` | normal | 链式弹跳 1.0/0.333/0.111 |
| Zerg | Ultralisk | `zerg_kaiser_blades` | normal | — |
| Protoss | Zealot | `protoss_psi_blades` | normal | hit_count=2 |
| Protoss | Dragoon | `protoss_phase_disruptor` | explosive | — |
| Protoss | Templar | `protoss_psionic_storm` | spell | 周期伤害 |
| Protoss | Reaver | `protoss_scarab` | normal | 溅射 + 弹药 |

### SC1 伤害矩阵

| 武器类型 | Light | Medium | Heavy |
|---------|-------|--------|-------|
| Normal | 100% | 100% | 100% |
| Explosive | 50% | 75% | 100% |
| Concussive | 100% | 50% | 25% |

### 盾牌规则
- 盾牌吸收全额基础伤害（不受护甲、体型倍率影响）
- 穿透盾牌后的剩余伤害才计算体型倍率和护甲减免
- 最低伤害保底 0.5

---

## Task 完成详情

### Task 0: 基线建立 + 计划定义
**Commit**: `87ddbd8` + `49c8f7d` + `8187039`
**日期**: 2026-07-29

- 建立 QA 基线报告
- 编写 1,963 行执行计划 (`docs/plans/2026-07-29-sc1-combat-differentiation-execution-plan.md`)
- 定义 ADR: Combat Visual Events 架构 (`docs/architecture/adr-combat-visual-events.md`)
- 操作手感 P0/P1 改动（相机、选择、输入反馈）

**文件变更**: 18 files, +3,108 lines

---

### Task 1: Protobuf 战斗事件契约
**Commit**: `1030ed5`
**日期**: 2026-07-29

- 在 `proto/state.proto` 中定义 `CombatEvent` 消息体
- 生成 Python protobuf 代码
- 164 行 proto round-trip 测试

**文件变更**:
```
proto/state.proto                           |  57 +++++
simcore/proto_out/proto/state_pb2.py        |  32 +++
tests/proto/test_combat_event_proto.py     | 164 +++++
5 files changed, 245 insertions(+), 20 deletions(-)
```

---

### Task 1A: SC1 DAT 战斗真值审计
**Commit**: `f1b05cf`
**日期**: 2026-07-30

- 审计脚本 `tools/sc1_assets/audit_combat_reference.py`
- 生成 2,650 行战斗参考数据 `tools/sc1_assets/combat_reference.json`
- 对照 OpenBW 固定 commit 裁决每个字段

**文件变更**:
```
tools/sc1_assets/audit_combat_reference.py |  233 +++
tools/sc1_assets/combat_reference.json     | 2,650 ++++++
2 files changed, 2,883 insertions(+)
```

---

### Task 2: 语义武器定义
**Commit**: `c6509f2`
**日期**: 2026-07-30

- `data/combat/weapons.json`: 12 个武器完整定义（damage_type, hit_count, delivery_type, splash_profile, chain_fractions 等）
- `simcore/data/unit_stats.json`: 扩展至 1,029 行单位属性
- 326 行代表武器测试

**文件变更**:
```
data/combat/weapons.json                         | 264 ++++
data/combat/sc1_representative_reference.json    | 2,650 ++++++
simcore/data/unit_stats.json                     | 1,029 +++++
tests/simcore/test_sc1_representative_weapons.py | 326 ++++
5 files changed, 4,322 insertions(+)
```

---

### Task 3: 发射权威战斗事件
**Commit**: `25396cd`
**日期**: 2026-07-30

- `simcore/combat_events.py`: 事件类型定义（ATTACK_STARTED, IMPACT_RESOLVED, UNIT_DESTROYED, SPELL_RESOLVED）
- `simcore/rules.py`: resolve_combat 中发射事件，含完整字段（weapon_id, damage_multiplier, shield/health split, chain_index, splash_fraction 等）
- 335 行事件发射测试

**文件变更**:
```
simcore/combat_events.py                    | 114 +++++
simcore/engine.py                           |  17 +-
simcore/rules.py                            | 268 ++++-
tests/simcore/test_combat_event_emission.py | 335 +++++
4 files changed, 730 insertions(+), 4 deletions(-)
```

---

### Task 4: 战斗事件传输到前端和回放
**Commit**: `4506688`
**日期**: 2026-07-30

- `simcore/grpc_server.py` + `grpc_client.py`: gRPC 传输 combat_events
- `simcore/engine.py`: 集成事件流到引擎主循环
- 159 行传输测试

**文件变更**:
```
simcore/engine.py                            |   6 +-
simcore/grpc_client.py                       |  38 +-
simcore/grpc_server.py                       |  82 ++-
tests/simcore/test_combat_event_transport.py | 159 +++++
4 files changed, 281 insertions(+), 4 deletions(-)
```

---

### Task 5: Godot 从权威事件驱动战斗视觉
**Commit**: `f233f9c`
**日期**: 2026-07-30

- `godot/scripts/combat_visual_controller.gd`: 重写为事件驱动（-273/+474 行）
- `godot/scripts/game_view.gd`: 接入事件管线
- `godot/scripts/test_combat_event_pipeline.gd`: Godot headless 测试
- `tests/godot/test_combat_event_contract.py`: Python 侧契约测试

**文件变更**:
```
godot/scripts/combat_visual_controller.gd   | 474 ++--
godot/scripts/game_view.gd                  |  27 +-
godot/scripts/test_combat_event_pipeline.gd  |  92 +++
tests/godot/test_combat_event_contract.py   |  75 +++
4 files changed, 395 insertions(+), 273 deletions(-)
```

---

### Task 7: Weapon Visual Catalog 集成
**Commit**: `67c7dda`
**日期**: 2026-07-31

- `godot/resources/vfx/weapon_visual_catalog.json`: 12 个武器视觉映射
- `godot/resources/vfx/vfx_catalog.json`: 216 行 VFX 效果定义
- `godot/scripts/vfx_manager.gd`: 新增 `spawn_weapon_event()` 方法，支持所有 12 种弹道样式
- `godot/scripts/combat_visual_controller.gd`: `_emit` 方法改走 `spawn_weapon_event` 路径
- `tests/godot/test_weapon_visual_catalog.py`: 500 行测试（30 个测试用例）

**文件变更**:
```
godot/resources/vfx/weapon_visual_catalog.json |   1 +
godot/resources/vfx/vfx_catalog.json           | 216 +++
godot/resources/presentation_manifest.json     |  12 +
godot/resources/unit_type_catalog.json         |  12 +
godot/scripts/vfx_manager.gd                   | 170 ++++
godot/scripts/combat_visual_controller.gd     |  13 +-
godot/scripts/test_combat_event_pipeline.gd   |   8 +-
tests/godot/test_weapon_visual_catalog.py      | 500 +++++
tests/godot/test_operation_feel_contract.py   | 131 +++
9 files changed, 1,060 insertions(+), 3 deletions(-)
```

---

### Task 7A: 统一弹道/命中结算
**Commits**: `02bbf80` + `13312d0`
**日期**: 2026-07-31

#### 02bbf80 — 统一结算模块
- `simcore/combat_resolution.py` (425 行): 统一 `resolve_weapon_impact()` 入口
  - SC1 伤害矩阵：shield → armor → size multiplier → min damage
  - 盾牌吸收全额伤害，不受护甲/体型影响
- 375 行单元测试

#### 13312d0 — 弹道路由
- `simcore/projectile.py`: 确定性 ID (`proj_{tick}_{seq}`)，通过 `resolve_weapon_impact` 结算
- `simcore/engine.py`: 传入 `combat_events` + `kill_feed` 到 `process_projectiles`
- 275 行弹道集成测试

**文件变更**:
```
simcore/combat_resolution.py                       | 425 +++
simcore/rules.py                                   |   9 +-
simcore/projectile.py                              | 122 ++-
simcore/engine.py                                  |   9 +-
tests/simcore/test_combat_resolution.py            | 375 +++
tests/simcore/test_projectile_combat_integration.py| 275 +++
6 files changed, 1,189 insertions(+), 26 deletions(-)
```

---

### Task 8: Terran 4-unit 闭环 + SC1 盾牌修复
**Commit**: `41698d3`
**日期**: 2026-07-31

- **SC1 盾牌机制修复**: `rules.py` 中 3 处（显式攻击、自动攻击、溅射）统一为：
  - 盾牌吸收全额基础伤害（无体型倍率、无护甲减免）
  - 穿透后剩余伤害才计算体型倍率和护甲
- 4 个 Terran 战斗场景测试：
  - Marine → Zergling (concussive vs light, 6 dmg)
  - Firebat → 3 Zerglings (concussive splash 16+8)
  - Vulture → Zealot (concussive vs shield)
  - Tank → Dragoon (explosive vs heavy shield)

**文件变更**:
```
simcore/rules.py                                 |  70 ++++---
tests/simcore/test_combat_event_emission.py      |   6 +-
tests/simcore/test_sc1_representative_weapons.py | 232 +++++
3 files changed, 282 insertions(+), 26 deletions(-)
```

---

### Task 9: Zerg 4-unit 闭环 + Mutalisk 链式弹跳
**Commit**: `75dd70d`
**日期**: 2026-07-31

- **Mutalisk 链式弹跳** (`_apply_chain` 函数):
  - 从 `weapons.json` 加载配置: fractions=[1.0, 0.333, 0.111], radius=3
  - 确定性目标选择: 按 (distance, entity_id) 排序
  - 每次弹跳正确应用 SC1 盾牌→护甲逻辑
  - 发射 `impact_resolved` 事件带 `chain_index` 0, 1, 2
- 4 个 Zerg 战斗场景测试：
  - Zergling → Marine (normal vs light)
  - Hydralisk → Dragoon (explosive vs heavy shield)
  - Mutalisk → 3 Marines (chain bounce 9/2.997/0.999)
  - Ultralisk → Zealot (heavy melee vs shield)

**文件变更**:
```
simcore/rules.py                                 | 171 +++
tests/simcore/test_sc1_representative_weapons.py | 235 +++++
2 files changed, 406 insertions(+)
```

---

### Task 10: Protoss 4-unit 闭环 + 多 hit 循环
**Commit**: `6f4fe61`
**日期**: 2026-07-31

- **多 hit 循环** (Zealot `hit_count=2`):
  - `per_hit_dmg = base_dmg / hit_count`
  - 每次 hit 独立结算盾牌→护甲
  - 发射独立 `impact_resolved` 事件带 `hit_index` 0, 1, ...
  - 目标在 hit 间死亡则停止循环
  - 无盾牌路径使用 `calculate_damage()` 正确减去护甲
- 3 个 Protoss 战斗场景测试：
  - Zealot → Marine (2×8 normal = 16 dmg)
  - Dragoon → Dragoon (explosive, shield/health split)
  - Reaver → Zergling group (scarab splash + `scarab_count` 弹药)
- 更新 Tank 测试适配 hit_count=2

**文件变更**:
```
simcore/rules.py                                 | 136 ++++---
tests/simcore/test_sc1_representative_weapons.py | 203 +++++
2 files changed, 270 insertions(+), 69 deletions(-)
```

---

### Task 11: Test Mode 诊断层
**Commit**: `ec92860`
**日期**: 2026-07-31

- **`combat_diagnostics_overlay.gd`** (299 行): PanelContainer 诊断覆盖层
  - 显示: 攻击者/目标, 武器/护甲类型, 基础伤害, 倍率, 盾牌/生命伤害, 溅射/链式, tick/event ID
  - 仅 Test Mode 可见，正式对局不创建
- **`test_sc1_combat_slice.gd`** (579 行): Godot headless 测试
  - 10 个 matchup preset, 51 个断言
  - GDScript 移植 `resolve_weapon_impact` 逻辑
  - 支持 `--diagnostics` 命令行参数
- **`test_mode_gallery.gd`** (+257 行): 10 个 preset 按钮，接入诊断覆盖层
- **`game_view.gd`**: 修复预存在的 `dmg` 变量作用域错误 (line 1909)

**测试结果**: 51/51 Godot diagnostics PASS

**文件变更**:
```
godot/scripts/combat_diagnostics_overlay.gd | 299 +++
godot/scripts/test_sc1_combat_slice.gd      | 579 +++++
godot/scripts/test_mode_gallery.gd          | 257 ++++
godot/scripts/game_view.gd                  |   6 +-
4 files changed, 1,138 insertions(+), 3 deletions(-)
```

---

### Task 12: 资源与动画完整性门
**Commit**: `9ef3c00`
**日期**: 2026-07-31

- **7 个资源门测试** (`TestResourceGate`):
  - `presentation_manifest.unit_visuals` 覆盖全部 12 单位
  - `sprite_frames_config.units` 覆盖全部 12 单位
  - 非 Templar 单位有 `attack > 0` 帧
  - Templar 有 `cast > 0` 帧
  - 所有 PNG 资产文件存在于磁盘
  - 12 个 weapon ID 双射匹配
  - 每个 catalog weapon 映射到 manifest unit
- **验证脚本**: `verify_presentation_scene.py` 增加 12-unit combat resource gate
- **QA 报告**: 更新 Task 7-11 状态、资源门结果、已知缺口

**测试结果**: 52/52 Python tests PASS, verification OK

**文件变更**:
```
tests/godot/test_weapon_visual_catalog.py     | 146 ++++
scripts/verify_presentation_scene.py          |  89 ++++
docs/reports/sc1-combat-differentiation-qa.md | 133 +++-
3 files changed, 365 insertions(+), 3 deletions(-)
```

---

### Task 13: 端到端、回放与性能验收
**Commit**: `5b8b925`
**日期**: 2026-07-31

- **6 个 E2E 集成测试** (`tests/integration/test_combat_visual_events_e2e.py`):
  - **事件管线测试**: Marine vs Zergling 全链路验证（attack_started → impact_resolved, weapon_id, damage, event_id 唯一性, 事件顺序）
  - **确定性测试**: subprocess 隔离 `PYTHONHASHSEED=1` vs `999`，逐字节比较 JSON 输出
  - **链式弹跳确定性**: 6 Mutalisk vs 10 Marine，18 个 impact 事件的 chain target 选择一致
  - **三族完整性**: Terran/Zerg/Protoss 各一个 matchup，27 个事件字段非空验证
- **文档更新**:
  - `docs/godot_verification_guide.md`: SC1 战斗验证章节（CombatEvent 检查、12 preset、正式 matchup、回放一致性、性能上限）
  - `docs/reports/sc1-combat-differentiation-qa.md`: 最终测试计数

**测试结果**: 6/6 E2E PASS, 全量 1430 passed

**文件变更**:
```
tests/integration/test_combat_visual_events_e2e.py | 476 +++++
docs/godot_verification_guide.md                   |  68 +
docs/reports/sc1-combat-differentiation-qa.md      |   4 +-
3 files changed, 547 insertions(+), 1 deletion(-)
```

---

## Git 提交历史（按时间顺序）

| # | Hash | 日期 | 描述 | 变更 |
|---|------|------|------|------|
| 1 | `87ddbd8` | 2026-07-29 | feat: operation feel P0/P1 changes + combat differentiation plan | 15 files, +2993/-202 |
| 2 | `49c8f7d` | 2026-07-29 | docs: define authoritative combat visual events | 1 file, +58 |
| 3 | `8187039` | 2026-07-29 | docs: record SC1 combat differentiation baseline | 1 file |
| 4 | `1030ed5` | 2026-07-29 | feat: add combat event protobuf contract | 5 files, +245/-20 |
| 5 | `f1b05cf` | 2026-07-30 | Task 1A: SC1 DAT combat truth audit | 2 files, +2883 |
| 6 | `c6509f2` | 2026-07-30 | feat: define semantic weapons for representative units | 5 files, +4322/-3 |
| 7 | `25396cd` | 2026-07-30 | feat: emit authoritative combat events | 4 files, +730/-4 |
| 8 | `4506688` | 2026-07-30 | feat: transport combat events to frontend and replay | 4 files, +281/-4 |
| 9 | `f233f9c` | 2026-07-30 | feat: drive Godot combat visuals from authoritative events | 4 files, +395/-273 |
| 10 | `67c7dda` | 2026-07-31 | feat: wire weapon visual catalog into combat event pipeline (Task 7) | 9 files, +1060/-3 |
| 11 | `02bbf80` | 2026-07-31 | feat: unified combat resolution module (Task 7A) | 3 files, +809 |
| 12 | `13312d0` | 2026-07-31 | feat: route projectile damage through unified resolve_weapon_impact (Task 7A) | 3 files, +380/-26 |
| 13 | `41698d3` | 2026-07-31 | feat: fix SC1 shield mechanic + Terran combat scenarios (Task 8) | 3 files, +282/-26 |
| 14 | `75dd70d` | 2026-07-31 | feat: implement Mutalisk chain bounce + Zerg combat scenarios (Task 9) | 2 files, +406 |
| 15 | `6f4fe61` | 2026-07-31 | feat: implement multi-hit loop + Protoss combat scenarios (Task 10) | 2 files, +270/-69 |
| 16 | `ec92860` | 2026-07-31 | feat: add Test Mode combat diagnostics layer (Task 11) | 4 files, +1138/-3 |
| 17 | `9ef3c00` | 2026-07-31 | test: gate representative combat resources (Task 12) | 3 files, +365/-3 |
| 18 | `5b8b925` | 2026-07-31 | test: complete SC1 combat differentiation gate (Task 13) | 3 files, +547/-1 |

---

## 测试统计

| 类别 | 数量 | 状态 |
|------|------|------|
| Python 单元/集成测试 | 1,430 passed, 1 skipped | ✅ 0 failures |
| Godot diagnostics 测试 | 51/51 passed | ✅ |
| Godot combat event pipeline | PASS | ✅ |
| 资源验证 (12-unit gate) | OK | ✅ |
| 确定性 (PYTHONHASHSEED) | 逐字节一致 | ✅ |

---

## 新增/修改的核心文件

### SimCore (Python)
| 文件 | 行数 | 说明 |
|------|------|------|
| `simcore/combat_resolution.py` | 425 | 统一伤害结算模块 |
| `simcore/combat_events.py` | 114 | 战斗事件类型定义 |
| `simcore/rules.py` | ~1,700 | resolve_combat + _apply_chain + 多 hit 循环 |
| `simcore/projectile.py` | ~400 | 确定性弹道 + resolve_weapon_impact |
| `simcore/engine.py` | — | 集成 combat_events 到引擎 |
| `data/combat/weapons.json` | 264 | 12 个武器完整定义 |

### Godot (GDScript)
| 文件 | 行数 | 说明 |
|------|------|------|
| `combat_diagnostics_overlay.gd` | 299 | Test Mode 诊断覆盖层 |
| `test_sc1_combat_slice.gd` | 579 | 10 preset headless 测试 |
| `vfx_manager.gd` | +170 | spawn_weapon_event 方法 |
| `combat_visual_controller.gd` | 重写 | 事件驱动视觉 |
| `test_mode_gallery.gd` | +257 | 10 个 preset 按钮 |

### 测试
| 文件 | 行数 | 测试数 |
|------|------|--------|
| `test_sc1_representative_weapons.py` | ~1,100 | 31 (Terran+Zerg+Protoss) |
| `test_combat_resolution.py` | 375 | 统一结算 |
| `test_projectile_combat_integration.py` | 275 | 弹道集成 |
| `test_combat_event_emission.py` | 335 | 事件发射 |
| `test_combat_event_transport.py` | 159 | gRPC 传输 |
| `test_combat_event_proto.py` | 164 | Protobuf 契约 |
| `test_combat_visual_events_e2e.py` | 476 | E2E + 确定性 |
| `test_weapon_visual_catalog.py` | ~650 | 52 (含 7 资源门) |

### 数据/资源
| 文件 | 说明 |
|------|------|
| `weapon_visual_catalog.json` | 12 武器视觉映射 |
| `vfx_catalog.json` | VFX 效果定义 |
| `combat_reference.json` | 2,650 行 SC1 DAT 审计数据 |

---

## 已知缺口

1. **Templar 原始提取资源**: Templar 的 PNG 资产存在但缺乏丰富的原始帧提取（不影响游戏和诊断）
2. **30v30 VFX cap (Task 13 Step 3)**: 需要人工在 Godot 编辑器中测试 60 单位 30 秒场景
3. **人工正式对局评分 (Task 13 Step 5)**: 10 个 matchup 的人工评分需在 Godot 中操作

---

## 完成定义检查

| 条件 | 状态 |
|------|------|
| 12/12 单位有独立 weapon_id | ✅ |
| 12/12 单位数值可追溯到 source audit | ✅ |
| 12/12 单位 attack/cast 动画可播放 | ✅ |
| 12/12 单位正式对局通过权威事件触发 | ✅ |
| Test Mode 使用同一事件入口和 visual catalog | ✅ |
| normal/explosive/concussive 倍率与实际伤害一致 | ✅ |
| shield-first → health-armor → size multiplier 顺序正确 | ✅ |
| Shield/health damage 可拆分验证 | ✅ |
| Mutalisk 三段弹射有自动测试 | ✅ |
| Zealot 双 hit 有自动测试 | ✅ |
| Storm 周期伤害有自动测试 | ✅ |
| Reaver Scarab 有自动测试 | ✅ |
| replay 同 seed 确定 | ✅ |
| 所有自动测试通过 | ✅ (1430 + 51) |
| 人工 matchup 评分全部 ≥ 4/5 | ⏳ 待人工 |
