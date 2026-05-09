# RTS AI Native 平台 -- Game AI Agent Architecture

AI Native RTS 游戏研发平台，由多层 Agent 体系驱动。

## 技术栈

- **引擎**: Godot 4.4.1 (前端表现 + Dedicated Server) / Python Headless SimCore (训练)
- **语言**: GDScript (游戏逻辑/场景/UI) / C# (可选) / C++/Rust (GDExtension 性能热点) / Python (训练)
- **Agent 框架**: [AgentScope](https://github.com/agentscope-ai/agentscope) — 运行时多 Agent 编排 (MsgHub, Pipeline, ReAct)
- **训练框架**: PPO / IMPALA / V-trace (Python，直连 SimCore)
- **实验追踪**: MLflow Tracking + Model Registry
- **版本控制**: Git + Git LFS (资产)
- **协议**: Protobuf + gRPC

> **Note**: 平台包含运行时 Agent (游戏内决策) 和研发侧 Agent (开发自动化)。
> 运行时 Agent 使用 AgentScope 框架编排 (MsgHub 广播 + Pipeline 流水线 + ReAct 推理)。
> 研发侧 Agent 参考 claude-game-studios 的工业级实践：领导层 + 职能专家层 + 编排 skill。
> 引擎专家使用 Godot 系列 Agent (godot-specialist + 3 个子专家)。

## 项目结构

@.claude/docs/directory-structure.md

## 架构参考

@docs/architecture/four-layers.md

## 协调规则

@.claude/docs/coordination-rules.md

## 协作协议

**用户驱动协作，非自主执行。**
每个任务遵循: **问题 -> 选项 -> 决策 -> 草案 -> 批准**

- Agent 必须在写入文件前询问 "我可以写入 [filepath] 吗？"
- Agent 必须在请求批准前展示草案或摘要
- 多文件变更需要完整变更集的明确批准
- 未经用户指示不提交代码

## Agent 体系

### 层级 1: 领导层 (战略决策与冲突仲裁)

| Agent | Model | 核心职责 | Skills |
|-------|-------|----------|--------|
| rts-technical-director | opus | 架构决策、技术选型、跨系统冲突 | architecture-decision, tech-debt, gate-check |
| rts-producer | opus | 里程碑、Sprint、范围控制、协调 | sprint-plan, scope-check, estimate, milestone-review |
| rts-creative-director | opus | 游戏愿景、玩法调性、创意仲裁 | brainstorm, design-review |

### 层级 2: 职能专家层 (垂直领域实施)

| Agent | Model | 核心职责 | Skills |
|-------|-------|----------|--------|
| rts-simcore-engineer | sonnet | 规则引擎、状态管理、回放、协议 | code-review, architecture-decision |
| rts-ai-engineer | sonnet | AgentHub、行为树/RL、推理优化 | code-review, balance-check |
| rts-systems-designer | sonnet | 战斗公式、经济模型、克制矩阵 | design-review, balance-check, brainstorm |
| rts-data-engineer | sonnet | 遥测、回放解析、MLflow、ETL | code-review, replay-analyze |
| rts-devops | haiku | CI/CD、仿真池、构建、灰度发布 | code-review |
| rts-balance-analyst | sonnet | 胜率、ELO、强弱曲线、OP/UP | balance-check, replay-analyze |
| rts-test-orchestrator | sonnet | Test Matrix、Harness、A/B、回滚 | test-matrix, harness-run, gate-check |
| rts-design-assistant | sonnet | 配置草案、Patch Diff、GDD | design-review, brainstorm |
| rts-replay-analyst | sonnet | 战报、失误归因、训练标注 | replay-analyze, balance-check |

### 层级 3: 编排 Skill (多 Agent 协作流水线)

| Skill | 编排团队 | 触发场景 |
|-------|----------|----------|
| team-simcore | systems-designer → simcore-engineer → data-engineer → test-orchestrator | 新规则/状态/回放子系统开发 |
| team-ai | systems-designer → ai-engineer → data-engineer → test-orchestrator → balance-analyst | 新 Agent/训练/评测 |
| team-balance | balance-analyst → systems-designer → design-assistant → test-orchestrator | 平衡补丁 |
| team-release | producer → test-orchestrator → devops → data-engineer | 版本发布 |

### 运行时 Agent (游戏内实时决策)

#### M0: 单体基线 (当前)

| Agent | 决策频率 | 协议 | 核心职责 |
|-------|----------|------|----------|
| baseline-agent | 10 Hz | obs.world.v1 → cmd.micro.v1 | 采集-生产-进攻-防守 |

#### M1: 三核心 (规划)

| Agent | 决策频率 | 协议 | 核心职责 |
|-------|----------|------|----------|
| coordinator-agent | 10 Hz | blackboard, task.assign | 仲裁 + 黑板 |
| economy-agent | 5-10 Hz | obs.econ.v1 → intent.econ.v1 | 采集/工人/供给 |
| combat-agent | 10-20 Hz | local.obs.v1 → cmd.micro.v1 | 微操/集火/风筝 |

#### M2: 全 Agent (规划)

| Agent | 决策频率 | 协议 | 核心职责 |
|-------|----------|------|----------|
| strategy-agent | 1-2 Hz | obs.world.v1 → plan.macro.v1 | 宏观战略 |
| scout-agent | 1-2 Hz | obs.fow.v1 → intel.report.v1 | 侦察/情报 |
| build-agent | 2-5 Hz | obs.build.v1 → build.queue.v1 | 建造/科技 |

## 里程碑

| 阶段 | 周期 | 核心目标 |
|------|------|----------|
| M0 | 6 周 | 规则、回放、build、基线 AI、数据埋点闭环 |
| M1 | 10 周 | 产品玩法、训练线路、工具链参数化 |
| M2 | 20 周 | 3D 产品化 + AI 发布机制 |

## 编码标准

@.claude/docs/coding-standards.md

## 上下文管理

@.claude/docs/context-management.md
