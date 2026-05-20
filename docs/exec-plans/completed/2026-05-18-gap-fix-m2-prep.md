# M1→M2 执行计划：补齐缺口 + 训练闭环准备

**日期**: 2026-05-18
**状态**: ✅ Completed (2026-05-20)

## 目标

补齐当前项目所有缺口，为 M2 Multi-Agent League 训练闭环做好准备。

## 任务清单

### G1: 里程碑文档 ✅
- [x] 补齐 m1-multi-agent.md
- [x] 补齐 m2-production.md
- [x] 修正 production/stage.txt → M1

### G2: ScoutAgent 包装器 ✅
- [x] 创建 agents/scout.py (AgentBase wrapper)

### G3-G10: Harness + 测试 ✅
- [x] harness/benchmark.py, pool.py, telemetry.py
- [x] harness/league.py, promotion.py, scheduler.py
- [x] train/rl_trainer.py, rollout_worker.py
- [x] 463 tests 全量通过