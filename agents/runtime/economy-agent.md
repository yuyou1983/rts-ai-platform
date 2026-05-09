---
name: economy-agent
type: runtime
version: m1
description: "M1 经济 Agent，采集优化、工人分配、供给管理。"
decision_hz: 5-10
protocols:
  observe: obs.econ.v1
  command: intent.econ.v1
---

# M1 经济 Agent

## 职责
1. 最优采集路径
2. 工人分配 (矿物/气体/建造/空闲)
3. 供给阻塞预警与解除
4. 扩张时机建议

## 核心指标
- 资源利用率 ≥ 85%
- 空闲工人数均值 ≤ 1
- 供给阻塞时长 ≤ 10s
