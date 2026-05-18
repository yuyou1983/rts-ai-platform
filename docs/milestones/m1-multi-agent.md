# M1 里程碑：多 Agent 协作架构

**周期**: 4 周
**状态**: ✅ **M1 已完成** (2026-05-14)
**前置**: M0 Startup

---

## 目标

将 M0 单体脚本 AI 拆分为 Coordinator + Economy + Combat 三核心架构，通过 MsgHub 黑板广播实现跨 Agent 态势共享，验证多 Agent 协同比单体脚本有竞争力。

## 核心交付物

| 交付物 | 负责人 | 优先级 | 验收标准 |
|--------|--------|--------|----------|
| AgentScope 兼容层 | 架构 | P0 | AgentBase/Msg/MsgHub 接口对齐，`RTAS_USE_REAL_AGENTSCOPE` 开关可用 |
| CoordinatorAgent | AI | P0 | 全局仲裁 + 资源预算分配 + 子 Agent 调度 + 命令去重 |
| EconomyAgent (AgentBase) | AI | P0 | 采集 + 建造 + 工人分配 + 供给管理 |
| CombatAgent (AgentBase) | AI | P0 | 集火 + 风筝 + 撤退 + 多线防守 |
| ScoutAgent | AI | P1 | 未知区域巡逻 + 残血撤退 |
| AgentScopeGameLoop | 架构 | P0 | SimCore → Msg → MsgHub → 多 Agent → 合并命令 → SimCore |
| MsgHub 端到端测试 | QA | P0 | 消息广播到所有参与者 |
| 对战验证 | QA | P0 | Coordinator vs ScriptAI 50 局，胜率 ≥ 50% |

## 完成总结

### 关键指标

| 指标 | M1 目标 | 实际达成 |
|------|---------|---------|
| 多 Agent 架构 | Coordinator + 2 子 Agent | ✅ Coordinator + Economy + Combat + Scout |
| MsgHub 广播 | 消息自动传播 | ✅ 同步/异步双模式 |
| 对战闭环 | Coordinator vs ScriptAI | ✅ 50 局 0 crash |
| Coordinator 胜率 | ≥ 50% | ✅ 60% (50局统计) |
| 测试覆盖 | ≥ 100 tests | ✅ 224 tests |
| TPS | ≥ 20 | ✅ 500+ TPS |

### 架构映射

```
Coordinator (全局仲裁)
├── EconomyAgent  → 采集/建造/工人分配 (SequentialPipeline)
├── CombatAgent   → 集火/风筝/撤退 (FanoutPipeline with Scout)
└── ScoutAgent    → 巡逻/侦察 (FanoutPipeline with Combat)
```

### 文件清单

| 文件 | 职责 |
|------|------|
| `agentscope_compat/__init__.py` | 兼容层入口，RTAS_USE_REAL_AGENTSCOPE 开关 |
| `agentscope_compat/_agent_base.py` | AgentBase (observe/reply) |
| `agentscope_compat/_msg.py` | Msg (name/content/role/metadata) |
| `agentscope_compat/_msghub.py` | MsgHub (广播/订阅黑板) |
| `agents/coordinator.py` | CoordinatorAgent — 仲裁 + 预算 + 去重 |
| `agents/economy.py` | EconomyAgent AgentBase 包装器 |
| `agents/combat.py` | CombatAgent AgentBase 包装器 |
| `agents/sub_agents.py` | Economy/Combat/Scout 核心逻辑 |
| `agents/game_loop.py` | AgentScopeGameLoop — SimCore↔MsgHub 桥接 |
| `agents/react_adapter.py` | ReactGameAgent — LLM ReAct 适配器（框架，待接真实 LLM） |

### 关键设计决策

1. **兼容层优先**: 不强制依赖 agentscope 完整包，轻量 compat 层即可跑通多 Agent
2. **Budget 仲裁**: Coordinator 按 phase 动态分配 mineral/gas 预算给子 Agent
3. **命令去重**: 同一 unit_id 的重复命令（build vs gather）按优先级取一
4. **同步包装器**: AgentBase.__call__ 自动包装 async reply，兼容 SimCore 同步步进

## 参考

- AgentScope 集成方案: `docs/architecture/agentscope-integration.md`
- Agent 协议设计: `docs/architecture/agent-protocols.md`