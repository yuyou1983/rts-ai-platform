# AgentScope 集成方案

> AgentScope 是阿里巴巴通义实验室开源的多 Agent 框架 (Apache-2.0, 24k+ stars)，
> 本文档描述如何将其整合到 RTS AI Native 平台的 AgentHub 层。

## 为什么选择 AgentScope

| 需求 | AgentScope 能力 | 对应 RTS 场景 |
|------|----------------|--------------|
| 多 Agent 编排 | MsgHub (消息广播/订阅) | Coordinator → Economy/Combat/Scout/Build |
| 流水线执行 | SequentialPipeline / FanoutPipeline | team-simcore/team-ai 编排 skill |
| 工具调用 | ReActAgent + Toolkit | 运行时 Agent 调用 SimCore cmd 协议 |
| 异步高并发 | 全异步架构 (async/await) | 32-64 局并发仿真 |
| RL 训练集成 | Trinity-RFT + tuner 模块 | PPO/IMPALA 策略梯度训练闭环 |
| A2A 协议 | 内置 A2A Agent 支持 | 跨系统 Agent 互操作 |
| 结构化输出 | Pydantic BaseModel 支持 | 战斗公式/经济模型的结构化推理 |
| 内存管理 | InMemory / LongTermMemory | Agent 决策历史 + 战场态势黑板 |

## 架构映射

```
RTS 四层架构                    AgentScope 对应模块
─────────────                  ──────────────────
SimCore (仿真内核)              外部环境 (通过 gRPC 桥接)
  │                              │
  │ obs/cmd 协议                  │ Msg 对象
  ▼                              ▼
AgentHub (Agent运行层)          ┌─────────────────┐
  ├── Coordinator               │ MsgHub            │ ← 广播/订阅黑板
  ├── Economy                   │   + participants  │
  ├── Combat                    │   + announcement  │
  ├── Strategy                  │   + broadcast()   │
  ├── Scout                     └─────────────────┘
  └── Build                     ┌─────────────────┐
                                │ Pipeline          │ ← 流水线编排
Harness (训练验证层)             │   SequentialPipeline
  ├── MatchScheduler            │   FanoutPipeline  │
  ├── SimulationPool            └─────────────────┘
  ├── PromotionGate             ┌─────────────────┐
  └── ReplayParser              │ ReActAgent        │ ← 推理-行动循环
                                │   + Toolkit       │ ← 注册 SimCore cmd
Pipeline (工具链层)             │   + Memory        │ ← 决策历史
                                │   + structured_model│ ← 结构化输出
                                └─────────────────┘
                                ┌─────────────────┐
                                │ Tuner            │ ← RL 训练
                                │   + Trinity-RFT  │ ← Agentic RL
                                │   + judge         │ ← 自动评估
                                └─────────────────┘
```

## RTS 运行时 Agent 实现

### M0: BaselineAgent (单体脚本)

```python
from agentscope.agent import ReActAgent
from agentscope.model import OpenAIChatModel
from agentscope.memory import InMemoryMemory
from agentscope.tool import Toolkit

# 将 SimCore cmd 协议注册为工具
toolkit = Toolkit()
toolkit.register_tool_function(send_move_command)
toolkit.register_tool_function(send_attack_command)
toolkit.register_tool_function(send_build_command)

baseline = ReActAgent(
    name="baseline-agent",
    sys_prompt="你是 M0 基线 AI，执行采集-生产-进攻-防守循环。决策频率 10Hz。",
    model=OpenAIChatModel(model_name="qwen-max", ...),
    memory=InMemoryMemory(),
    toolkit=toolkit,
)
```

### M1: 三核心 MsgHub 编排

```python
from agentscope.agent import ReActAgent
from agentscope.pipeline import MsgHub, sequential_pipeline

coordinator = ReActAgent(name="coordinator", ...)
economy = ReActAgent(name="economy", ...)
combat = ReActAgent(name="combat", ...)

async def run_m1_tick(obs_msg: Msg):
    """M1 三核心单 tick 执行"""
    # MsgHub 实现黑板广播 — 每个Agent的回复自动广播给其他参与者
    async with MsgHub(
        participants=[coordinator, economy, combat],
        announcement=obs_msg,  # 当前 tick 的世界观察
    ) as hub:
        # 1. Coordinator 先做全局仲裁
        await coordinator()

        # 2. Economy 和 Combat 并行决策
        await fanout_pipeline([economy, combat])

        # 结果自动广播回 SimCore
```

### M2: 全 Agent + League

```python
agents = [coordinator, economy, combat, strategy, scout, build]

async with MsgHub(participants=agents, announcement=obs_msg) as hub:
    # Coordinator 仲裁 + 战术分配
    await coordinator()

    # Economy/Build 顺序执行（资源竞争）
    await sequential_pipeline([economy, build])

    # Combat/Scout 并行执行（互不阻塞）
    await fanout_pipeline([combat, scout])

    # Strategy 低频规划（每 5 tick 执行一次）
    if tick % 5 == 0:
        await strategy()
```

## RL 训练闭环

AgentScope 的 Trinity-RFT 集成为 M1+ 的策略训练提供了关键能力：

```
                   ┌──────────────────────┐
                   │   AgentScope Tuner    │
                   │  ┌────────────────┐  │
SimCore ←─gRPC──→ │  │ Trinity-RFT    │  │ ← PPO/IMPALA 策略梯度
  ↑  ↓            │  │ + Agent Replay │  │
  │  │             │  │ + Auto Judge  │  │
  │  └─────────────│──└────────────────┘  │
  │                └──────────────────────┘
  │                         │
  └──── MLflow Tracking ────┘
```

- **Trinity-RFT**: AgentScope 内置的 Agentic RL 框架，支持在线/离线训练
- **Auto Judge**: 用 LLM-as-a-judge 自动生成奖励信号（无需手工 reward shaping）
- **Werewolf 先例**: AgentScope 已验证多 Agent 游戏的 RL 训练（狼人杀胜率 50% → 80%）

## 研发侧 Agent 编排

研发侧的 team-* skill 也可以用 AgentScope 的 Pipeline 编排：

```python
# team-simcore: 新规则子系统开发
from agentscope.pipeline import sequential_pipeline, fanout_pipeline

async def team_simcore(subsystem: str):
    # Phase 1: 系统设计（顺序 — 设计依赖分析）
    design = await sequential_pipeline([systems_designer])

    # Phase 2: 实现 + 数据并行
    await fanout_pipeline([simcore_engineer, data_engineor])

    # Phase 3: 测试验证
    await sequential_pipeline([test_orchestrator])
```

## 与 SimCore 的桥接

AgentScope 运行在 Python 进程中，SimCore 也是 Python，因此可以零开销直连：

```python
# 方案 A: 进程内直连 (M0 推荐，零延迟)
from simcore import SimCore
simcore = SimCore(seed=42, map="lost_temple")

# 方案 B: gRPC 桥接 (M1+ 推荐，支持分布式)
from agentscope.tool import Toolkit
toolkit = Toolkit()

# 将 SimCore 的 cmd 协议注册为 Agent 工具
@toolkit.register_tool
async def sim_send_commands(commands: MicroCommands) -> None:
    """向 SimCore 发送微操命令"""
    await grpc_stub.SendCommands(commands)

@toolkit.register_tool
async def sim_observe(protocol: str) -> Msg:
    """从 SimCore 获取观察"""
    obs = await grpc_stub.Observe(protocol)
    return Msg(name="simcore", content=obs, role="tool")
```

## 依赖

```toml
[project.optional-dependencies]
agentscope = ["agentscope>=2.0"]
```

AgentScope 基础依赖较轻（openai, pydantic, shortuuid, tiktoken 等），
不会与 SimCore 的 numpy/torch 产生冲突。

## 参考

- AgentScope 代码: `~/code/agentscope`
- [AgentScope 论文 v1](https://arxiv.org/abs/2402.14034)
- [AgentScope 论文 v2](https://arxiv.org/abs/2508.16279)
- [Trinity-RFT](https://github.com/agentscope-ai/Trinity-RFT)
- [狼人杀示例](https://github.com/agentscope-ai/agentscope/tree/main/examples/game/werewolves)