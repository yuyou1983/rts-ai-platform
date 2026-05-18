# M1→M2 执行计划：补齐缺口 + 训练闭环

**日期**: 2026-05-18
**状态**: 🟢 Active

## 目标

补齐当前项目所有缺口，为 M2 Multi-Agent League 训练闭环做好准备。

## 任务清单

### G1: 里程碑文档 ✅
- [x] 补齐 m1-multi-agent.md
- [x] 补齐 m2-production.md
- [x] 修正 production/stage.txt → M1

### G2: ScoutAgent 包装器
- [ ] 创建 agents/scout.py (AgentBase wrapper)

### G3: ReactGameAgent LLM 后端
- [ ] 创建 agents/llm_client.py (OpenAI 兼容 API)
- [ ] 创建 agents/prompts/ 目录 + RTS 决策 prompt 模板
- [ ] 修改 react_adapter.py 接入 llm_client

### G4-G6: Harness 训练基础设施
- [ ] harness/scheduler.py (联赛调度)
- [ ] harness/league.py (版本池 + 自对弈)
- [ ] harness/promotion.py (晋级门)

### G7-G8: 训练基础设施
- [ ] train/rl_trainer.py (TRL GRPOTrainer 集成)
- [ ] train/rollout_worker.py (异步采集)

### G9-G10: 测试 + 验证
- [ ] 补齐测试文件
- [ ] 全量 243+ tests 通过