# M2 Phase 3：训练生产闭环

**日期**: 2026-05-20
**状态**: 🟢 Active

## 目标

建设 GRPO 自对弈训练闭环，让 Agent 能通过自我博弈持续进化。

## 前置完成

- ✅ Phase 1: Gym 环境 + GRPO smoke-test
- ✅ Phase 2: 四层架构边界恢复 + test-core/integration 拆分

## 任务清单

### T1: TRL GRPOTrainer 集成 ⬜
- [ ] 替换 SimplePolicy → TRL GRPOTrainer
- [ ] 100 episode 稳定训练无 NaN
- [ ] 训练曲线导出 (loss/reward CSV)

### T2: Rollout Worker 异步采集 ⬜
- [ ] asyncio 32 路并发
- [ ] Shared RolloutBuffer
- [ ] ~500 games/hr on 4 cores

### T3: League 调度 ⬜
- [ ] Round-robin N×(N+1)/2 per seed
- [ ] 历史版本池
- [ ] AgentVersion 注册 + ELO 计算

### T4: Promotion Gate ⬜
- [ ] 100 局验证
- [ ] 新版 > 旧版 55% → 自动替换
- [ ] Wilson CI 置信区间

### T5: 验证 ⬜
- [ ] 全量 459 core tests 通过
- [ ] 23 integration tests 通过
- [ ] `make lint-arch` 0 violations