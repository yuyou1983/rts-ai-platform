# Godot 操作手感、战斗画面、兵种类型 — QA 报告

> Phase 0 baseline, 2026-06-23

## 1. 评分项 (1-5 分)

| 评分项 | 分数 | 说明 |
|--------|------|------|
| 相机移动/缩放/跟随 | 3 | WASD、边缘滚动、中键拖拽已实现；参数散在 export 中，无统一配置，zoom 参数范围偏大(max=20) |
| 框选/点选/编队 | 3 | 点选、框选、双击、Ctrl/Shift 选择、控制组 1-9 已实现；无建组/跳转视觉反馈 |
| 右键命令反馈 | 2 | 攻击有 VFX；移动无目的地标记；A-Move 无光标/路径区分；无效命令无反馈 |
| 战斗可读性 | 2 | 有攻击闪白、受击火花、死亡圈；但弹道/曳光/投射物全部缺失，近战/远程/法术不可肉眼区分 |
| VFX 上限 | 1 | 无活跃特效数上限，`_effects` 数组只靠 lifetime 过期 |
| 兵种比例 | 3 | visual_class 缩放已配置；Drone anim_info 之前复用 SCV 已修；Zerg/Protoss 比例需人工确认 |
| Test Mode 完整性 | 2 | 仅有 race/type/batch 三维筛选；缺 domain/role/tier/vfx_profile/visual_class/action 筛选 |
| vfx_profile 一致性 | 1 | presentation_manifest.json 声明了 vfx_profile 但 VFXManager 不读取，两套映射体系断裂 |
| 音效系统 | 1 | vfx_catalog.json 定义了 sfx 字段但 VFXManager 完全没有音频播放代码 |

**总分: 18/45**

## 2. 当前可调参数 Baseline

### camera_controller.gd

| 参数 | 当前值 | 类型 |
|------|--------|------|
| keyboard_speed | 500.0 | @export |
| edge_scroll_margin | 20.0 | @export |
| edge_scroll_speed | 400.0 | @export |
| min_zoom | 2.0 | @export |
| max_zoom | 20.0 | @export |
| zoom_step | 0.5 | @export |
| zoom_lerp_speed | 10.0 | @export |
| map_width | 64.0 | @export |
| map_height | 64.0 | @export |
| cell_size | 1.0 | @export |

### selection_manager.gd

| 参数 | 当前值 | 类型 |
|------|--------|------|
| MAX_SELECTION_SIZE | 12 | const |
| DOUBLE_CLICK_INTERVAL | 0.4 | const |
| building_priority | true | var |
| formation spacing | 0.8 | 默认参数 |
| hotkey range | 1-9 | 硬编码 |
| owner 判定 | 1 | 硬编码 |

## 3. VFX 体系现状

### vfx_catalog.json 已定义效果 (8种)

- `muzzle_flash_small` — 小型枪口闪
- `hit_spark` — 命中火花
- `acid_hit` — 酸液命中
- `shell_impact` — 弹壳冲击
- `shield_hit` — 护盾命中
- `building_burst` — 建筑爆炸
- `flame_burst` — 火焰爆发
- `psi_flash` — 灵能闪光

### VFXManager 映射方式

1. `_lookup_unit_effect(unit_name, action)` → 查 `unit_effects[unit_name][action]`
2. `_normalize_unit_key()` 归一化（如 `*zerg*` → `Zergling`）
3. Fallback: Protoss→shield_hit, Zerg→acid_hit, 其他→hit_spark; 高伤害→shell_impact

**问题**: `presentation_manifest.json` 中的 `vfx_profile` 字段（terran_small_arms/terran_flame/terran_ordnance 等）完全未接入 VFXManager

### 缺失 VFX

- 所有弹道/曳光/投射物效果
- 近战挥击/冲击弧
- 护盾涟漪(shield ripple)
- 建筑受击烟雾
- 死亡 burst 分层（小/大/建筑）

## 4. 命令反馈缺失清单

| 反馈 | 状态 | 优先级 |
|------|------|--------|
| 右键移动目的地脉冲 | ❌ 缺失 | 🔴 高 |
| A-Move 目标标记 | ❌ 缺失 | 🔴 高 |
| 无效命令拒绝反馈 | ❌ 缺失 | 🔴 高 |
| 建造放置 ghost/红绿指示 | ❌ 缺失 | 🔴 高 |
| 控制组建组 HUD 提示 | ❌ 缺失 | 🟡 中 |
| 控制组双击跳转居中 | ❌ 缺失 | 🟡 中 |
| 采集命令视觉确认 | ❌ 缺失 | 🟡 中 |
| 技能/巡逻光标变化 | ❌ 缺失 | 🟡 中 |
| 技能失败红色闪烁 | ❌ 缺失 | 🔴 高 |
| 音效系统 | ❌ 缺失 | 🔴 高 |

## 5. Test Mode 筛选现状

| 维度 | 状态 |
|------|------|
| Race (All/Terran/Zerg/Protoss/Neutral) | ✅ |
| Type (All/Building/Unit/Resource) | ✅ |
| Batch (All/动态 batch ID) | ✅ |
| Domain (ground/air) | ❌ |
| Role (worker/infantry/vehicle/air/caster/siege/support) | ❌ |
| Tier (basic/advanced/tech) | ❌ |
| VFX Profile | ❌ |
| Visual Class | ❌ |
| Action State (idle/move/attack) | ❌ |

## 6. 测试 Baseline

| 测试 | 结果 |
|------|------|
| `verify_presentation_scene.py` | ✅ PASSED |
| `pytest tests/godot/` | ✅ 39 passed |
| `.godot/ import cache` | ✅ 已从 git 移除并加入 .gitignore |
| `test_generated_manifest_matches` | ✅ 已修复（含 P1C+P2 全量检查） |

## 7. 主要问题 Top 5

1. **vfx_profile 断裂**: manifest 声明了 profile 但 VFXManager 不读取，需统一
2. **无 VFX 上限**: 密集战斗会无限增长特效对象
3. **命令反馈缺失**: 移动/A-Move/无效命令/建造放置无视觉确认
4. **音效管线为零**: catalog 有 sfx 定义但无播放代码
5. **Test Mode 筛选不足**: 缺 domain/role/tier/vfx_profile/visual_class/action

## 8. 下一步 (Phase 1)

按计划执行 Phase 1 — 操作手感：
1. 新增 `godot/resources/feel/control_feel_config.json`
2. camera_controller.gd 从配置读取参数
3. selection_manager.gd 从配置读取参数
4. game_view.gd 增加右键/攻击/无效命令反馈
5. 增加控制组反馈
6. 新增 `tests/godot/test_control_feel_config.py`
7. 新增 `godot/scripts/test_control_feel_config.gd`
