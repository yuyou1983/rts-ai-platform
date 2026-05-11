# RTS AI Platform — AI Native RTS 游戏研发平台

> 确定性 headless 仿真内核 + 多 Agent 对抗 + Godot 可视化前端 + RL 训练闭环

## 项目概述

RTS AI Platform 是一个**从头为 AI 训练设计的**即时战略游戏研发平台。核心思路：先完成 2D headless 可训练、可回放、可批量仿真、可自动测试的 RTS 战斗沙盒，再逐步叠加 3D 表现层。

平台由四个解耦但数据闭环的平面组成：

| 平面 | 职责 |
|------|------|
| **SimCore** | 确定性 Python 仿真内核，支持 headless 批量运行、回放、Gym 环境封装 |
| **AgentHub** | 多 Agent 运行时编排（Coordinator → Economy/Combat/Scout/SubAgents） |
| **Harness** | 批量对局、benchmark、遥测、训练池 |
| **Godot** | HTTP 可视化前端，Human vs AI 交互 |

## 核心功能

### 仿真内核 (SimCore)
- **确定性 tick 仿真**：相同种子 → 逐帧一致，支持完整回放
- **完整 RTS 规则**：移动/采集/建造/训练/攻击/自动攻击/战争迷雾
- **gym.Env 封装**：`SimCoreGymEnv`，标准 `step/reset`，可直连 RL 训练
- **gRPC + HTTP 双协议**：`SimCoregRPCServer` + `HTTPGateway`，支持前后端分离

### 多 Agent 体系 (AgentHub)
- **Coordinator**：中央调度，分配任务给子 Agent，胜率 ~60%
- **EconomyAgent**：工人分配、资源采集、建造决策
- **CombatAgent**：集结进攻、防御响应、集火目标选择
- **ScoutAgent**：基于迷雾覆盖率的智能侦察路径规划
- **ScriptAI**：基线脚本 AI，单文件完整博弈逻辑
- **SubAgents**：可组合的细粒度子策略（骚扰、防守、扩张等）

### 可视化前端 (Godot 4.6)
- **Human P1 vs AI P2**：WASD 移镜头、左键框选、右键移动/攻击
- **战争迷雾**：per-player 三态渲染（Unexplored/Explored/Visible）
- **小地图**：点击跳转镜头，实体颜色标记
- **战斗视觉**：攻击脉冲环、受击闪光、伤害飘字
- **完整闭环**：Game Over 判定 + R 重开 + Q 退出

### 训练与 Harness
- **批量对局**：`HarnessPool` 多进程并行
- **Benchmark**：100 局自动对局，胜率/平均时长/崩溃率统计
- **遥测**：`TelemetryCollector` 事件记录 + CSV 导出
- **GRPO 训练**：`train/` 下集成 TRL GRPO 微调管线

## 架构设计

```
┌──────────────────────────────────────────────────────┐
│                    Godot 4.6 前端                      │
│  game_view.gd · grpc_bridge.gd · fog_renderer.gd      │
│  HTTPRequest → /api/step → JSON state → 2D Canvas      │
└──────────────┬───────────────────────────────────────┘
               │ HTTP (localhost:8080)
┌──────────────▼───────────────────────────────────────┐
│                 HTTP Gateway (async)                    │
│  /api/start_game · /api/step · /api/get_state          │
│  自动注入 AI P2 命令 · 返回全部实体给前端              │
└──────────────┬───────────────────────────────────────┘
               │ gRPC (localhost:50051)
┌──────────────▼───────────────────────────────────────┐
│              SimCore gRPC Server                       │
│  StartGame · Step · GetState · StreamState             │
└──────────────┬───────────────────────────────────────┘
               │
┌──────────────▼───────────────────────────────────────┐
│              SimCore Engine                            │
│  RuleEngine.apply() → validate → move → combat        │
│  → gather → construct → fog → terminal check           │
└──────────────────────────────────────────────────────┘
```

**数据流（每 tick）**：
1. Godot 发送 P1 命令 → HTTPGateway `/api/step`
2. Gateway 自动调用 `ScriptAI` 生成 P2 命令，合并
3. 合并命令通过 gRPC 发送到 SimCore Server
4. Server 执行 `RuleEngine.apply()`，返回快照
5. Gateway 序列化为 JSON 返回 Godot
6. Godot 解析并渲染（实体 + 迷雾 + HUD + 战斗效果）

## 项目结构

```
rts-ai-platform/
├── simcore/                    # 仿真内核
│   ├── engine.py              # SimCore 主类，step/run/replay
│   ├── rules.py               # RuleEngine：validate → move → combat → gather → construct → fog
│   ├── state.py               # GameState + get_observations（per-player 迷雾过滤）
│   ├── entities.py            # Entity/Unit/Building/Resource 数据类
│   ├── mapgen.py              # 程序化地图生成（矿/气/出生点）
│   ├── replay.py              # 回放序列化/反序列化
│   ├── gym_env.py             # gym.Env 封装
│   ├── grpc_server.py         # gRPC 服务端
│   ├── grpc_client.py          # gRPC 客户端
│   ├── http_gateway.py        # HTTP REST 网关（Godot → gRPC）
│   └── proto_out/             # 编译后的 protobuf 文件
├── agents/                     # 多 Agent 体系
│   ├── coordinator.py         # 中央协调器
│   ├── economy.py             # 经济 Agent
│   ├── combat.py              # 战斗 Agent
│   ├── sub_agents.py          # 子 Agent（Scout/Build/Defend/Harass）
│   ├── script_ai.py           # 基线脚本 AI
│   ├── game_loop.py           # Agent 游戏循环
│   └── react_adapter.py       # ReAct 适配器
├── harness/                    # Harness 批量测试
│   ├── benchmark.py           # 对局 benchmark
│   ├── pool.py                # 多进程并行池
│   ├── telemetry.py           # 遥测收集
│   └── devops_harness/        # DevOps harness 工具链
├── train/                      # RL 训练
│   └── test_grpo.py           # GRPO 训练测试
├── godot/                      # Godot 4.6 前端
│   ├── scripts/
│   │   ├── game_view.gd       # 主渲染 + 输入 + HUD + 战斗效果
│   │   ├── grpc_bridge.gd     # HTTP 通信桥接
│   │   ├── fog_renderer.gd    # 迷雾三态渲染
│   │   └── minimap_rect.gd    # 小地图
│   ├── scenes/                 # Godot 场景文件
│   └── project.godot
├── proto/                      # Protobuf 协议定义
│   ├── state.proto            # GameState 快照（含 attack_target_id/target_x/target_y）
│   ├── cmd.proto              # 命令协议
│   ├── obs.proto              # 观察协议
│   └── service.proto          # gRPC 服务定义
├── tests/                      # 测试套件（125 tests）
├── scripts/                    # 工具脚本
│   ├── smoke_mvp.py           # MVP 冒烟测试
│   └── test_e2e_godot_flows.py # 端到端流程测试
├── docs/                       # 文档
│   └── milestones/            # 里程碑文档
└── Makefile                    # 构建与运行入口
```

## 快速开始

### 环境要求

- Python 3.11+
- Godot 4.6+（macOS/Linux）
- gRPC 依赖：`pip install grpcio grpcio-tools`

### 安装

```bash
cd ~/code/rts-ai-platform
make build          # 编译 protobuf + 安装依赖
```

### 运行方式

#### 1. Human vs AI（MVP 推荐）

```bash
make play           # 一键启动：gRPC server + HTTP gateway + Godot
```

启动后在 Godot 中按 **F5** 运行游戏。

| 操作 | 按键 |
|------|------|
| 移动镜头 | WASD |
| 框选单位 | 左键拖拽 |
| 追加选择 | Shift + 左键 |
| 取消选择 | Esc |
| 移动/采集/攻击 | 右键 |
| 建造兵营 | 按住 B + 右键 |
| 训练单位 | T（选中基地→工人，选中兵营→士兵） |
| 重开游戏 | R（Game Over 后） |
| 退出 | Q（Game Over 后） |
| 小地图跳转 | 左键点击小地图 |

> 右键空地时：士兵自动攻击最近敌人，工人移动到目标点

#### 2. Headless 对局

```bash
make sim            # 默认 seed=42，baseline vs baseline
make smoke-test     # 验证对局能正常结束
```

#### 3. 批量 Benchmark

```bash
python -m harness.benchmark --games 100 --ai coordinator vs script_ai
```

#### 4. RL 训练（Gym 环境）

```python
from simcore.gym_env import SimCoreGymEnv

env = SimCoreGymEnv()
obs, info = env.reset()
for _ in range(1000):
    action = agent.act(obs)
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated:
        obs, info = env.reset()
```

### 停止服务

```bash
make stop           # 清理所有后台进程
```

### 运行测试

```bash
make test           # 125 tests, 4 xdist workers
make smoke-test-mvp # MVP 端到端冒烟验证
```

## 里程碑与更新日志

### M0 — 平台骨架 (2026-04)
- 项目架构搭建，四平面解耦设计
- Python 仿真内核骨架（Entity/GameState/RuleEngine）
- gRPC 协议定义（state/cmd/obs/service）
- Godot 项目初始化

### M1 — 规则闭环 (2026-05 初)
- 完整 RTS 规则实现：移动、采集、建造、训练、攻击、自动攻击
- 程序化地图生成（矿/气/出生点对称）
- 确定性回放验证（463 帧 0 差异）
- 基线 ScriptAI 实现
- 118 tests 全过

### M2 — 可视化 + 训练 (2026-05 中)
- **Phase 1**：HTTP Gateway，Godot ↔ SimCore 数据通路打通
- **Phase 2**：训练基础设施（HarnessPool、Benchmark、Telemetry、GRPO 管线）
- **Phase 3**：视觉打磨，100 局 benchmark 验证（0 崩溃，Coordinator 60% 胜率）

### M3 — 战斗原型 / MVP (2026-05-11) ✅
- **Human P1 vs AI P2** 完整闭环
- 攻击命令修复（Proto 补 attack_target_id/target_x/target_y 字段）
- 战争迷雾 per-player 三态渲染
- 小地图点击跳转镜头
- 战斗视觉反馈：攻击脉冲环、受击闪光、伤害飘字
- 右键智能交互：点击敌人攻击、空地自动寻敌
- HUD 增强：选中建筑类型 + 训练提示（T→Worker(50$)/T→Soldier(100$)）
- Game Over 判定 + R 重开 + Q 退出
- 一键启动 `make play` / `make stop`
- 冒烟测试 `make smoke-test-mvp`
- **125 tests 全过**

## Agent 体系

### 运行时 Agent（游戏内实时决策）

| Agent | 决策频率 | 核心职责 |
|-------|---------|----------|
| Coordinator | 10 Hz | 统一调度、任务分配、冲突仲裁 |
| EconomyAgent | 5-10 Hz | 采集、工人分配、建造优先级 |
| CombatAgent | 10-20 Hz | 集结进攻、防御响应、撤退决策 |
| ScoutAgent | 1-2 Hz | 迷雾驱动侦察路径、情报收集 |
| SubAgents | 2-10 Hz | 骚扰/防守/扩张/建造等子策略 |

### 研发侧 Agent（开发流程自动化）

| Agent | 核心职责 |
|-------|----------|
| Test Orchestrator | 测试矩阵生成、Harness 调度 |
| Balance Analyzer | 平衡性分析、强弱曲线拟合 |
| Design Assistant | 策划配置生成 |
| Replay Analyzer | 战报生成、失误归因 |

## 技术栈

| 层面 | 技术 |
|------|------|
| 仿真内核 | Python 3.11, 确定性 tick, gRPC |
| Agent 框架 | AgentScope 多 Agent 编排 |
| 训练框架 | TRL (GRPO), Gymnasium |
| 实验追踪 | MLflow Tracking |
| 前端引擎 | Godot 4.6 (GDScript, HTTPRequest) |
| 协议 | Protobuf 3 + gRPC + REST/JSON |
| 测试 | pytest + xdist, 125 tests |
| 代码质量 | ruff + mypy |
| 版本控制 | Git + GitHub |

## 参考资料

- [AlphaStar Nature 论文](https://www.nature.com/articles/s41586-019-1724-z)
- [SC2LE 论文](https://arxiv.org/abs/1708.04782)
- [SMACv2 论文](https://arxiv.org/abs/2212.07489)
- [Godot Engine](https://godotengine.org/)
- [AgentScope](https://github.com/agentscope-ai/agentscope)
- [TRL - Transformer Reinforcement Learning](https://github.com/huggingface/trl)
- [MLflow](https://mlflow.org/)

## License

MIT