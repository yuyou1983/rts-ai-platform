# Godot Test Mode QA Follow-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 把当前 Test Mode 从“能展示资源”推进到“可用于人工验收 SC1 资源、比例、动画、战斗 VFX 的稳定诊断台”。

**Architecture:** 保持 Godot L3 表现层内聚，不修改 SimCore 规则。Test Mode 作为 Godot 的 diagnostic mode，应主动隔离普通游戏 HUD、fog、minimap、debug elevation，使用独立 UI 控制器、布局配置和截图验收脚本；`game_view.gd` 只负责接入，不继续承载 Test Mode 的细节。

**Tech Stack:** Godot 4.6.2 GDScript, `godot/scripts/test_mode_gallery.gd`, `godot/scripts/visual_calibration_overlay.gd`, `godot/resources/unit_type_catalog.json`, `godot/resources/presentation_manifest.json`, `godot/resources/vfx/vfx_catalog.json`, pytest, Godot headless smoke scripts.

---

## 1. 当前截图结论

基于本轮 Test Mode 截图，当前状态是“功能框架基本完成，但还不能作为资源验收台”。

### 已完成

- 已有四个视图入口：`Roster`、`Scale`、`Animation`、`Combat`。
- 已有 race/type/domain/role/tier/preview/batch 过滤控件。
- 已有 `VisualCalibrationOverlay`，可显示 pivot、footprint、selection radius、health bar anchor。
- 已有 screenshot 快捷键逻辑。
- 资源能被批量放到地图中，Test Mode 已能调起 generated assets。

### 主要问题

- Test Mode 没有隔离普通 HUD：右侧资源栏、portrait、APM、minimap 仍然占画面。
- fog/shroud 仍然影响 Test Mode，可验收区域被右侧黑雾切掉。
- 左侧 Test Mode 菜单和 zoom/elevation/calibration 按钮遮挡精灵。
- Roster filter panel 覆盖地图和标签，筛选 UI 与资源展示抢空间。
- world-space 标签太小且模糊，截图中大量标题/metadata 不可读。
- Scale view 只能粗略看三族核心单位，缺少 footprint/radius/ruler，不能判断是否真正对齐。
- Animation view 单位过小、分布稀疏，当前阶段名和单位动作关系不清楚。
- Combat view 空间利用率低，攻击者/目标/VFX 关系不明显，无法判断 projectile/hit/death 是否正确。
- 多数单位带强烈洋红 tint，诊断模式下会干扰判断原始资源色彩。
- 小地图在 Test Mode 中显示大量点，但无法帮助资源验收，反而占据注意力。

## 2. 当前自动校验

本轮已验证：

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot/ -q -x
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_input_feedback_controller.gd
```

结果：

- presentation manifest 校验通过。
- `tests/godot/` 全量通过。
- `test_input_feedback_controller.gd` 16/16 通过。

发现一个缺口：

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
```

当前失败原因：

```text
File not found: res://scripts/test_vfx_catalog_profiles.gd
```

说明 VFX profile 的 pytest 已存在，但 Godot headless 层的 VFX catalog smoke 没有落地。

## 3. P0 - Test Mode 隔离普通游戏 UI

**目标:** 进入 Test Mode 后，截图画面只服务资源验收，不被正式游戏 HUD、fog、minimap 干扰。

**Files:**

- Modify: `godot/scripts/game_view.gd`
- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `godot/scripts/hud.gd`
- Modify: `godot/scripts/hud_overlay_renderer.gd`
- Test: `tests/godot/test_testmode_isolation.py`

- [x] **Step 1: 增加 Test Mode isolation 状态**

在 `game_view.gd` 中增加一个明确入口：

```gdscript
func _set_test_mode_isolation(enabled: bool) -> void:
	if _hud:
		_hud.visible = not enabled
	if _hud_overlay:
		_hud_overlay.set_test_mode_isolation(enabled)
	if _mm_rect_node:
		_mm_rect_node.visible = not enabled
	if _fog_renderer:
		_fog_renderer.visible = not enabled
	queue_redraw()
```

- [x] **Step 2: Test Mode toggle 时调用 isolation**

在 Test Mode 打开/关闭分支中调用：

```gdscript
_set_test_mode_isolation(_test_gallery != null and _test_gallery.is_active())
```

- [x] **Step 3: HUD overlay 增加 isolation API**

在 `hud_overlay_renderer.gd` 增加：

```gdscript
var _test_mode_isolation: bool = false

func set_test_mode_isolation(enabled: bool) -> void:
	_test_mode_isolation = enabled

func is_test_mode_isolation() -> bool:
	return _test_mode_isolation
```

并在绘制 combat pings、control hints、normal gameplay overlays 时跳过不必要层。选择圈和 calibration overlay 可保留。

- [x] **Step 4: 新增 pytest 静态护栏**

创建 `tests/godot/test_testmode_isolation.py`：

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_game_view_has_test_mode_isolation_hook() -> None:
    text = (ROOT / "godot/scripts/game_view.gd").read_text(encoding="utf-8")
    assert "func _set_test_mode_isolation" in text
    assert "_set_test_mode_isolation(" in text


def test_hud_overlay_has_isolation_api() -> None:
    text = (ROOT / "godot/scripts/hud_overlay_renderer.gd").read_text(encoding="utf-8")
    assert "func set_test_mode_isolation" in text
    assert "func is_test_mode_isolation" in text
```

- [x] **Step 5: 运行校验**

```bash
python3 -m pytest tests/godot/test_testmode_isolation.py -q
python3 -m pytest tests/godot/ -q -x
```

**验收:** Test Mode 截图中不再显示普通游戏 HUD、portrait、APM、minimap；fog 不再切掉验收区域。

## 4. P0 - 修复 Test Mode UI 遮挡

**目标:** 菜单、过滤器、精灵展示互不遮挡；截图中的 UI 信息可读。

**Files:**

- Create: `godot/scripts/test_mode_ui_controller.gd`
- Modify: `godot/scripts/test_mode_gallery.gd`
- Test: `tests/godot/test_testmode_ui_layout.py`

- [x] **Step 1: 新增 UI controller**

创建 `godot/scripts/test_mode_ui_controller.gd`：

```gdscript
class_name TestModeUIController
extends Control

signal mode_selected(mode: String)
signal filter_changed(key: String, value: String)

var mode_sidebar: VBoxContainer
var filter_panel: PanelContainer

func setup() -> void:
	anchor_left = 0.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	mouse_filter = Control.MOUSE_FILTER_PASS

	mode_sidebar = VBoxContainer.new()
	mode_sidebar.name = "ModeSidebar"
	mode_sidebar.anchor_left = 0.0
	mode_sidebar.anchor_top = 0.0
	mode_sidebar.anchor_right = 0.0
	mode_sidebar.anchor_bottom = 0.0
	mode_sidebar.offset_left = 12
	mode_sidebar.offset_top = 96
	mode_sidebar.offset_right = 156
	mode_sidebar.offset_bottom = 360
	add_child(mode_sidebar)

	filter_panel = PanelContainer.new()
	filter_panel.name = "FilterPanel"
	filter_panel.anchor_left = 0.0
	filter_panel.anchor_top = 0.0
	filter_panel.anchor_right = 1.0
	filter_panel.anchor_bottom = 0.0
	filter_panel.offset_left = 168
	filter_panel.offset_top = 12
	filter_panel.offset_right = -320
	filter_panel.offset_bottom = 172
	filter_panel.visible = false
	add_child(filter_panel)
```

- [x] **Step 2: 从 `test_mode_gallery.gd` 移走 hardcoded UI positions**

删除或封装这些硬编码位置：

```gdscript
_test_btn.position = Vector2(8, 8)
_elev_btn.position = Vector2(8, 42)
_calib_btn.position = Vector2(8, 68)
btn.position = Vector2(8, 110 + i * 26)
_test_filter_panel.offset_left = 132
_test_filter_panel.offset_right = 900
```

改为由 `TestModeUIController` 创建和管理 UI。

- [x] **Step 3: 增加展示安全区**

在 `test_mode_gallery.gd` 增加 layout constants：

```gdscript
const TESTMODE_WORLD_ORIGIN := Vector2(8.0, 6.0)
const TESTMODE_WORLD_RIGHT_LIMIT := 54.0
const TESTMODE_WORLD_BOTTOM_LIMIT := 58.0
```

所有 `_create_view_*()` 从 `TESTMODE_WORLD_ORIGIN` 开始排布，避免左侧 UI 遮挡。

- [x] **Step 4: 静态测试禁止旧硬编码复发**

创建 `tests/godot/test_testmode_ui_layout.py`：

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_testmode_ui_controller_exists() -> None:
    path = ROOT / "godot/scripts/test_mode_ui_controller.gd"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "class_name TestModeUIController" in text
    assert "ModeSidebar" in text
    assert "FilterPanel" in text


def test_gallery_uses_world_safe_area_constants() -> None:
    text = (ROOT / "godot/scripts/test_mode_gallery.gd").read_text(encoding="utf-8")
    assert "TESTMODE_WORLD_ORIGIN" in text
    assert "TESTMODE_WORLD_RIGHT_LIMIT" in text
    assert "TESTMODE_WORLD_BOTTOM_LIMIT" in text
```

- [x] **Step 5: 运行校验**

```bash
python3 -m pytest tests/godot/test_testmode_ui_layout.py -q
```

**验收:** 左侧菜单不再压住单位；Roster filter panel 不再覆盖主要展示区域。

## 5. P1 - 标签改成屏幕空间渲染

**目标:** 标签和 metadata 在截图中可读，不随 camera zoom 变成糊块。

**Files:**

- Create: `godot/scripts/test_mode_label_layer.gd`
- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `godot/scripts/game_view.gd`
- Test: `tests/godot/test_testmode_label_layer.py`

- [x] **Step 1: 新增 label layer**

创建 `godot/scripts/test_mode_label_layer.gd`：

```gdscript
class_name TestModeLabelLayer
extends Control

var _camera: Camera2D
var _font: Font
var _labels: Array = []

func setup(camera: Camera2D, font: Font) -> void:
	_camera = camera
	_font = font
	anchor_left = 0.0
	anchor_top = 0.0
	anchor_right = 1.0
	anchor_bottom = 1.0
	mouse_filter = Control.MOUSE_FILTER_IGNORE

func set_labels(labels: Array) -> void:
	_labels = labels
	queue_redraw()

func _draw() -> void:
	if _camera == null or _font == null:
		return
	for label in _labels:
		var world_pos: Vector2 = label.get("world_pos", Vector2.ZERO)
		var text: String = str(label.get("text", ""))
		var color: Color = label.get("color", Color.WHITE)
		var screen_pos: Vector2 = _camera.get_canvas_transform() * world_pos
		draw_string(_font, screen_pos, text, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, color)
```

- [x] **Step 2: TestModeGallery 输出 label model**

在 `test_mode_gallery.gd` 增加：

```gdscript
func get_screen_labels() -> Array:
	var labels: Array = []
	for header in _test_section_headers:
		labels.append({
			"world_pos": header.get("pos", Vector2.ZERO),
			"text": str(header.get("text", "")),
			"color": header.get("color", Color.WHITE),
		})
	for e in _test_ents:
		if bool(e.get("preview_hidden", false)):
			continue
		var text := str(e.get("label", ""))
		if text != "":
			labels.append({
				"world_pos": Vector2(float(e.get("px", 0.0)) + 0.6, float(e.get("py", 0.0)) + 0.9),
				"text": text,
				"color": Color(0.95, 0.95, 0.9, 0.95),
			})
	return labels
```

- [x] **Step 3: 禁用旧 world-space label 绘制**

`draw_labels()` 保留但只在 debug flag 下启用，默认使用 `TestModeLabelLayer`。

- [x] **Step 4: 添加测试**

创建 `tests/godot/test_testmode_label_layer.py`：

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_testmode_label_layer_exists() -> None:
    text = (ROOT / "godot/scripts/test_mode_label_layer.gd").read_text(encoding="utf-8")
    assert "class_name TestModeLabelLayer" in text
    assert "func set_labels" in text
    assert "func _draw" in text


def test_gallery_exposes_screen_labels() -> None:
    text = (ROOT / "godot/scripts/test_mode_gallery.gd").read_text(encoding="utf-8")
    assert "func get_screen_labels" in text
```

**验收:** 截图中模式标题、单位名、scale/radius/vfx metadata 都清晰可读。

## 6. P1 - Scale View 做成比例验收板

**目标:** Scale view 能直接判断三族 worker、基础兵、主基地、生产建筑是否对齐。

**Files:**

- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `godot/scripts/visual_calibration_overlay.gd`
- Modify: `tests/godot/test_visual_class_scale.py`

- [x] **Step 1: Scale view 默认开启 calibration overlay**

进入 `scale` 模式时：

```gdscript
if _gallery_mode == "scale":
	_show_calibration = true
	if _calibration_overlay:
		_calibration_overlay.active = true
```

- [x] **Step 2: 增加 tile ruler**

在 `visual_calibration_overlay.gd` 增加：

```gdscript
func draw_tile_ruler(canvas: CanvasItem, origin: Vector2, tile_count: int = 8) -> void:
	for i in range(tile_count + 1):
		var x := origin.x + float(i)
		canvas.draw_line(Vector2(x, origin.y), Vector2(x, origin.y + 0.25), Color(1, 1, 1, 0.55), 0.03)
	canvas.draw_line(origin, origin + Vector2(float(tile_count), 0.0), Color(1, 1, 1, 0.55), 0.03)
```

- [x] **Step 3: Scale view 固定三列四行**

布局必须固定：

```text
             Terran        Zerg        Protoss
Workers      SCV           Drone       Probe
Basic Army   Marine        Zergling    Zealot
Townhall     CommandCenter Hatchery    Nexus
Production   Barracks      SpawningPool Gateway
```

每个 cell 显示：

```text
unit_id
rs=<render_scale> sr=<selection_radius>
fp=<footprint> hbo=<health_bar_offset>
```

- [x] **Step 4: 加强比例测试**

扩展 `tests/godot/test_visual_class_scale.py`：

```python
def test_scale_anchor_units_exist_in_manifest() -> None:
    anchors = [
        "SCV", "Drone", "Probe",
        "Marine", "Zergling", "Zealot",
        "CommandCenter", "Hatchery", "Nexus",
        "Barracks", "SpawningPool", "Gateway",
    ]
    # load presentation_manifest.json and assert every anchor exists in unit_visuals or building_visuals
```

**验收:** Scale 截图不需要主观猜测，能直接看到 footprint/radius/pivot 是否对齐。

## 7. P1 - Combat View 做成 VFX 验收板

**目标:** Combat view 能验证 projectile、hit、death，而不是只显示两排小单位。

**Files:**

- Modify: `godot/scripts/test_mode_gallery.gd`
- Modify: `godot/scripts/combat_visual_controller.gd`
- Modify: `godot/scripts/vfx_manager.gd`
- Create: `godot/scripts/test_vfx_catalog_profiles.gd`
- Test: `tests/godot/test_vfx_profiles.py`

- [x] **Step 1: Combat view 每行显示一个 profile**

固定覆盖：

```gdscript
const _COMBAT_PAIRS: Array = [
	{"profile": "terran_ballistic", "attacker": "Marine", "target": "Zergling"},
	{"profile": "terran_explosive", "attacker": "Tank", "target": "Dragoon"},
	{"profile": "terran_flame", "attacker": "Firebat", "target": "Zergling"},
	{"profile": "zerg_melee", "attacker": "Zergling", "target": "Marine"},
	{"profile": "zerg_acid", "attacker": "Hydralisk", "target": "Zealot"},
	{"profile": "protoss_psi", "attacker": "Dragoon", "target": "Hydralisk"}
]
```

- [x] **Step 2: 每行绘制攻击轨道**

在 attacker 和 target 之间显示：

```text
attacker sprite -> projectile lane -> target sprite -> hit/death marker
```

不要把 attacker 和 target 放太远；固定 4-5 tiles 间距。

- [x] **Step 3: Combat view 主动触发 VFX manager**

`_update_combat_phase()` 不只改 `preview_action`，还要调用一个 signal：

```gdscript
signal combat_preview_event(event: Dictionary)
```

event 示例：

```gdscript
combat_preview_event.emit({
	"event_type": "projectile_fired",
	"vfx_profile": pair.get("profile", "none"),
	"source_pos": attacker_pos,
	"target_pos": target_pos,
})
```

由 `game_view.gd` 转发给 `vfx_manager.spawn_combat_event(event)`。

- [x] **Step 4: 补齐缺失的 Godot headless VFX script**

创建 `godot/scripts/test_vfx_catalog_profiles.gd`：

```gdscript
extends SceneTree

const VFX_CATALOG_PATH := "res://resources/vfx/vfx_catalog.json"

func _init() -> void:
	var ok := true
	var text := FileAccess.get_file_as_string(VFX_CATALOG_PATH)
	if text == "":
		push_error("missing vfx catalog")
		ok = false
	var parsed = JSON.parse_string(text)
	if not (parsed is Dictionary):
		push_error("vfx catalog is not a dictionary")
		ok = false
	else:
		var profiles: Dictionary = parsed.get("profiles", {})
		for required in ["terran_ballistic", "terran_explosive", "terran_flame", "zerg_melee", "zerg_acid", "protoss_psi"]:
			if not profiles.has(required):
				push_error("missing profile: %s" % required)
				ok = false
	quit(0 if ok else 1)
```

- [x] **Step 5: 运行**

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
python3 -m pytest tests/godot/test_vfx_profiles.py -q
```

**验收:** Combat view 每一行都能看出 profile、攻击者、目标、弹道、命中、死亡阶段。

## 8. P2 - Roster View 分页和截图基准

**目标:** Roster 不再把 93 个资源塞进同一个巨大地图，而是按页验收。

**Files:**

- Modify: `godot/scripts/test_mode_gallery.gd`
- Create: `godot/scripts/testmode_screenshot_exporter.gd`
- Test: `tests/godot/test_testmode_screenshot_exporter.py`

- [x] **Step 1: 增加 page state**

```gdscript
var _test_page: int = 0
const TESTMODE_ITEMS_PER_PAGE := 24
```

- [x] **Step 2: Roster 根据当前 filter 后分页**

构造 `visible_ids` 后：

```gdscript
var start := _test_page * TESTMODE_ITEMS_PER_PAGE
var end := mini(start + TESTMODE_ITEMS_PER_PAGE, visible_ids.size())
var page_ids := visible_ids.slice(start, end)
```

- [x] **Step 3: UI 增加 Prev/Next Page**

显示：

```text
Page 1/4
```

- [x] **Step 4: 截图导出所有标准视图**

创建 `godot/scripts/testmode_screenshot_exporter.gd`，提供：

```gdscript
func export_all_modes(output_dir: String) -> void:
	for mode in ["roster", "scale", "animation", "combat"]:
		# switch mode, wait one frame, save PNG
```

- [x] **Step 5: 运行并记录截图**

输出目录建议：

```text
reports/godot-testmode/YYYYMMDD-HHMM/
```

**验收:** 每轮资源提取后，可导出固定四张以上截图进行人工对比。

## 9. P2 - 色彩诊断模式

**目标:** 解决当前截图里强洋红 team color/tint 干扰原图判断的问题。

**Files:**

- Modify: `godot/resources/feel/control_feel_config.json`
- Modify: `godot/scripts/entity_visual.gd`
- Modify: `godot/scripts/test_mode_gallery.gd`
- Test: `tests/godot/test_control_feel_config.py`

- [x] **Step 1: 增加 Test Mode tint policy**

在 `control_feel_config.json` 增加：

```json
{
  "test_mode": {
    "hide_game_hud": true,
    "force_fog_visible": true,
    "neutral_team_tint": true,
    "show_minimap": false,
    "show_world_grid": false
  }
}
```

- [x] **Step 2: Test entity 增加 neutral tint flag**

在 `_make_test_asset_entity()` 返回字典增加：

```gdscript
"neutral_team_tint": true
```

- [x] **Step 3: EntityVisual/Sprite 更新时尊重 neutral tint**

如果 entity 有 `neutral_team_tint == true`，不要套玩家强 tint，只显示资源原色。

- [x] **Step 4: 测试配置字段**

扩展 `tests/godot/test_control_feel_config.py`：

```python
def test_test_mode_config_exists(config: dict) -> None:
    test_mode = config["test_mode"]
    assert test_mode["hide_game_hud"] is True
    assert test_mode["force_fog_visible"] is True
    assert test_mode["neutral_team_tint"] is True
```

**验收:** Test Mode 默认显示资源原始色彩；需要看队伍色时再手动打开。

## 10. 最终验收矩阵

每轮完成后必须提交以下证据：

- `python3 scripts/verify_presentation_scene.py`
- `python3 -m pytest tests/godot/ -q -x`
- `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_input_feedback_controller.gd`
- `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd`
- 四张截图：
  - `roster_all_page_1.png`
  - `scale_core.png`
  - `animation_units.png`
  - `combat_profiles.png`

人工判定标准：

- UI 不遮挡任何待验收 sprite。
- 标签清晰可读。
- Scale view 能看出三族 worker/basic/townhall/production 的比例关系。
- Combat view 能看出 attacker -> projectile -> hit -> death。
- Test Mode 默认不显示普通游戏 HUD、fog、minimap。
- Calibration overlay 开启后能明确显示 pivot、footprint、selection radius、health bar anchor。

## 11. 建议执行顺序

1. P0 Test Mode isolation。
2. P0 UI 遮挡修复。
3. P1 screen-space labels。
4. P1 Scale view 验收板。
5. P1 Combat view VFX 验收板。
6. P2 Roster 分页和截图导出。
7. P2 neutral tint / 色彩诊断模式。

每个 P0/P1 小节单独提交，避免再次形成一个难以回滚的大 Test Mode 改动。

