# Godot SC1 手感与精细度改进计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 Godot 前端从“资源、特效、目录基本完整”推进到“接近 SC1 的 RTS 操作手感、战斗可读性和视觉精细度”。

**Architecture:** 保持 Proto(L0) -> SimCore(L1) -> Agents(L2) -> Godot(L3) 的边界。此计划优先在 Godot 表现层解决输入、镜头、选择、VFX、地形、资源比例问题；只有确认状态字段缺失时，才向 SimCore 或 Proto 提需求。

**Tech Stack:** Godot 4.x GDScript, `godot/resources/feel/control_feel_config.json`, `godot/resources/unit_type_catalog.json`, `godot/resources/presentation_manifest.json`, `godot/resources/vfx/vfx_catalog.json`, pytest, Godot headless scripts, manual visual QA.

---

## 0. 当前状态判断

已完成的基础工作：

- `godot/resources/feel/control_feel_config.json` 已存在，并覆盖 camera、selection、command_feedback、vfx_limits、selection_ring、animation、terrain、resource_visuals。
- `godot/resources/unit_type_catalog.json` 已存在，当前声明 93 个条目，其中单位 43 个，建筑 50 个。
- `godot/scripts/entity_visual.gd` 已加入状态过渡、死亡 fade、建筑施工表现。
- `godot/scripts/hud_overlay_renderer.gd` 已加入 race-colored selection ring、建筑施工 wireframe、fog 数据接入。
- `godot/scripts/terrain_renderer.gd` 已新增，以 height_map 生成 procedural terrain。
- Godot 相关测试当前通过：
  - `python3 scripts/verify_presentation_scene.py`
  - `python3 -m pytest tests/godot/ -q -x`
  - `python3 -m pytest tests/godot/test_control_feel_config.py tests/godot/test_unit_type_catalog.py tests/godot/test_vfx_profiles.py -q`

主要问题：

- 测试已经能证明“文件结构和引用关系成立”，但还不能证明“操作像 SC1”。
- 当前 `camera_controller.gd` 会在 setup 时把速度乘以 zoom，这会导致不同窗口、地图大小、zoom 下的速度感不稳定。
- 选择圈和反馈已经更丰富，但偏装饰化；SC1 的重点是低噪声、强识别、快速确认，而不是高亮复杂度。
- 战斗 VFX 已 profile 化，但攻击反馈仍需要从“命令触发特效”升级到“武器节奏、弹道、命中、死亡由状态/事件驱动”。
- `terrain_renderer.gd` 的 procedural height_map 表现与 SC1 tileset 风格仍有距离；如果目标是 SC1 观感，后续应推进 tile renderer。
- 兵种目录完整性已改善，但单位比例、pivot、shadow、footprint、health bar offset 仍需要按 visual class 做人工和自动化双重校准。

## 1. 改进方向

### 方向 A：从“能操作”变成“有 SC1 手感标尺”

核心目标：

- 输入反馈 1 帧内出现。
- 选择、右键、攻击移动、编队切换不依赖服务端回包才给玩家反馈。
- 相机速度用屏幕比例表达，而不是直接用 world units 或一次性乘 zoom。
- zoom 作为调试/研究视角保留，但默认游戏视角应固定在少数可控档位。

### 方向 B：从“特效丰富”变成“战斗信息清楚”

核心目标：

- 玩家能看出谁开火、打向哪里、是否命中、目标是否死亡。
- 近战、枪械、爆炸、火焰、酸液、灵能、护盾各有清晰但克制的视觉语言。
- 密集战斗时不遮挡单位、血条和选择圈。
- 特效由 weapon/profile + combat event 驱动，而不是简单按单位名触发。

### 方向 C：从“资源能显示”变成“资源和 footprint 对齐”

核心目标：

- 建筑边界、选择圈、血条、footprint、sprite pivot 同步。
- SCV/Probe/Drone 作为比例基准，校准三族基本兵种和建筑。
- Test Mode 成为资源验收工具：按 race/kind/domain/role/tier 展示，支持 idle/move/attack preview。
- generated asset、presentation manifest、unit type catalog 三者不漂移。

### 方向 D：从 procedural terrain 转向 SC1 tileset 表达

核心目标：

- 如果目标是接近 SC1，地表应优先使用 tileset/megatile 资源，而不是 height_map contour。
- fog 表现应接近 SC1 的 unexplored black + explored shroud + visible 三态，不宜过度现代平滑。
- grid、cliff marker、debug elevation 默认关闭，只在调试模式开启。

### 方向 E：从大脚本继续增长转向表现层模块化

核心目标：

- `game_view.gd` 继续承担编排，但输入反馈、战斗视觉、资源目录、Test Mode、terrain/fog 各自有独立模块。
- 每个模块有 headless smoke 或 pytest 校验。
- 不为了视觉微调修改 SimCore。

## 2. 文件责任边界

### 需要新增

- `godot/resources/feel/sc1_feel_baseline.json`
  - 记录 SC1-like 目标指标：camera screen speed、edge ramp、selection latency、right-click feedback duration、default zoom preset。
- `tests/godot/test_sc1_feel_baseline.py`
  - 校验 baseline 数值域、必填字段和与 `control_feel_config.json` 的兼容性。
- `godot/scripts/input_feedback_controller.gd`
  - 只负责本地输入反馈：地面 ping、攻击 ping、invalid ping、attack-move marker、control group flash。
- `godot/scripts/combat_visual_controller.gd`
  - 只负责从 state delta 推导 combat event，并调用 `vfx_manager.gd`。
- `godot/scripts/visual_calibration_overlay.gd`
  - Test Mode/Debug 用：显示 pivot、footprint、selection radius、health bar anchor。
- `docs/reports/godot-sc1-feel-gap-report.md`
  - 每轮人工测试记录：SC1 参考、当前 Godot 表现、偏差、修正项。

### 需要修改

- `godot/scripts/camera_controller.gd`
  - 改为 screen-space camera speed，移除 setup 时一次性乘 zoom 的速度变形。
- `godot/scripts/selection_manager.gd`
  - 增加更明确的 click/drag/box select 判定和本地选择反馈约束。
- `godot/scripts/hud_overlay_renderer.gd`
  - 降低选择圈装饰强度，增加 SC1-like simple mode。
- `godot/scripts/entity_visual.gd`
  - 将状态过渡参数与实际 attack cooldown / movement velocity 对齐。
- `godot/scripts/vfx_manager.gd`
  - 接受 `combat_visual_controller.gd` 的 normalized combat event。
- `godot/scripts/test_mode_gallery.gd`
  - 增加 calibration overlay 和 attack preview。
- `godot/resources/feel/control_feel_config.json`
  - 分离 debug visual、gameplay visual、SC1-like visual preset。
- `godot/resources/presentation_manifest.json`
  - 校准 pivot、render_scale、selection_radius、health_bar_offset、footprint。
- `godot/resources/vfx/vfx_catalog.json`
  - 增加 weapon timing、projectile speed、muzzle offset、impact offset。
- `docs/godot_verification_guide.md`
  - 增加 SC1 手感专项验收表。

## 3. Phase 0 - 建立 SC1 手感基准

**目标:** 先把“差距很大”变成可记录、可复测的偏差。

- [ ] 新增 `docs/reports/godot-sc1-feel-gap-report.md`。
- [ ] 在报告中建立 10 个固定评分项：
  - camera pan stability
  - camera edge scroll
  - zoom readability
  - click selection accuracy
  - box selection accuracy
  - right-click acknowledgement
  - control group recall
  - unit movement readability
  - basic combat readability
  - building footprint clarity
- [ ] 每项使用 1-5 分，记录“SC1 参考行为 / 当前 Godot 行为 / 偏差 / 下一步动作”。
- [ ] 新增 `godot/resources/feel/sc1_feel_baseline.json`，初始内容如下：

```json
{
  "schema_version": 1,
  "camera": {
    "default_zoom_preset": "gameplay",
    "keyboard_screen_per_second": 0.85,
    "edge_screen_per_second": 0.75,
    "edge_ramp_px": 28.0,
    "middle_drag_screen_ratio": 1.0,
    "zoom_presets": {
      "gameplay": 1.0,
      "inspection": 1.35,
      "debug_overview": 0.65
    }
  },
  "input_feedback": {
    "max_visual_latency_frames": 1,
    "right_click_ping_seconds": 0.22,
    "attack_ping_seconds": 0.28,
    "invalid_ping_seconds": 0.16
  },
  "selection": {
    "click_slop_px": 4.0,
    "drag_threshold_px": 5.0,
    "double_click_seconds": 0.30,
    "max_group_size": 12
  },
  "visual_noise": {
    "selection_ring_mode": "simple",
    "debug_grid_default": false,
    "debug_elevation_default": false
  }
}
```

- [ ] 新增 `tests/godot/test_sc1_feel_baseline.py`，至少校验：
  - `schema_version == 1`
  - `camera.keyboard_screen_per_second` 在 `[0.2, 2.0]`
  - `input_feedback.max_visual_latency_frames <= 1`
  - `selection.max_group_size == 12`
  - `visual_noise.selection_ring_mode` 是 `simple` 或 `enhanced`
- [ ] 运行：

```bash
python3 -m pytest tests/godot/test_sc1_feel_baseline.py -q
```

验收：

- 有一份可持续更新的 gap report。
- 有一份 SC1-like baseline config。
- 后续所有手感改动都能说明影响了哪一个评分项。

## 4. Phase 1 - 相机和输入闭环

**目标:** 先解决最影响 RTS 手感的部分：相机、点选、框选、右键反馈、编队召回。

- [ ] 修改 `godot/scripts/camera_controller.gd`，不要在 `setup()` 中执行 `keyboard_speed *= zoom` 和 `edge_scroll_speed *= zoom`。
- [ ] 把相机速度改成 screen-space 表达：

```gdscript
func _screen_speed_to_world(screen_per_second: float) -> float:
	var vp_size: Vector2 = get_viewport().get_visible_rect().size
	var visible_world_w: float = vp_size.x / maxf(_camera.zoom.x, 0.001)
	return visible_world_w * screen_per_second
```

- [ ] keyboard movement 使用 `keyboard_screen_per_second` 转 world speed。
- [ ] edge scroll 使用 `edge_screen_per_second`，并加入边缘 ramp：

```gdscript
var left_strength: float = clampf((edge_scroll_margin - mpos.x) / edge_scroll_margin, 0.0, 1.0)
_camera.position.x -= world_speed * left_strength * delta
```

- [ ] 默认 gameplay zoom 固定，不随地图大小自动变成极端 zoom；debug overview 走单独快捷键或 Test Mode。
- [ ] 新增 `godot/scripts/input_feedback_controller.gd`：
  - `show_ground_ping(world_pos: Vector2) -> void`
  - `show_attack_ping(world_pos: Vector2) -> void`
  - `show_invalid_ping(world_pos: Vector2) -> void`
  - `show_control_group_flash(group_id: int, assigned: bool) -> void`
- [ ] `game_view.gd` 的右键、attack-move、control group 反馈调用 `input_feedback_controller.gd`，不要继续把绘制状态散落在主脚本。
- [ ] 新增 headless smoke：`godot/scripts/test_input_feedback_controller.gd`，验证 controller 可以实例化、加载配置、生成和清理 ping。
- [ ] 运行：

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_input_feedback_controller.gd
python3 -m pytest tests/godot/test_control_feel_config.py tests/godot/test_sc1_feel_baseline.py -q
```

验收：

- 操作反馈不等待 SimCore 回包。
- 相机速度在不同 zoom 下主观稳定。
- 边缘滚动靠近边缘逐步加速，而不是突然跳速。
- 编队召回和空组反馈清楚但不抢画面。

## 5. Phase 2 - 选择圈、血条、footprint 精细化

**目标:** 降低视觉噪声，增强边界和单位身份识别。

- [ ] 在 `control_feel_config.json` 增加：

```json
{
  "visual_preset": {
    "mode": "sc1_like",
    "debug_grid_default": false,
    "debug_elevation_default": false,
    "selection_ring_style": "simple"
  }
}
```

- [ ] 修改 `hud_overlay_renderer.gd`：
  - `simple` 模式只画单层清晰选择圈。
  - `enhanced` 模式保留 race-colored dashed ring。
  - 默认 `simple`。
- [ ] 选择圈颜色规则：
  - 本方选中：绿色。
  - 敌方 hover/target：红色。
  - 中立资源 hover：青色或白色低 alpha。
  - 不使用按种族变色作为默认选中圈。
- [ ] 增加 `visual_calibration_overlay.gd`：
  - 显示 sprite bounds。
  - 显示 footprint rect。
  - 显示 selection radius。
  - 显示 pivot cross。
  - 显示 health bar anchor。
- [ ] Test Mode 增加 calibration 开关。
- [ ] 修改 `presentation_manifest.json`，用 worker 作为比例锚点：
  - SCV / Probe / Drone 在同屏大小相近。
  - Marine / Zergling / Zealot 形成可读的基础战斗单位梯度。
  - CommandCenter / Hatchery / Nexus 在 footprint 和 sprite 视觉上同量级。
- [ ] 新增或扩展 `tests/godot/test_visual_class_scale.py`：
  - worker `render_scale` 差异不超过 20%。
  - townhall `selection_radius` 差异不超过 25%。
  - building `health_bar_offset` 必须存在。
  - building `footprint` 或等价字段必须存在。
- [ ] 运行：

```bash
python3 -m pytest tests/godot/test_visual_class_scale.py tests/godot/test_presentation_manifest.py -q
python3 scripts/verify_presentation_scene.py
```

验收：

- 建筑边界不再靠猜。
- 选择圈、footprint、sprite 可在 Test Mode 中一眼对齐。
- 默认画面不出现过度旋转、过度发光、调试线常驻。

## 6. Phase 3 - 战斗事件驱动的 VFX

**目标:** 从“输入时播放特效”升级到“根据战斗状态变化播放特效”。

- [ ] 新增 `godot/scripts/combat_visual_controller.gd`。
- [ ] controller 保存上一帧 entity 状态，并推导事件：
  - `attack_started`
  - `projectile_fired`
  - `hit_confirmed`
  - `shield_hit`
  - `unit_died`
  - `building_damaged`
- [ ] 事件来源优先级：
  - 若 SimCore state 已有明确字段，直接使用。
  - 若缺字段，使用 `attack_target`、hp delta、position delta 推导。
  - 若仍缺，降级为 command input feedback，不伪装成命中。
- [ ] `vfx_manager.gd` 接受 normalized event：

```gdscript
func spawn_combat_event(event: Dictionary) -> void:
	var profile_name: String = str(event.get("vfx_profile", "none"))
	var event_type: String = str(event.get("event_type", ""))
	var source_pos: Vector2 = event.get("source_pos", Vector2.ZERO)
	var target_pos: Vector2 = event.get("target_pos", Vector2.ZERO)
```

- [ ] `vfx_catalog.json` 的 profile 增加 timing 字段：

```json
{
  "terran_ballistic": {
    "attack": "muzzle_flash_small",
    "hit": "hit_spark",
    "death": "small_death_burst",
    "projectile": "hitscan",
    "tracer": "line",
    "priority": 2,
    "projectile_speed_tiles_per_second": 36.0,
    "muzzle_offset_tiles": 0.35,
    "impact_offset_tiles": 0.0
  }
}
```

- [ ] VFX active cap 按 priority 淘汰低优先级特效。
- [ ] 加入 10 个代表单位人工验收：
  - Marine
  - Tank
  - Firebat
  - Hydralisk
  - Zergling
  - Mutalisk
  - Zealot
  - Dragoon
  - Reaver
  - Carrier
- [ ] 运行：

```bash
python3 -m pytest tests/godot/test_vfx_profiles.py -q
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
```

验收：

- 玩家能分清“我下了攻击命令”和“攻击真的命中”。
- 密集战斗中特效不会遮挡单位轮廓和血条。
- 死亡反馈比普通命中更强，但不长期占据画面。

## 7. Phase 4 - SC1 tileset 与 fog 表达

**目标:** 如果目标是接近 SC1，地形和 fog 需要从 debug/procedural 风格切换到 RTS tileset 风格。

- [ ] 保留 `terrain_renderer.gd` 作为 debug elevation renderer。
- [ ] 新增 `godot/scripts/sc1_tileset_renderer.gd`，职责：
  - 读取 tileset manifest。
  - 按 map tile 绘制地表。
  - 默认使用 nearest filtering。
  - debug elevation 只作为 overlay。
- [ ] 新增 `godot/resources/terrain/tileset_manifest.json`，字段：
  - `tileset_id`
  - `tile_size_px`
  - `atlas`
  - `tile_index_to_rect`
  - `default_tile`
- [ ] `game_view.gd` 根据配置选择 renderer：
  - `terrain_mode = "sc1_tileset"` 使用 `sc1_tileset_renderer.gd`
  - `terrain_mode = "height_debug"` 使用 `terrain_renderer.gd`
- [ ] fog 表达改为三态：
  - unexplored: black
  - explored: dark shroud
  - visible: transparent
- [ ] fog smoothing 只在边缘低幅处理，不把整个 shroud 做成现代渐变雾。
- [ ] 运行：

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/test_presentation_manifest.py -q
```

验收：

- 默认战场不再像 height debug map。
- grid/cliff/elevation 默认关闭。
- fog 与单位可见性一致，不出现单位在雾中仍过亮的问题。

## 8. Phase 5 - Test Mode 变成资源验收台

**目标:** 让 Test Mode 能直接发现比例、pivot、动画、攻击表现问题。

- [x] 修改 `test_mode_gallery.gd`，增加四个视图：
  - `Roster`
  - `Scale`
  - `Animation`
  - `Combat`
- [x] `Roster` 显示 race/kind/domain/role/tier 筛选。
- [x] `Scale` 同屏显示 worker、basic army、townhall、production building。
- [x] `Animation` 循环 idle/move/attack/death。
- [x] `Combat` 生成固定 attacker -> target 对，展示 projectile/hit/death。
- [x] 每个 sprite 下方显示：
  - unit_id
  - render_scale
  - selection_radius
  - footprint
  - vfx_profile
- [x] 增加截图导出按钮或 debug hotkey，将当前 Test Mode 视图写入 `reports/godot-test-mode/`。
- [x] 新增 pytest 检查 Test Mode 所有筛选字段来自 `unit_type_catalog.json`。
- [ ] 运行：

```bash
python3 -m pytest tests/godot/test_unit_type_catalog.py tests/godot/test_visual_class_scale.py -q
```

验收：

- 后续提取资源时，不需要进正式游戏也能人工检查。
- 三族比例差异能在 Scale 视图直接看出来。
- 单位攻击和移动表现可以在 Combat/Animation 视图单独验收。

## 9. Phase 6 - 完整人工验收矩阵

**目标:** 每轮 Godot 手感迭代都用固定动作验收，而不是只看截图。

人工验收动作：

- [ ] Terran：
  - 框选 4 个 SCV。
  - 右键矿区。
  - Ctrl+1 编队。
  - 双击 1 回到编队。
  - 建造 Barracks。
  - Marine attack-move。
- [ ] Zerg：
  - Drone 采集。
  - Zergling move/attack。
  - Hydralisk 远程攻击。
  - Hatchery footprint 检查。
- [ ] Protoss：
  - Probe 采集。
  - Pylon/Nexus/Zealot/Dragoon 比例检查。
  - shield hit 检查。
- [ ] Mixed Combat：
  - 6v6。
  - 12v12。
  - 30v30。
  - 地面打空中。
  - 建筑被攻击。
- [ ] Fog/Terrain：
  - 未探索黑区。
  - 探索后 shroud。
  - 可见区。
  - debug elevation off/on。

记录到：

```text
docs/reports/godot-sc1-feel-gap-report.md
```

启动命令：

```bash
python3 -m simcore.grpc_server
python3 -m simcore.http_gateway
/Applications/Godot.app/Contents/MacOS/Godot --path godot
```

验收：

- 每项有截图或文字记录。
- 每项给出 1-5 分。
- 低于 3 分的项目必须进入下一轮 backlog。

## 10. 执行优先级

P0 必做：

- SC1 feel baseline。
- gap report。
- camera speed 修正。
- input feedback controller。

P1 必做：

- selection ring simple mode。
- visual calibration overlay。
- worker/townhall scale 校准。
- combat visual controller。

P2 建议：

- SC1 tileset renderer。
- Test Mode 四视图。
- screenshot report。

P3 暂缓：

- 更复杂 shader。
- 大规模粒子系统。
- 任何为了视觉效果而修改 SimCore 规则的工作。

## 11. 每阶段提交建议

```bash
git add docs/reports/godot-sc1-feel-gap-report.md godot/resources/feel/sc1_feel_baseline.json tests/godot/test_sc1_feel_baseline.py
git commit -m "godot: add sc1 feel baseline"

git add godot/scripts/camera_controller.gd godot/scripts/input_feedback_controller.gd godot/scripts/game_view.gd
git commit -m "godot: stabilize camera and input feedback"

git add godot/scripts/hud_overlay_renderer.gd godot/scripts/visual_calibration_overlay.gd godot/resources/presentation_manifest.json tests/godot/test_visual_class_scale.py
git commit -m "godot: calibrate selection and visual scale"

git add godot/scripts/combat_visual_controller.gd godot/scripts/vfx_manager.gd godot/resources/vfx/vfx_catalog.json tests/godot/test_vfx_profiles.py
git commit -m "godot: drive combat vfx from state events"

git add godot/scripts/sc1_tileset_renderer.gd godot/resources/terrain/tileset_manifest.json godot/scripts/game_view.gd
git commit -m "godot: add sc1 tileset terrain renderer"
```

提交前检查：

```bash
git status --short
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/ -q -x
```

不要提交：

- `godot/.godot/imported/*`
- Godot editor cache
- 临时 replay
- 原始 SC1 专有资源

