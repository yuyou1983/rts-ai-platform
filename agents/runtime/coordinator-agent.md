---
name: coordinator-agent
type: runtime
version: m1
description: "M1 协调器 Agent，黑板读写、子任务分发、冲突仲裁。"
decision_hz: 10
protocols:
  observe: obs.world.v1
  command: blackboard.write, task.assign
---

# M1 协调器 Agent

M0 阶段不存在独立 Coordinator，由 baseline-agent 单体处理。
M1 阶段拆分为三核心架构：Coordinator + Economy + Combat。

## 职责
1. 黑板维护 (全局状态摘要、活跃任务、资源预算)
2. 子 Agent 任务分发
3. 命令冲突仲裁 (按固定优先级)
4. 全局局势评估

## 仲裁规则
优先级: 战斗安全 > 供给阻塞 > 战略目标 > 侦察 > 低优扩建

## 黑板 Schema
```
Blackboard:
├── global_state: 局势评分 (0-100)
├── resource_budget: 各 Agent 资源配额
├── active_tasks: 活跃任务列表
├── intel: 情报汇总
└── decisions: 近期决策历史
```
