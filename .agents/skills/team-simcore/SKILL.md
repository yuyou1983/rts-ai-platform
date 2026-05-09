---
name: team-simcore
description: "编排仿真内核开发团队：协调 rts-systems-designer (规则设计) + rts-simcore-engineer (规则实现) + rts-data-engineer (回放/遥测) + rts-test-orchestrator (验证) 端到端完成一个 SimCore 子系统。"
argument-hint: "[subsystem: combat|economy|tech|movement|replay]"
user-invocable: true
---

当此 skill 被调用时，编排仿真内核团队通过结构化流水线。

## 团队组成
- **rts-systems-designer** — 设计公式、规则、边界情况
- **rts-simcore-engineer** — 实现规则引擎、状态管理、命令处理
- **rts-data-engineer** — 实现回放录制、遥测采集、特征提取
- **rts-test-orchestrator** — 生成测试矩阵、验证确定性

## 流水线

### Phase 1: 规则设计
委派给 **rts-systems-designer**:
- 创建/更新 design/gdd/ 中的子系统设计文档
- 定义公式、变量、边界情况、调参旋钮
- 输出: 完成的 GDD 文档

### Phase 2: 规则实现
委派给 **rts-simcore-engineer**:
- 根据 GDD 实现规则引擎
- 编写协议层的 Protobuf 定义
- 确保 Headless 模式下完整运行
- 输出: SimCore 代码 + 协议定义

### Phase 3: 回放与遥测
委派给 **rts-data-engineer**:
- 为新规则添加回放录制点
- 定义遥测事件 schema
- 确保新事件的 MLflow 追踪
- 输出: 回放/遥测集成

### Phase 4: 确定性验证
委派给 **rts-test-orchestrator**:
- 生成 seed × 场景 的测试矩阵
- 验证回放重放一致率 ≥ 99.5%
- 验证非法动作率 ≤ 0.1%
- 输出: 验证报告

每个阶段转换时，展示子 Agent 的分析结果，由用户决定是否继续。
