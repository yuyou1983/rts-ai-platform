# RTS AI Native 游戏研发平台

> AI Native RTS 游戏研发平台 - 从第一天起就把平台拆成四个互相解耦但数据闭环的平面

## 项目概述

本项目旨在构建一个**可训练仿真内核 SimCore、运行时与研发侧 AgentHub、训练与验证 Harness、内容与发布工具链 Pipeline** 的统一载体。

核心目标：**不是先追求 3D 表现，而是先完成 2D headless 可训练、可回放、可批量仿真、可自动测试的 RTS 战斗沙盒**。

## 项目结构

```
rts-ai-platform/
├── agents/                    # Agent 配置
│   ├── runtime/              # 运行时 Agent (游戏内实时决策)
│   │   ├── rts-coordinator/  # 中央协调器
│   │   ├── rts-combat/       # 战斗/微操
│   │   ├── rts-economy/      # 经济/采集
│   │   ├── rts-strategy/     # 宏观战略
│   │   ├── rts-scout/        # 侦察/情报
│   │   └── rts-build/        # 建造/科技
│   └── dev/                   # 研发侧 Agent (开发流程自动化)
│       ├── rts-test-orchestrator/  # 测试编排
│       ├── rts-balance/            # 平衡性分析
│       ├── rts-design-assistant/   # 策划辅助
│       └── rts-replay-analyzer/    # 回放分析
├── docs/                      # 文档
│   ├── architecture/          # 架构设计
│   ├── protocols/             # 协议文档
│   └── milestones/            # 里程碑计划
├── protocols/                  # 协议定义
│   ├── obs/                   # 观察协议
│   └── cmd/                   # 命令协议
├── src/                       # Godot 游戏源码 (GDScript/C#/GDExtension)
├── simcore/                   # Python Headless SimCore (训练用)
└── scripts/                   # 工具脚本
```

## 里程碑

| 阶段 | 周期 | 核心目标 |
|------|------|----------|
| M0 | 6 周 | 规则、回放、build、基线 AI、数据埋点闭环 |
| M1 | 10 周 | 产品玩法、训练线路、工具链参数化加深 |
| M2 | 20 周 | 3D 产品化垂直切片 + 可灰度 AI 发布机制 |

## Agent 体系

### 运行时 Agent (游戏内)

| Agent | 优先级 | 决策频率 | 核心职责 |
|-------|--------|----------|----------|
| rts-coordinator | P0 | 10 Hz | 统一调度、冲突仲裁 |
| rts-combat | P0 | 10-20 Hz | 集火、风筝、撤退 |
| rts-economy | P0 | 5-10 Hz | 采集、工人分配 |
| rts-strategy | P0 | 1-2 Hz | 开局路线、攻守切换 |
| rts-scout | P1 | 1-2 Hz | 侦察路径、情报收集 |
| rts-build | P1 | 2-5 Hz | 建造、科技队列 |

### 研发侧 Agent (开发流程)

| Agent | 优先级 | 核心职责 |
|-------|--------|----------|
| rts-test-orchestrator | P0 | 测试矩阵生成、Harness 调度 |
| rts-balance | P1 | 平衡性分析、强弱曲线拟合 |
| rts-design-assistant | P1 | 策划配置生成 |
| rts-replay-analyzer | P1 | 战报生成、失误归因 |

## 技术栈

- **引擎**: Godot 4.4.1 (前端表现 + Dedicated Server) / Python Headless SimCore (训练)
- **Agent 框架**: [AgentScope](https://github.com/agentscope-ai/agentscope) — 运行时多 Agent 编排
- **训练框架**: PPO / IMPALA / V-trace (Python，直连 SimCore)
- **实验追踪**: MLflow Tracking + Model Registry
- **版本控制**: Git + Git LFS (资产)
- **协议**: Protobuf + gRPC

## 快速开始

```bash
# 进入项目目录
cd ~/code/rts-ai-platform

# 查看 Agent 配置
ls agents/runtime/
ls agents/dev/

# 查看协议定义
ls protocols/
```

## 参考资料

- [AlphaStar Nature 论文](https://www.nature.com/articles/s41586-019-1724-z)
- [SC2LE 论文](https://arxiv.org/abs/1708.04782)
- [SMACv2 论文](https://arxiv.org/abs/2212.07489)
- [Godot Engine](https://godotengine.org/)
- [MLflow](https://mlflow.org/)