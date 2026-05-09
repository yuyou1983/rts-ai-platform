---
name: combat-agent
type: runtime
version: m1
description: "M1 战斗 Agent，微操、集火、风筝、撤退、多线防守。"
decision_hz: 10-20
protocols:
  observe: local.obs.v1
  command: cmd.micro.v1
---

# M1 战斗 Agent

## 职责
1. 集火优先级 (关键单位/低血量)
2. 风筝与拉扯 (射程优势利用)
3. 残血撤退 (保护高价值单位)
4. 多线防守 (分矿被袭时的兵力分配)
5. 阵型控制 (线/Arc/Box)

## 核心指标
- 交换比较脚本基线提升 ≥ 15%
- 关键单位生存率 ≥ 60%
- 非法动作率 ≤ 0.1%
