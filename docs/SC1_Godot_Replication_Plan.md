# StarCraft Godot 复刻 — 任务拆解方案

## 项目目标
将 https://github.com/asdwsx1234/StarCraft/ (Web/jQuery/Canvas) 完整复刻到 Godot 4.6，
设计服务端 SimCore 以支持确定性帧同步 + AI 对抗，最终实现 Human vs AI / AI vs AI 的完整闭环。

## 架构决策

### 与现有 rts-ai-platform 的关系
- **SimCore 重写**：基于 StarCraft 原作规则，重写 simcore/ 为完整三族引擎
- **Godot 独立项目**：在 rts-ai-platform/godot/ 下重构，复用现有 HTTP/gRPC 通信层
- **Agent 复用**：现有 Coordinator/Economy/Combat Agent 架构保留，适配新的命令协议

### 核心架构
```
Godot 4.6 (前端)
  ├─ 渲染层：TileMap + AnimatedSprite2D + CanvasItem
  ├─ 输入层：InputMap + 选中/命令系统
  └─ 通信层：HTTPRequest → HTTP Gateway
        │
Python SimCore (后端)
  ├─ 确定性 tick 引擎 (60 TPS logic, lockstep)
  ├─ 完整三族规则 (44 单位 + 42 建筑 + 50+ 升级 + 25+ 技能)
  ├─ A* 寻路 + 碰撞分离
  ├─ gRPC Server → HTTP Gateway
  └─ AgentHub (ScriptAI / Coordinator / RL)
```

## Sprint 拆解 (6 Sprints × ~3 天)

---

### Sprint 0：项目脚手架 & 数据定义 (~3天)
**目标**：搭建 Godot 项目结构，定义所有单位/建筑/技能的配置数据

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 0.1 | Godot 项目初始化 | 项目结构 + InputMap 配置 | 1h |
| 0.2 | 单位配置表 (44单位) | `data/units/terran.json`, `zerg.json`, `protoss.json` | 4h |
| 0.3 | 建筑配置表 (42建筑) | `data/buildings/terran.json`, `zerg.json`, `protoss.json` | 4h |
| 0.4 | 技能配置表 (25+技能) | `data/spells.json` | 3h |
| 0.5 | 升级配置表 (50+升级) | `data/upgrades.json` | 3h |
| 0.6 | 伤害矩阵 & 战斗公式 | `data/combat.json` | 1h |
| 0.7 | Proto3 协议重定义 | `proto/state.proto`, `cmd.proto` | 3h |
| 0.8 | SimCore 骨架重写 | `simcore/engine.py` 新框架 | 4h |
| 0.9 | 测试：配置数据完整性 | `tests/test_data_integrity.py` | 2h |

**交付物**：完整数据定义 + 协议 + 项目骨架，0.9 测试全过

---

### Sprint 1：核心引擎 — 移动/寻路/碰撞 (~3天)
**目标**：SimCore 实现确定性 tick 仿真，含 A* 寻路和碰撞分离

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 1.1 | 地图系统 (瓦片地形) | `simcore/map.py` — TileMap + 路径代价 | 6h |
| 1.2 | A* 寻路引擎 | `simcore/pathfinder.py` — 支持飞行/地面/建筑阻挡 | 6h |
| 1.3 | 移动 & 碰撞分离 | `simcore/movement.py` — 推开重叠单位 | 4h |
| 1.4 | 8方向速度矩阵 | 从原作提取每个单位的 speed → 像素/tick | 2h |
| 1.5 | 命令系统 (move/stop/attack/patrol/hold) | `simcore/commands.py` | 4h |
| 1.6 | gRPC Server 适配 | 重新编译 proto + Server 端 | 2h |
| 1.7 | HTTP Gateway 适配 | 命令格式转换 | 2h |
| 1.8 | 测试：寻路正确性 + 确定性回放 | `tests/test_pathfinder.py` | 3h |

**交付物**：可 headless 运行的 tick 引擎，支持 move/stop，A* 寻路

---

### Sprint 2：经济 & 建造系统 (~3天)
**目标**：实现采矿/采气、建造建筑、训练单位、科技升级的完整闭环

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 2.1 | 资源系统 (矿/气/人口) | `simcore/resource.py` — 三资源追踪 + 支付 | 3h |
| 2.2 | 工人采集循环 | `simcore/gathering.py` — 往返基地+资源点 | 4h |
| 2.3 | 建筑建造 (含科技树前置) | `simcore/construction.py` — 前置校验+建造进度 | 5h |
| 2.4 | 单位训练 + 虫族幼虫系统 | `simcore/production.py` — 队列+计时+幼虫3只 | 5h |
| 2.5 | 升级/研究系统 | `simcore/upgrades.py` — 50+升级效果应用 | 4h |
| 2.6 | 三族特殊机制 | 虫族: 菌毯+变异; 人族: 附加建筑+维修; 神族: 护盾+水晶塔供电 | 6h |
| 2.7 | 测试：经济闭环 + 科技树约束 | `tests/test_economy.py` | 3h |

**交付物**：完整经济+建造+训练+升级系统，三族特殊机制

---

### Sprint 3：战斗 & 技能系统 (~3天)
**目标**：实现完整战斗公式、子弹系统、25+技能、升级效果

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 3.1 | 战斗公式 (伤害矩阵+护甲+护盾) | `simcore/combat.py` — NORMAL/BURST/WAVE × SMALL/MIDDLE/BIG | 4h |
| 3.2 | 子弹系统 (追踪/直射/范围) | `simcore/bullets.py` — 20+弹道类型 | 5h |
| 3.3 | 自动攻击 AI (最近目标优先级) | `simcore/auto_attack.py` — 原作 AI 逻辑 | 3h |
| 3.4 | 人族技能 (Stim/Cloak/Lockdown/Nuke/EMP/Yamato/Heal/Repair/Scanner) | `simcore/spells_terran.py` | 6h |
| 3.5 | 虫族技能 (Burrow/Parasite/Broodling/Ensnare/Consume/DarkSwarm/Plague) | `simcore/spells_zerg.py` | 5h |
| 3.6 | 神族技能 (PsiStorm/Hallucination/Meld/Feedback/Maelstrom/MindControl/Recall/Stasis/DisruptionWeb) | `simcore/spells_protoss.py` | 5h |
| 3.7 | 升级效果应用到战斗 (攻防+射程+速度+护盾) | 集成到 combat.py | 3h |
| 3.8 | 测试：战斗公式 + 技能效果 | `tests/test_combat.py`, `tests/test_spells.py` | 3h |

**交付物**：完整战斗+子弹+技能系统，含所有升级效果

---

### Sprint 4：战争迷雾 & Godot 前端 (~3天)
**目标**：Godot 实现完整 RTS 交互 UI + 迷雾渲染

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 4.1 | Godot 场景结构 | Main → GameWorld → EntityLayer → FogLayer + UI层 | 3h |
| 4.2 | 单位/建筑渲染 (Shape2D 占位) | 矩形/圆形/菱形 + 朝向 + 血条 | 4h |
| 4.3 | 选择系统 (单选/框选/Shift+/Ctrl+/双击) | InputMap + 选中高亮 | 4h |
| 4.4 | 右键命令 (Move/Attack/Gather/Build) | 智能上下文 + 命令队列 | 4h |
| 4.5 | 小地图 (实体标记+点击跳转+视口框) | MiniMap Control | 3h |
| 4.6 | 战争迷雾 (三态渲染:暗/半/透) | FogLayer + shader 或 tilemap | 4h |
| 4.7 | HUD (资源/人口/选中信息/命令卡/操作提示) | Control 节点树 | 4h |
| 4.8 | 摄像头 (WASD+边缘滚动+小地图跳转) | Camera2D + 限位 | 2h |
| 4.9 | HTTP 通信桥接 | GrpcBridge 节点复用 | 2h |

**交付物**：可交互的 Godot 前端，Human 能完整操作一局游戏

---

### Sprint 5：AI 对抗 & 端到端闭环 (~3天)
**目标**：ScriptAI 适配三族 + Human vs AI 完整对局 + 胜负判定

| # | 任务 | 产出 | 预估 |
|---|------|------|------|
| 5.1 | ScriptAI 三族适配 | `agents/script_ai.py` — 三族建造序列+出兵逻辑 | 6h |
| 5.2 | Coordinator Agent 三族适配 | `agents/coordinator.py` — 分种族策略 | 4h |
| 5.3 | 胜负判定 + Game Over UI | 建筑全灭=负 + 神族特殊( Nexus/奴隶+建筑) | 3h |
| 5.4 | AI 自动注入 (HTTP Gateway) | P2 命令生成 + 合并 | 2h |
| 5.5 | 战斗视觉反馈 (攻击环/受击闪光/伤害飘字/子弹轨迹) | 粒子 + 动画 + 浮动文字 | 4h |
| 5.6 | make play 一键启动 | Makefile 更新 | 1h |
| 5.7 | E2E 冒烟测试 | `scripts/smoke_sc1.py` — 验证完整对局 | 2h |
| 5.8 | Benchmark: 100局 AI vs AI | `harness/benchmark.py` — 三族交叉对局 | 3h |

**交付物**：Human vs AI 可玩闭环 + AI vs AI benchmark

---

## 并行执行策略

```
时间轴: Day1─────Day3─────Day6─────Day9─────Day12────Day15

后端:  [Sprint0][Sprint1][Sprint2][Sprint3]
前端:                    [Sprint4]
集成:                              [Sprint5]
```

- Sprint 0-3 纯后端，可连续执行
- Sprint 4 前端在 Sprint 1-2 完成后即可开始（依赖通信层）
- Sprint 5 集成在 Sprint 3+4 完成后开始

## 关键风险

| 风险 | 缓解 |
|------|------|
| 原作 10FPS 逻辑迁移到 60FPS | SimCore 内部保持固定步长 tick (如 1/60s)，Godot 按帧插值渲染 |
| 无 A* 寻路导致单位卡墙 | Sprint 1 优先实现 A*，验收标准含绕障测试 |
| 三族特殊机制复杂（菌毯/水晶塔供电/附加建筑） | Sprint 2 分三族并行 agent 开发 |
| 25+ 技能实现工作量大 | Sprint 3 拆三族并行 agent 开发 |
| Godot 前端工作量与后端等量 | Sprint 4 专注交互核心，视觉用 Shape2D 占位 |

## 验收标准

1. 所有 44 单位 + 42 建筑 + 50+ 升级 + 25+ 技能配置数据完整
2. SimCore 确定性回放验证 (1000帧 0差异)
3. Human vs AI 可完整对局 (采矿→建造→出兵→战斗→胜负)
4. AI vs AI 100局 0崩溃
5. `make play` 一键启动