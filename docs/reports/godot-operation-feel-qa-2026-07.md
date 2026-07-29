# Godot 操作手感 P1 QA 报告

**日期：** 2026-07-21  
**引擎：** Godot 4.6.2  
**范围：** 点选、框选、编队、右键语义、attack-move targeting、镜头数学、输入遥测

## 自动化结果

| 指标 | 门槛 | 结果 | 状态 |
|------|------|------|------|
| input-to-feedback P95 | <= 1 帧 | 0 帧（headless 同帧路径） | PASS |
| empty command rate | <= 1% | 0%（测试样本） | PASS |
| control group recall success | 100% | 100%（测试样本） | PASS |
| click target success | >= 95% | 30/30，100% | PASS |
| box selection expected set | >= 95% | 10/10，100% | PASS |
| camera diagonal speed error | <= 1% | < 0.1% | PASS |
| 1280x720 visible world width | 32 +/- 2% | 32 | PASS |
| 1920x1080 visible world width | 32 +/- 2% | 32 | PASS |

自动化命令：

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_operation_feel.gd
python3 -m pytest tests/godot -q -x
```

本轮 Godot 操作行为测试为 **22/22 PASS**；Godot 前端 pytest 回归全量通过，项目 headless 启动与编辑器脚本解析无错误。

## 三族覆盖

自动矩阵为 Terran、Zerg、Protoss 各生成 10 个拥有独立 `selection_radius` 的目标，验证按单位半径选择最接近实体。框选矩阵验证仅返回框内己方实体，并受 12 单位上限保护。

这证明选择几何和种族无关，但不能替代实际精灵透明边界、动画状态和玩家主观反馈测试。

## 人工 60 秒验收

状态：**待人工执行**。

每个分辨率执行以下流程：

1. 四边边缘滚动各 3 次。
2. 点选 SCV、Drone、Probe 和三族基础战斗单位各 5 次。
3. 框选 6 个单位，执行 Ctrl+1、1、双击 1。
4. 右键空地 10 次，确认只移动。
5. 右键敌人 5 次，确认定点攻击。
6. A+左键 5 次，确认红色十字反馈。
7. Shift 点击已选单位 5 次，确认可取消选择。

| 分辨率 | camera pan | edge scroll | click | box select | right-click | group recall | 结论 |
|--------|------------|-------------|-------|------------|-------------|--------------|------|
| 1280x720 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | PENDING |
| 1920x1080 | 待测 | 待测 | 待测 | 待测 | 待测 | 待测 | PENDING |

通过门槛：六项均不低于 4/5。人工门未完成前，不宣称整体操作手感达到 SC1 水平。

## 已知限制

- SimCore 尚无独立 `attack_move` 命令；当前 A+左键保留正确 targeting 和反馈，但命令降级为 formation move。
- `feel_metrics.jsonl` 默认关闭。启用 `debug/feel_metrics_enabled` 后才记录真实对局数据。
- 自动测试测量代码路径与几何正确性，不测鼠标硬件、显示延迟或玩家肌肉记忆。
