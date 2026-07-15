# Godot SC1 手感 Gap Report

> 初始建立日期: 2026-07-06
> 评分标准: 1-5 分 (5 = 完全匹配 SC1 参考行为, 1 = 严重偏离)
> 低于 3 分的项目必须进入下一轮 backlog。

---

## 评分项

| # | 评分项 | SC1 参考行为 | 当前 Godot 行为 | 偏差 | 下一步动作 |
|---|--------|-------------|----------------|------|-----------|
| 1 | Camera pan stability | 键盘/鼠标中键平移速度用屏幕比例表达，不同 zoom 下主观速度一致 | `camera_controller.gd` 在 setup 时 `keyboard_speed *= zoom`，导致不同窗口/地图/zoom 下速度感不稳定 | **评分: 2** — 速度受 zoom 影响不稳定，无 screen-space 速度表达 | 改为 `_screen_speed_to_world()` 计算，移除 setup 中乘 zoom |
| 2 | Camera edge scroll | 鼠标靠近屏幕边缘时渐进加速，28px ramp 区间，速度与键盘平移同源 | 边缘滚动无渐进 ramp，速度与键盘速度耦合且也受 zoom 乘法影响 | **评分: 2** — 无渐进加速，边缘体验生硬 | 加入 `edge_ramp_px` 和 `edge_screen_per_second`，使用 strength clamp |
| 3 | Zoom readability | 默认固定 gameplay zoom，少数档位 (gameplay/inspection/debug)，不随地图自动缩放 | zoom 随地图 setup 自动设置，可能产生极端 zoom，无固定 gameplay preset | **评分: 2** — 无固定预设，zoom 随意变化导致可读性差 | 新增 zoom_presets，默认 gameplay=1.0，debug 另走快捷键 |
| 4 | Click selection accuracy | 点击 slop 4px 内判定选中，点空地立即取消选择，1 帧内反馈 | 点击判定 slop 未标准化，选中反馈可能有帧延迟或依赖 SimCore 回包 | **评分: 2** — slop 值不确定，反馈可能延迟 | 在 `sc1_feel_baseline.json` 固定 `click_slop_px=4.0`，selection_manager 本地判定 |
| 5 | Box selection accuracy | 拖拽阈值 5px，框选最大 12 单位一组，1 帧内高亮 | 框选阈值和最大组数未固定，高亮可能延迟 | **评分: 2** — 阈值和组数无约束 | 固定 `drag_threshold_px=5.0`, `max_group_size=12`，本地高亮 |
| 6 | Right-click acknowledgement | 右键命令后在目标位置显示 0.22s 地面 ping，1 帧内出现，不等待 SimCore | 右键反馈可能散落在 game_view 主脚本中，无独立 controller，可能等回包 | **评分: 2** — 无独立 ping controller，反馈可能延迟 | 新增 `input_feedback_controller.gd`，本地 1 帧内显示 ping |
| 7 | Control group recall | Ctrl+数字键编队，双击数字键镜头跳到编队中心，空组有清晰提示 | 编队功能可能存在但无独立 flash 反馈和镜头跳转逻辑 | **评分: 2** — 缺少编队 flash 和镜头跳转 | `input_feedback_controller.gd` 增加 `show_control_group_flash()` |
| 8 | Unit movement readability | 移动方向和速度通过 sprite 朝向+动画表达，不靠特效遮挡 | 单位移动可能缺少朝向切换或动画节奏，特效可能遮挡 | **评分: 2** — 朝向和动画节奏未校准，特效噪声偏高 | 降低移动特效，对齐 sprite 朝向与移动方向 |
| 9 | Basic combat readability | 能看清谁开火、打向哪里、是否命中、目标是否死亡 | 当前 combat VFX 由命令触发而非状态驱动，命中/死亡反馈弱 | **评分: 2** — 命中和死亡反馈不明确，VFX 偏装饰化 | 新增 `combat_visual_controller.gd`，状态驱动 VFX |
| 10 | Building footprint clarity | 建筑 footprint rect 与 sprite 边界、选择圈、血条对齐 | footprint 可能缺失或与 sprite/选择圈/血条不匹配 | **评分: 2** — footprint 与其他视觉元素不同步 | 在 presentation_manifest 校准，新增 calibration overlay |

---

## 汇总

| 项目 | 初始评分 |
|------|---------|
| camera pan stability | 2 |
| camera edge scroll | 2 |
| zoom readability | 2 |
| click selection accuracy | 2 |
| box selection accuracy | 2 |
| right-click acknowledgement | 2 |
| control group recall | 2 |
| unit movement readability | 2 |
| basic combat readability | 2 |
| building footprint clarity | 2 |
| **平均** | **2.0** |

所有项目均低于 3 分，全部进入 Phase 1+ backlog。
