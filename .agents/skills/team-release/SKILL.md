---
name: team-release
description: "编排发布团队：协调 rts-producer (Go/No-Go) + rts-test-orchestrator (质量门) + rts-devops (构建/部署) + rts-data-engineer (数据回流) 完成发布流程。"
argument-hint: "[version or 'next']"
user-invocable: true
---

当此 skill 被调用时，编排发布团队。

## 团队组成
- **rts-producer** — Go/No-Go 决策、范围确认
- **rts-test-orchestrator** — 质量门控、回归测试
- **rts-devops** — 构建、部署、灰度
- **rts-data-engineer** — 数据回流验证

## 流水线

### Phase 1: 发布计划
委派给 **rts-producer**:
- 确认里程碑验收标准全部满足
- 确认延期范围项
- 输出: 发布授权

### Phase 2: 质量门控
委派给 **rts-test-orchestrator**:
- 运行完整回归测试
- 检查所有质量门控
- 输出: 质量报告

### Phase 3: 构建
委派给 **rts-devops**:
- 生成 release candidate 构建
- 签名、存档
- 输出: 构建 artifact

### Phase 4: 灰度发布
委派给 **rts-devops** + **rts-data-engineer**:
- Shadow → Staging → Canary → Promote
- 监控数据回流
- 输出: 发布结果

每个阶段转换时需要用户审批。
