# Godot Operation Feel Iteration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `systematic-debugging`, `test-driven-development`, and `godot-specialist` while implementing this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修正当前 Godot 前端输入语义和镜头模型，并建立可重复的操作手感测试，使点选、框选、右键、攻击移动、编队和镜头达到稳定、清晰、接近 SC1 的操作闭环。

**Architecture:** 所有改动保持在 Godot L3，不改变 SimCore 的战斗规则。`game_view.gd` 只负责把输入意图路由到独立控制器；选择规则归 `selection_manager.gd`，镜头规则归 `camera_controller.gd`，即时视觉确认归 `input_feedback_controller.gd`。运行参数只从 `control_feel_config.json` 读取，`sc1_feel_baseline.json` 作为验收目标，避免双配置源互相覆盖。

**Tech Stack:** Godot 4.6.2, typed GDScript, JSON configuration, Godot headless smoke tests, pytest static/config guards, manual 60-second interaction trials.

---

## P0-P1 执行状态（2026-07-21）

| Task | 状态 | 结果 |
|------|------|------|
| Task 1 失败行为契约 | 完成 | 新增 pytest 契约与 Godot headless 行为测试 |
| Task 2 编队召回 | 完成 | 修复普通数字键不可召回及双击跳转分支 |
| Task 3 输入意图 | 完成 | 新增纯 `InputIntentRouter`；右键空地恢复移动；A+左键进入 attack-move targeting |
| Task 4 相机模型 | 完成 | 单一运行配置、可见世界宽度 zoom、对角归一化、UI/失焦边缘滚动抑制 |
| Task 5 选择几何 | 完成 | manifest 命中半径、5px click/drag、Shift toggle、三族点选/框选矩阵 |
| Task 6 手感遥测 | 完成 | 默认关闭的 JSONL recorder 与 P95/空命令率/编队成功率汇总 |
| Task 7 验收 | 自动完成/人工待验收 | 30 次点选、10 次框选、双分辨率数学通过；人工 60 秒门待执行 |

说明：SimCore 当前没有独立 `attack_move` 命令。P0 保留正确的输入状态和红色地面反馈，命令层明确降级为 formation move；真正的沿途索敌需要后续 ADR 决定是否扩展 Proto/SimCore。

## 1. 本轮审计结论

截至提交 `452895e`，Test Mode、资源比例、输入反馈、战斗 VFX 和 tileset 基础设施已经落地。自动校验通过：

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot -q -x
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_input_feedback_controller.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
```

但现有测试主要证明文件、配置和独立控制器存在，尚未证明真实输入链路正确。当前 P0 问题如下：

1. `game_view.gd` 的编队热键分支缩进错误。数字键召回位于 `if _selection` 的 `else` 中；正常存在 `SelectionManager` 时，非 Ctrl/Shift 数字键没有召回动作。
2. 战斗单位右键空地被解释为 `attack_nearest`。这与 SC1 的上下文命令不一致：右键空地应移动，A + 左键才是 attack-move。
3. `camera_controller.setup()` 在 `set_map_size()` 之前调用，初始 zoom 使用默认 64x64，而不是服务器返回的真实地图尺寸。
4. 相机动态最小 zoom 强制整个地图装入视口。RTS 正式视角应按可读的世界跨度定义，地图边界只负责 clamp，不应决定默认单位视觉尺寸。
5. 选择链路仍使用硬编码 `5.0` 和全局 `SELECT_RADIUS`；配置中的 `drag_threshold_px`、`click_slop_px` 和资源的 `selection_radius` 没有完整贯穿真实输入。
6. `sc1_feel_baseline.json` 与 `control_feel_config.json` 同时作为运行时输入，优先级隐藏在脚本中，调参时无法确定哪个值真正生效。
7. 右键处理包含逐次 `print()`，高频操作会污染日志并影响性能测量。

## 2. 文件责任

**新增：**

- `godot/scripts/input_intent_router.gd`：把原始鼠标/键盘事件归一化为 select、move、attack、attack_move、gather、build、control_group 意图。
- `godot/scripts/feel_metrics_recorder.gd`：记录 input-to-feedback 帧数、误选、空命令、镜头位移和编队召回结果；不依赖 SimCore。
- `godot/scripts/test_operation_feel.gd`：Godot headless 行为测试，直接验证输入意图、编队和镜头数学。
- `tests/godot/test_operation_feel_contract.py`：静态架构和配置单一来源护栏。
- `docs/reports/godot-operation-feel-qa-2026-07.md`：人工测试结果模板和每轮分数。

**修改：**

- `godot/scripts/game_view.gd`：接入 intent router；修复编队分支；删除右键高频诊断日志；不再内嵌上下文命令判定。
- `godot/scripts/selection_manager.gd`：集中 click/drag/modifier/selection-radius 规则。
- `godot/scripts/camera_controller.gd`：先接收地图信息再 setup；用目标可见世界宽度定义 zoom；地图仅用于边界 clamp。
- `godot/scripts/input_feedback_controller.gd`：按意图绘制 move/attack/attack-move/invalid 的即时反馈，并输出反馈创建帧。
- `godot/resources/feel/control_feel_config.json`：成为唯一运行时手感配置。
- `godot/resources/feel/sc1_feel_baseline.json`：只保存验收阈值，不参与运行时覆盖。
- `docs/godot_verification_guide.md`：增加操作手感专项测试步骤。

## 3. Task 1 - 锁定当前失败行为

- [ ] 创建 `tests/godot/test_operation_feel_contract.py`，先写以下失败测试：

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_game_view_routes_plain_number_to_group_recall() -> None:
    text = (ROOT / "godot/scripts/game_view.gd").read_text(encoding="utf-8")
    assert "func _handle_control_group_key" in text
    assert "_selection.select_hotkey_group(group_idx)" in text


def test_ground_right_click_is_not_attack_nearest() -> None:
    text = (ROOT / "godot/scripts/game_view.gd").read_text(encoding="utf-8")
    assert 'action = "attack_nearest"' not in text


def test_runtime_does_not_load_baseline_as_config() -> None:
    for name in ("camera_controller.gd", "input_feedback_controller.gd"):
        text = (ROOT / "godot/scripts" / name).read_text(encoding="utf-8")
        assert "_load_baseline_config" not in text
```

- [ ] 运行并确认失败：

```bash
python3 -m pytest tests/godot/test_operation_feel_contract.py -q
```

预期：三个测试均失败，证明测试捕获了当前真实问题。

- [ ] 创建 `godot/scripts/test_operation_feel.gd`，测试框架至少提供 `_assert_true()`、失败计数和非零退出码。

- [ ] 提交：

```bash
git add tests/godot/test_operation_feel_contract.py godot/scripts/test_operation_feel.gd
git commit -m "test(godot): lock operation feel regressions"
```

## 4. Task 2 - 修复编队召回语义

- [ ] 在 `game_view.gd` 提取单一函数：

```gdscript
func _handle_control_group_key(group_idx: int, event: InputEventKey) -> void:
	if _selection == null:
		return
	if event.ctrl_pressed:
		_selection.create_hotkey_group(group_idx)
		_input_feedback_ctrl.show_control_group_flash(group_idx, true)
		return
	if event.shift_pressed:
		_selection.add_to_hotkey_group(group_idx)
		_input_feedback_ctrl.show_control_group_flash(group_idx, true)
		return

	var now: float = Time.get_ticks_msec() / 1000.0
	if _last_group_key == group_idx and now - _last_group_time <= 0.30:
		_selection.jump_to_hotkey_group(group_idx)
		_last_group_key = -1
		_last_group_time = 0.0
	else:
		_selection.select_hotkey_group(group_idx)
		if _selection.get_selected_ids().is_empty():
			_input_feedback_ctrl.show_control_group_flash(group_idx, false)
		_last_group_key = group_idx
		_last_group_time = now
```

- [ ] 在 headless 测试覆盖：Ctrl+1 建组、1 召回、连续两次 1 请求镜头跳转、空组有反馈。

- [ ] 运行：

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_operation_feel.gd
python3 -m pytest tests/godot/test_operation_feel_contract.py -q
```

- [ ] 提交：

```bash
git add godot/scripts/game_view.gd godot/scripts/test_operation_feel.gd tests/godot/test_operation_feel_contract.py
git commit -m "fix(godot): restore control group recall and camera jump"
```

## 5. Task 3 - 分离输入意图与命令生成

- [ ] 创建 `input_intent_router.gd`，只判断意图，不提交命令：

```gdscript
class_name InputIntentRouter
extends RefCounted

enum Intent { NONE, MOVE, ATTACK, ATTACK_MOVE, GATHER, BUILD, RALLY }

func resolve_right_click(has_units: bool, has_buildings: bool, has_workers: bool,
		clicked: Dictionary) -> Intent:
	if has_buildings and not has_units:
		return Intent.RALLY
	if clicked.is_empty():
		return Intent.MOVE
	if int(clicked.get("owner", 0)) > 1 and str(clicked.get("type", "")) != "resource":
		return Intent.ATTACK
	if has_workers and str(clicked.get("type", "")) == "resource":
		return Intent.GATHER
	return Intent.MOVE
```

- [ ] 增加显式 attack-move 状态：按 A 进入 targeting；左键地面生成 `attack_move` 意图；Esc 或右键取消 targeting。

- [ ] 禁止右键空地搜索最近敌人。若 SimCore 暂无 `attack_move` 命令，Godot 先发送 move，并在文档登记协议缺口；不要伪装成攻击最近目标。

- [ ] 反馈映射必须固定：MOVE=绿色，ATTACK=红色目标，ATTACK_MOVE=红色地面十字，INVALID=灰红短闪。

- [ ] headless 覆盖六种上下文：单位+空地、单位+敌人、工人+资源、建筑+空地、A+空地、无选择+右键。

- [ ] 提交：

```bash
git add godot/scripts/input_intent_router.gd godot/scripts/game_view.gd godot/scripts/input_feedback_controller.gd godot/scripts/test_operation_feel.gd
git commit -m "refactor(godot): normalize RTS input intents"
```

## 6. Task 4 - 修正相机坐标模型

- [ ] 调整初始化顺序：

```gdscript
_cam_ctrl = CameraControllerScript.new()
add_child(_cam_ctrl)
_cam_ctrl.set_map_size(_map_w, _map_h)
_cam_ctrl.setup(_camera)
```

- [ ] 在运行配置增加可读视野目标：

```json
"camera": {
  "gameplay_visible_world_width": 32.0,
  "inspection_visible_world_width": 22.0,
  "overview_visible_world_width": 48.0,
  "keyboard_screen_per_second": 0.72,
  "edge_screen_per_second": 0.62,
  "edge_scroll_margin": 20.0,
  "edge_ramp_px": 20.0
}
```

- [ ] zoom 计算改为 `viewport_width / visible_world_width`。地图尺寸只用于 `_clamp_camera()`；小地图允许镜头停在中心，不把动态最小 zoom 强塞到 `max_zoom` 以上。

- [ ] 键盘对角移动向量先 normalize，避免斜向速度为横向的 1.414 倍。

- [ ] 边缘滚动在窗口失焦、鼠标位于 HUD/Test Mode UI、或中键拖拽时暂停。

- [ ] headless 数学测试覆盖 1280x720、1920x1080 两种视口：相同 preset 的可见世界宽度误差小于 2%；W 与 W+D 一秒位移长度相同，误差小于 1%。

- [ ] 提交：

```bash
git add godot/scripts/camera_controller.gd godot/scripts/game_view.gd godot/resources/feel/control_feel_config.json godot/scripts/test_operation_feel.gd
git commit -m "fix(godot): make camera scale and movement screen-stable"
```

## 7. Task 5 - 统一选择命中规则

- [ ] `game_view.gd` 不再用硬编码 `5.0` 判断 click/drag，调用 `SelectionManager.classify_pointer_release(start, end)`。

- [ ] 点选命中使用 presentation manifest 的 `selection_radius`，屏幕最小命中半径设为 6 px，避免缩放后小单位难以点击。

- [ ] 框选规则固定：默认只选择己方单位；建筑与单位同框时遵守 `building_priority`；Shift=增减选择；Ctrl+点击=当前视口同类型；上限 12。

- [ ] 选择反馈在本地事件当帧出现，不等待下一次服务端状态刷新。

- [ ] headless 覆盖临界值：4.9 px 为点击、5.1 px 为框选；小单位 6 px 命中；敌方单位不可加入己方编队；Shift toggle 正反两次恢复原集合。

- [ ] 提交：

```bash
git add godot/scripts/game_view.gd godot/scripts/selection_manager.gd godot/scripts/test_operation_feel.gd
git commit -m "fix(godot): unify click and box selection geometry"
```

## 8. Task 6 - 建立手感遥测而非主观猜测

- [ ] 创建 `feel_metrics_recorder.gd`，每个动作记录：`event_name`、`input_frame`、`feedback_frame`、`command_frame`、`selected_count`、`result`。

- [ ] 只在 `debug/feel_metrics_enabled=true` 时记录到 `user://feel_metrics.jsonl`，正式运行默认关闭。

- [ ] 增加聚合指标：

```text
input_to_feedback_frames_p95 <= 1
empty_command_rate <= 1%
control_group_recall_success = 100%
click_target_success >= 95% (30 次固定目标)
box_select_expected_set >= 95% (10 个固定场景)
camera_diagonal_speed_error <= 1%
```

- [ ] 创建 `docs/reports/godot-operation-feel-qa-2026-07.md`，每次人工验证记录硬件、分辨率、地图、动作次数、指标和主观 1-5 分。

- [ ] 提交：

```bash
git add godot/scripts/feel_metrics_recorder.gd godot/scripts/game_view.gd docs/reports/godot-operation-feel-qa-2026-07.md
git commit -m "test(godot): add operation feel metrics"
```

## 9. Task 7 - 真实对局 60 秒验收

- [ ] 使用 Terran 开局场景，固定执行：边缘滚动四边各 3 次、框选 6 个单位、Ctrl+1、1、双击 1、右键移动 10 次、右键敌人 5 次、A+左键 5 次、Shift 增减选择 5 次。

- [ ] 使用 Zerg 和 Protoss 各重复一次点选、框选、编队、移动，排除精灵尺寸导致的种族偏差。

- [ ] 在 1280x720 与 1920x1080 各执行一次；记录 metrics 和截图。

- [ ] 评分门槛：camera pan、edge scroll、click selection、box selection、right-click acknowledgement、control group recall 六项均不低于 4/5；任一项低于 4，不进入 VFX 或新兵种迭代。

- [ ] 全量回归：

```bash
python3 scripts/verify_presentation_scene.py
python3 -m pytest tests/godot -q -x
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_operation_feel.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_input_feedback_controller.gd
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_catalog_profiles.gd
```

- [ ] 更新 `docs/reports/godot-sc1-feel-gap-report.md`，不保留未经复测的旧分数。

## 10. 执行顺序与边界

严格按 `Task 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7` 执行。P0 是 Task 1-4，未通过前不要调整动画、VFX、地形和资源比例。Task 5-7 是 P1 验收闭环。

本轮不做：SimCore 战斗数值修改、寻路算法重写、单位 AI 重构、音效系统、更多 SC1 资源提取。若 attack-move 在 Proto/SimCore 中确实缺失，单独创建跨层 ADR 和后续计划，不在本轮偷偷扩展协议。

## 11. 完成定义

- 普通数字键可召回编队，双击可跳转镜头。
- 右键空地始终是移动；右键敌人是攻击；A+左键是 attack-move。
- 不同分辨率下默认可见世界范围和镜头速度稳定。
- 点选与框选使用同一份运行配置和单位命中半径。
- 输入反馈 p95 不超过 1 帧，且有可复现的 JSONL 证据。
- 三族、两种分辨率的人工验收均达到六项至少 4/5。
- Godot 全量自动测试和三个 headless smoke 全部通过。
