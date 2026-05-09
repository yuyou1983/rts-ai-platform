# M0 启动阶段

**周期**: 6 周
**目标**: 把"规则、回放、build、基线 AI、数据埋点"五件事闭环连在一起

## 核心交付物

| 交付物 | 负责人 | 优先级 | 验收标准 |
|--------|--------|--------|----------|
| 规则/状态/命令协议 v1 | 技术总监 + 玩法主程 | P0 | 同一 seed 可复现实验；状态快照与回放一致 |
| 2D Headless SimCore | 玩法主程 | P0 | 1v1 从开局到胜负完整跑通；崩溃率 < 2% |
| 基线脚本 AI（经济/战斗） | AI 负责人 | P0 | 能完成采集、生产、进攻、防守基本循环 |
| Replay/Telemetry v1 | 数据工程 | P0 | 回放完整率 >= 99%；核心事件可追溯 |
| CI/一键构建/冒烟测试 | 工具链负责人 | P0 | 每次提交可自动 build + smoke battle |

## 周计划

### Week 1-2: 协议与基础

- [ ] 定义 obs/cmd 协议 v1
- [ ] SimCore 规则引擎原型
- [ ] 状态快照系统
- [ ] 命令解析器
- [ ] 回放录制基础

### Week 3-4: SimCore 核心

- [ ] 2D headless 运行时
- [ ] 基线脚本 AI (经济)
- [ ] 基线脚本 AI (战斗)
- [ ] 单局回放完整录制

### Week 5-6: CI 与数据

- [ ] CI/CD pipeline 搭建
- [ ] 一键构建系统
- [ ] 冒烟测试自动化
- [ ] 数据埋点系统
- [ ] 基础指标面板

## 验收 KPI

| 维度 | 目标 |
|------|------|
| 规则一致性 | 同一 seed 回放一致率 >= 99.5% |
| 构建稳定性 | nightly build 成功率 >= 85% |
| AI 合法性 | 非法动作率 <= 0.5% |
| 回放完整性 | replay + event + build metadata 关联率 >= 99% |
| 吞吐 | 2D 并发仿真 32-64 局 |

## Agent 开发计划

### 运行时 Agent
- [x] rts-coordinator IDENTITY.md
- [x] rts-combat IDENTITY.md
- [x] rts-economy IDENTITY.md
- [ ] rts-strategy IDENTITY.md
- [ ] rts-scout IDENTITY.md
- [ ] rts-build IDENTITY.md

### 研发侧 Agent
- [x] rts-test-orchestrator (配置)
- [x] rts-balance (配置)
- [x] rts-design-assistant (配置)
- [x] rts-replay-analyzer (配置)

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 规则不确定/不可重放 | 高 | 先做 deterministic replay 与 seed 管理 |
| 2D headless 性能不足 | 中 | 性能基准测试，必要时优化热路径 |
| 基线 AI 过弱无法闭环 | 中 | 分层实现：脚本规则 -> 状态机 -> 学习型 |