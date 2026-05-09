---
name: scout-agent
type: runtime
version: m2
description: "M2 侦察 Agent，视野覆盖、敌方 tech 识别、威胁评估"
decision_hz: 1-2
protocols:
  observe: obs.fow.v1
  command: intel.report.v1
status: planned
---

# Scout Agent (规划中)

M0/M1 阶段不独立实现，职责由上级 Agent 兼管。
M2 阶段独立实现，支持 League 训练和 OOD 泛化评测。
