# Godot 操作手感、战斗画面、兵种类型迭代计划

> 面向后续 agent 执行。目标是把 Godot 前端从“资源能显示”推进到“RTS 操作、战斗可读性、兵种表达可验证”。

**Goal:** 提升 Godot 前端的操作手感、战斗画面表现和兵种类型表达，同时保持现有四层架构边界：视觉和交互问题优先在 Godot 表现层解决，只有确认 SimCore 状态缺字段或协议缺表达时才进入 L1/L0。

**Architecture:** 沿用 Proto(L0) -> SimCore(L1) -> Agents(L2) -> Godot(L3)。本计划以 Godot L3 为主，采取 data-first 方式：先补表现配置、目录和校验，再改 GDScript 消费这些配置。避免先大规模重写 `game_view.gd`。

**Tech Stack:** Godot 4.x GDScript、`presentation_manifest.json`、`sprite_frames_config.json`、`vfx_catalog.json`、SC1 generated manifest、pytest、Godot headless scripts、人工视觉 QA。

## 1. 范围

### In Scope

- 操作手感：相机移动/缩放/跟随、框选/点选/编队、右键命令反馈、攻击移动反馈、控制组反馈、基础 APM/输入延迟观测。
- 战斗画面：武器发射、弹道/曳光、命中、护盾、酸液、火焰、爆炸、死亡、建筑受击、特效层级和密集战斗性能上限。
- 兵种类型：人族/虫族/神族兵种目录、地面/空中/建筑区分、角色类型、科技层级、生产建筑、VFX profile、Test Mode 筛选和预览。
- 校验体系：自动化 manifest/schema 测试、Godot headless smoke、人工视觉评分表。

### Non Goals

- 不在本计划里改 RTS 平衡数值，除非是为了暴露前端显示字段。
- 不把原始 SC1 专有资源提交到仓库；只提交 manifest、转换脚本、校验报告或可合法提交的派生产物。
- 不先重构整个 `game_view.gd`；只有在配置和测试落地后，再做小步拆分。
- 不调整运行时 AI/AgentScope 决策链路。

## 2. 当前判断

当前 Godot 层已经具备基础设施：

- `godot/scripts/camera_controller.gd` 已有键盘、边缘滚动、中键拖拽、缩放、跟随和边界限制。
- `godot/scripts/selection_manager.gd` 已有点选、框选、双击、Ctrl/Shift 选择、控制组和最大选择数。
- `godot/scripts/game_view.gd` 已串联 HUD、SelectionManager、CameraController、SpriteLoader、VFXManager、雾、Test Mode 和输入事件。
- `godot/scripts/vfx_manager.gd` 已能从 `godot/resources/vfx/vfx_catalog.json` 读取攻击、命中、死亡等效果。
- `godot/resources/presentation_manifest.json` 已经承担抽象单位/建筑到视觉资源的映射。
- `docs/godot_verification_guide.md` 已有完整人工验证入口。

主要短板：

- 操作参数散落在脚本常量和 exported vars 中，缺少统一“手感配置”和回归校验。
- 战斗 VFX 偏 unit-to-effect 映射，缺少按 weapon/profile/domain 分层的可读性规范。
- 兵种目录仍混杂在 HUD、presentation manifest、units data、generated manifest 之间，缺少单一可验证的“兵种类型目录”。
- Test Mode 能展示资源，但还没有成为“兵种类型、动作、攻击效果、比例”的完整验收工具。

## 3. 目标验收标准

完成后需要满足：

- 操作：移动、缩放、框选、右键、攻击移动、编队在 10 分钟人工测试中无明显误触、无视觉反馈缺失。
- 战斗：每个可攻击单位至少有发射/命中/死亡反馈；地面、空中、近战、远程、法术、建筑受击能被肉眼区分。
- 兵种：`data/units/units.json` 中的单位都能映射到 Godot 的类型目录和 presentation manifest；Test Mode 可按 race/kind/domain/role/tier 筛选。
- 性能：密集战斗 VFX 不无限增长，存在最大活跃特效数或对象池策略。
- 校验：Godot 表现相关 pytest、presentation scene verification、Godot headless smoke 均可运行。

## 4. 文件计划

### 新增文件

- `godot/resources/feel/control_feel_config.json`
  - 统一相机、选择、命令反馈、控制组反馈参数。
- `godot/resources/unit_type_catalog.json`
  - 统一兵种类型、角色、生产建筑、domain、tier、VFX profile、selection class。
- `tests/godot/test_control_feel_config.py`
  - 校验手感配置 schema、数值范围和必填字段。
- `tests/godot/test_unit_type_catalog.py`
  - 校验兵种目录与 `data/units/units.json`、`presentation_manifest.json`、HUD train catalog 的一致性。
- `godot/scripts/test_control_feel_config.gd`
  - Godot headless 验证配置能被加载并应用。
- `godot/scripts/test_vfx_catalog_profiles.gd`
  - Godot headless 验证 VFX profile 和 effect id 可解析。
- `docs/reports/godot-controls-combat-units-qa.md`
  - 人工 QA 记录模板和每轮验收结果。

### 修改文件

- `godot/scripts/camera_controller.gd`
  - 从 `control_feel_config.json` 读取相机速度、缩放、平滑、边缘滚动、跟随参数。
- `godot/scripts/selection_manager.gd`
  - 从配置读取框选阈值、双击时间、点击容差、选择上限、控制组反馈行为。
- `godot/scripts/game_view.gd`
  - 接入命令反馈层、攻击移动反馈、Test Mode 新筛选项；避免把新逻辑继续堆成大块。
- `godot/scripts/hud.gd`
  - 训练按钮从 `unit_type_catalog.json` 或其派生数据校验；减少硬编码漂移。
- `godot/scripts/vfx_manager.gd`
  - 从 unit-specific 映射推进到 weapon/profile 映射，增加活跃 VFX 上限。
- `godot/resources/vfx/vfx_catalog.json`
  - 补齐 projectile/tracer/impact/death/shield/flame/acid/psi/building profiles。
- `godot/resources/presentation_manifest.json`
  - 补齐兵种 display metadata、selection radius、health bar offset、VFX profile 对齐。
- `scripts/verify_presentation_scene.py`
  - 增加兵种目录、VFX profile、Test Mode 资源完整性校验。
- `docs/godot_verification_guide.md`
  - 增加本轮操作手感、战斗画面、兵种类型专项检查表。

## 5. Phase 0 - 基线和护栏

**目标:** 先确认当前 Godot 表现层问题的可复现基线，避免凭感觉反复调。

任务：

- [ ] 创建 `docs/reports/godot-controls-combat-units-qa.md`，包含 1-5 分评分项：相机、框选、右键反馈、编队、攻击移动、战斗可读性、兵种比例、Test Mode 完整性。
- [ ] 运行现有 Godot 表现校验，记录当前结果。
- [ ] 梳理 `game_view.gd`、`camera_controller.gd`、`selection_manager.gd`、`vfx_manager.gd` 当前可调参数，写入 QA 报告的 baseline 区域。
- [ ] 确认 `.godot/` import cache 不进入提交范围。

建议命令：

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/ -q -x
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_p1a_sprite_loader.gd
```

交付物：

- `docs/reports/godot-controls-combat-units-qa.md`
- 当前测试输出摘要
- 当前视觉/手感主要问题清单

## 6. Phase 1 - 操作手感

**目标:** 把 RTS 常用操作从“能操作”调到“可连续操作、反馈清楚、参数可回归”。

任务：

- [ ] 新增 `godot/resources/feel/control_feel_config.json`。
- [ ] 在 `camera_controller.gd` 中接入配置：
  - keyboard pan speed
  - edge scroll margin/speed
  - middle drag sensitivity
  - zoom min/max/step
  - zoom smoothing
  - follow selected/group smoothing
  - map edge clamp padding
- [ ] 在 `selection_manager.gd` 中接入配置：
  - drag start threshold
  - click slop
  - double click interval
  - max selection size
  - Ctrl/Shift behavior
  - building priority toggle
- [ ] 在 `game_view.gd` 增加命令反馈：
  - 右键地面：短暂绿色目标脉冲
  - 右键敌人：红色攻击脉冲
  - attack-move：路径/目标点特殊标识
  - invalid command：低亮度拒绝反馈
- [ ] 增加控制组反馈：
  - Ctrl+数字建组时 HUD 短提示
  - 双击数字跳转时相机平滑居中
  - 空控制组输入时轻量提示
- [ ] 新增 `tests/godot/test_control_feel_config.py`，检查配置范围。
- [ ] 新增 `godot/scripts/test_control_feel_config.gd`，检查 Godot 能读取配置。

建议默认参数起点：

```json
{
  "camera": {
    "keyboard_speed": 620.0,
    "edge_scroll_margin": 24.0,
    "edge_scroll_speed": 520.0,
    "middle_drag_sensitivity": 1.0,
    "min_zoom": 1.6,
    "max_zoom": 7.5,
    "zoom_step": 0.35,
    "zoom_lerp_speed": 12.0
  },
  "selection": {
    "drag_threshold_px": 5.0,
    "click_slop_px": 6.0,
    "double_click_interval": 0.35,
    "max_selection_size": 12
  },
  "command_feedback": {
    "ground_ping_duration": 0.32,
    "attack_ping_duration": 0.38,
    "invalid_ping_duration": 0.22
  }
}
```

验收：

- 5 分钟连续操作中，框选和点选不互相误触。
- zoom 不出现过大视野导致单位不可读，也不出现过近导致地图不可控。
- 右键、攻击移动、控制组都有可见反馈。
- `test_control_feel_config.py` 和 Godot headless config test 通过。

## 7. Phase 2 - 战斗画面和 VFX 可读性

**目标:** 让战斗画面表达“谁在打、打到了哪里、伤害类型是什么、单位是否死亡”，同时避免密集战斗变成视觉噪声。

任务：

- [ ] 重整 `godot/resources/vfx/vfx_catalog.json`，建立 profile 层：
  - `terran_ballistic`
  - `terran_explosive`
  - `terran_flame`
  - `zerg_melee`
  - `zerg_acid`
  - `zerg_spore`
  - `protoss_psi`
  - `protoss_phase`
  - `building_hit`
  - `shield_hit`
- [ ] 在 `vfx_manager.gd` 中优先按 `vfx_profile` 获取效果；缺失时才 fallback 到 unit key。
- [ ] 增加 projectile/tracer 表现：
  - hitscan：短线曳光 + muzzle flash
  - ballistic：有飞行时间的亮点/弹道
  - melee：短距离挥击/冲击弧
  - acid/spore：慢速投射物 + splash
  - psi：高亮短闪 + shield ripple
- [ ] 增加 hit/death 分层：
  - 小型单位死亡：短 burst + fade
  - 大型单位死亡：更长爆炸/碎片
  - 建筑死亡：building burst + smoke
  - Protoss shield：优先显示 shield hit，再显示 hull hit
- [ ] 添加活跃 VFX 上限：
  - 普通特效上限
  - projectile 上限
  - death effect 上限
  - 超限时丢弃低优先级特效
- [ ] 新增 `godot/scripts/test_vfx_catalog_profiles.gd`。
- [ ] 扩展 `tests/godot/test_presentation_manifest.py` 或新增 pytest，确保所有可攻击单位都有 `vfx_profile`。

验收：

- Marine、Tank、Firebat、Hydralisk、Zergling、Mutalisk、Zealot、Dragoon、Reaver、Carrier 至少覆盖一轮视觉检查。
- 近战/远程/爆炸/火焰/酸液/灵能可肉眼区分。
- 密集 30v30 战斗中，VFX 不遮挡血条和选择圈。
- VFX 上限生效，没有无限增长对象。

## 8. Phase 3 - 兵种类型目录

**目标:** 把“兵种是什么、属于什么角色、如何生产、如何展示”集中到一个可验证目录，减少 HUD、manifest、测试场景之间的漂移。

任务：

- [ ] 新增 `godot/resources/unit_type_catalog.json`。
- [ ] 每个单位至少包含：
  - `unit_id`
  - `race`
  - `domain`: `ground` / `air`
  - `kind`: `unit`
  - `role`: `worker` / `infantry` / `vehicle` / `air` / `caster` / `siege` / `support`
  - `tier`: `basic` / `advanced` / `tech`
  - `production_building`
  - `presentation_key`
  - `vfx_profile`
  - `selection_class`
  - `test_mode_group`
- [ ] 覆盖 `data/units/units.json` 中的人族、虫族、神族单位。
- [ ] 将 `hud.gd` 的 train catalog 与 `unit_type_catalog.json` 对齐：
  - 第一阶段可以保持 HUD 硬编码，但必须新增测试防止漂移。
  - 第二阶段再改为从目录派生训练按钮。
- [ ] 扩展 Test Mode：
  - race filter: Terran/Zerg/Protoss
  - kind filter: unit/building
  - domain filter: ground/air
  - role filter: worker/infantry/vehicle/air/caster/siege/support
  - tier filter: basic/advanced/tech
  - preview mode: idle/move/attack
- [ ] 让 Test Mode 的单位预览使用主界面同一套 SpriteLoader、VFXManager 和 scaling 逻辑。
- [ ] 新增 `tests/godot/test_unit_type_catalog.py`：
  - `data/units/units.json` 中单位必须存在目录项。
  - 目录项 `presentation_key` 必须能在 `presentation_manifest.json` 解析。
  - 目录项 `vfx_profile` 必须能在 `vfx_catalog.json` 解析。
  - HUD train catalog 中的单位必须存在目录项。

验收：

- Test Mode 可以按 race/domain/role/tier 精确筛选。
- SCV、Probe、Drone 的 worker 比例和选择圈一致性通过人工检查。
- 三族 basic combat units 同屏展示时，视觉比例可读，不再出现某一种族整体偏小。
- 所有单位目录测试通过。

## 9. Phase 4 - 集成 QA

**目标:** 用一组固定场景验证操作、战斗、兵种表达是否真的改善。

人工 QA 场景：

- Terran start：
  - 框选 SCV
  - 右键采集
  - 建造 SupplyDepot/Barracks
  - 训练 Marine
  - Marine attack-move
- Zerg start：
  - Drone 采集
  - Larva/Overlord/Zergling 视觉检查
  - Zergling 近战攻击反馈
  - Hydralisk 酸液攻击反馈
- Protoss start：
  - Probe 采集
  - Pylon/Nexus/Zealot/Dragoon 比例检查
  - shield hit 反馈检查
- Mixed combat：
  - 12v12 小规模战斗
  - 30v30 密集战斗
  - 地面 vs 空中
  - 建筑受击和死亡
- Test Mode：
  - 三族单位全量展示
  - 三族建筑全量展示
  - move preview
  - attack preview
  - race/domain/role/tier filters

建议启动命令：

```bash
python3 -m simcore.grpc_server
python3 -m simcore.http_gateway
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```

记录项：

- 每个场景截图
- 操作主观评分
- 战斗可读性评分
- 兵种比例评分
- 缺失资源/错误资源列表
- 是否需要 SimCore 协议补字段

## 10. Phase 5 - 小步重构

**目标:** 在测试和 QA 通过之后，再降低 Godot 前端脚本复杂度。

触发条件：

- `game_view.gd` 新增逻辑超过 200 行。
- VFX、Test Mode、命令反馈任一模块开始影响主流程可读性。
- 同一类数据读取逻辑复制超过 2 次。

允许拆分：

- `godot/scripts/command_feedback_layer.gd`
  - 右键、attack-move、invalid command、control group feedback。
- `godot/scripts/combat_visual_controller.gd`
  - combat event inference、VFX dispatch、priority/capping。
- `godot/scripts/test_mode_gallery.gd`
  - Test Mode 筛选、布局、preview 状态。
- `godot/scripts/resource_catalog_loader.gd`
  - feel config、unit catalog、vfx catalog 的 typed loader。

重构要求：

- 每拆一个脚本，必须保留或新增 headless smoke。
- 不改变 SimCore 输入输出。
- 不改变 manifest schema，除非同步更新测试。

## 11. 执行顺序

建议其他 agent 按这个顺序执行：

1. Phase 0：建立 QA baseline 和当前问题列表。
2. Phase 1：实现操作手感配置和基础反馈。
3. 人工 Gate A：只验操作，不验所有 VFX。
4. Phase 2：实现战斗 VFX profile 和上限。
5. 人工 Gate B：验 10 个代表单位战斗效果。
6. Phase 3：实现兵种类型目录和 Test Mode 筛选。
7. 人工 Gate C：验三族单位/建筑完整展示。
8. Phase 4：完整集成 QA。
9. Phase 5：根据复杂度决定是否拆分脚本。

每个 Phase 建议单独提交，提交信息格式：

```text
godot: add controls feel baseline
godot: improve combat vfx profiles
godot: add unit type catalog
godot: expand visual qa coverage
```

## 12. 自动化校验命令

基础：

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/ -q -x
```

专项：

```bash
python3 -m pytest tests/godot/test_presentation_manifest.py -q
python3 -m pytest tests/godot/test_visual_class_scale.py -q
python3 -m pytest tests/godot/test_sc1_generated_manifest.py -q
python3 -m pytest tests/godot/test_control_feel_config.py -q
python3 -m pytest tests/godot/test_unit_type_catalog.py -q
```

Godot headless：

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_p1a_sprite_loader.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_game_view_probe_override.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_control_feel_config.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
```

架构护栏：

```bash
make lint-arch
```

## 13. 风险和处理

- 风险：把视觉问题错误下沉到 SimCore。
  - 处理：除非缺字段，否则优先改 Godot manifest/config/script。
- 风险：VFX 越加越花，影响 RTS 可读性。
  - 处理：按 profile 分层，增加优先级和活跃数量上限。
- 风险：三族比例继续漂移。
  - 处理：把 `selection_radius`、`render_scale`、`health_bar_offset` 纳入 manifest 测试和 Test Mode 截图 QA。
- 风险：HUD 训练目录和资源目录不同步。
  - 处理：先加 `test_unit_type_catalog.py` 锁住一致性，再考虑 HUD 从目录派生。
- 风险：Godot import cache 污染提交。
  - 处理：提交前检查 `git status --short`，不要提交 `.godot/imported/*` 和编辑器 cache。

## 14. 需要用户确认的点

这些点不阻塞 Phase 0-1，但会影响 Phase 2-3 的审美和范围：

- 战斗画面参考更偏 SC1 原版，还是允许更现代的高亮特效。
- Test Mode 是否需要导出截图报告，方便非 Godot 环境审阅。
- 兵种类型目录是否严格按 SC1 原版单位，还是允许当前项目已有抽象单位继续并行存在。
- VFX 是否要优先服务研究可读性，而不是完全复刻原版。

