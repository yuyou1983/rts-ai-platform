---
name: team-balance
description: "编排平衡调整团队：协调 rts-balance-analyst (数据分析) + rts-systems-designer (补丁设计) + rts-design-assistant (配置生成) + rts-test-orchestrator (验证) 端到端完成一个平衡补丁。"
argument-hint: "[balance-issue: unit-OP|map-bias|economy-stall|meta-stale]"
user-invocable: true
---

当此 skill 被调用时，编排平衡调整团队。

## 团队组成
- **rts-balance-analyst** — 数据分析，量化问题
- **rts-systems-designer** — 设计补丁方案
- **rts-design-assistant** — 生成配置 diff
- **rts-test-orchestrator** — 验证补丁效果

## 流水线

### Phase 1: 问题量化
委派给 **rts-balance-analyst**:
- 收集大规模对局数据
- 计算胜率矩阵、ELO、交换比
- 识别统计显著的偏离
- 输出: 问题报告 + 建议方向

### Phase 2: 补丁设计
委派给 **rts-systems-designer**:
- 设计 2-3 个补丁方案
- 每个方案解释 WHY 和预期影响
- 输出: 补丁设计文档

### Phase 3: 配置生成
委派给 **rts-design-assistant**:
- 根据选定方案生成配置 diff
- 生成 patch notes 草稿
- 输出: 配置变更 + patch notes

### Phase 4: 补丁验证
委派给 **rts-test-orchestrator**:
- 用补丁前后对比的测试矩阵
- 验证胜率回归到目标范围
- 验证无副作用
- 输出: Go/No-Go 报告

每个阶段转换时需要用户审批。
