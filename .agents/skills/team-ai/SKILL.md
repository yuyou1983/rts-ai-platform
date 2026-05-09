---
name: team-ai
description: "编排 AI 开发团队：协调 rts-systems-designer (行为设计) + rts-ai-engineer (Agent 实现) + rts-data-engineer (训练数据) + rts-test-orchestrator (评测) 端到端完成一个 AI 功能。"
argument-hint: "[ai-feature: baseline|economy|combat|league]"
user-invocable: true
---

当此 skill 被调用时，编排 AI 开发团队通过结构化流水线。

## 团队组成
- **rts-systems-designer** — 设计行为规则、评估指标
- **rts-ai-engineer** — 实现 Agent 行为树/策略网络
- **rts-data-engineer** — 准备训练数据、标注管线
- **rts-test-orchestrator** — 编排评测、A/B 测试
- **rts-balance-analyst** — 分析平衡影响

## 流水线

### Phase 1: 行为设计
委派给 **rts-systems-designer**:
- 定义 Agent 的行为规范
- 定义评估指标和通过标准
- 输出: 行为规范文档

### Phase 2: Agent 实现
委派给 **rts-ai-engineer**:
- 实现行为树/状态机/策略网络
- 集成到 AgentHub
- 输出: Agent 代码

### Phase 3: 训练数据 (如需学习型策略)
委派给 **rts-data-engineer**:
- 准备模仿学习数据
- 标注训练样本
- 输出: 训练数据集

### Phase 4: 评测
委派给 **rts-test-orchestrator**:
- 生成对战矩阵
- 运行 Harness 评测
- A/B 对比基线

### Phase 5: 平衡评估
委派给 **rts-balance-analyst**:
- 分析胜率、ELO、交换比
- 识别对其他 Agent 的影响

每个阶段转换时需要用户审批。
