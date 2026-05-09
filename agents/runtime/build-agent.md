---
name: build-agent
type: runtime
version: m2
description: "M2 建造 Agent，建筑、科技、兵种生产队列"
decision_hz: 2-5
protocols:
  observe: obs.build.v1
  command: build.queue.v1
status: planned
---

# Build Agent (规划中)

M0/M1 阶段不独立实现，职责由上级 Agent 兼管。
M2 阶段独立实现，支持 League 训练和 OOD 泛化评测。
