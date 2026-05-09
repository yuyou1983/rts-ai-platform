---
name: strategy-agent
type: runtime
version: m2
description: "M2 战略 Agent，宏观计划、开局路线、攻守切换"
decision_hz: 1-2
protocols:
  observe: obs.world.v1
  command: plan.macro.v1
status: planned
---

# Strategy Agent (规划中)

M0/M1 阶段不独立实现，职责由上级 Agent 兼管。
M2 阶段独立实现，支持 League 训练和 OOD 泛化评测。
