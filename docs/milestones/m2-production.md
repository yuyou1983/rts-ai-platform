# M2 里程碑：训练生产闭环

**周期**: 6 周
**状态**: 🟡 **进行中** (Phase 1-2 ✅, Phase 3 活跃)
**前置**: M1 Multi-Agent ✅

---

## 目标

建设 GRPO 自对弈训练闭环 + League 版本池 + Promotion Gate 自动晋级，让 Agent 能通过自我博弈持续进化。

## 核心交付物

| 交付物 | 优先级 | 状态 | 验收标准 |
|--------|--------|------|----------|
| Gym 环境 (SimCoreGym) | P0 | ✅ | step/reset/reward 符合 Gymnasium API |
| GRPO smoke-test | P0 | ✅ | 1 episode 完成无 NaN |
| 四层架构边界恢复 | P0 | ✅ | `make lint-arch` 0 violations |
| test-core / test-integration 拆分 | P0 | ✅ | 459 core / 23 integration tests |
| TRL GRPOTrainer 集成 | P0 | ❌ | 100 episode 稳定训练 |
| Rollout Worker (异步采集) | P0 | ❌ | 32 路并发 |
| League 调度器 | P1 | ❌ | Round-robin + 历史版本池 |
| Promotion Gate | P1 | ❌ | 新版 > 旧版 55% → 自动替换 |
| 训练曲线可视化 | P2 | ❌ | 胜率/奖励曲线 |
| Replay 回放器 | P2 | ❌ | Godot 加载 replay JSON |

## 阶段拆分

### Phase 1: 基础设施 ✅ (2026-05-18 完成)

- [x] SimCoreGym env (obs/action/reward 符合 Gymnasium)
- [x] GRPO smoke-test (SimplePolicy, 1.84s)
- [x] 150局 benchmark 0 crash, 确定性回放 0 差异
- [x] MemoryLake 插件配置

### Phase 2: 架构硬化 ✅ (2026-05-20 完成)

- [x] 四层架构边界恢复: simcore(L1) ❌→ agents/runtime(L2)
- [x] 新增 runtime/ 编排层: agent_factory, auto_step, gym_ai
- [x] simcore 依赖注入: agent_factory 回调替代直接 import
- [x] lint_deps.py: runtime=L2 约束注册
- [x] Makefile: python→python3 统一, test-core/test-integration 拆分
- [x] 集成测试标记: @pytest.mark.integration

### Phase 3: 训练闭环 🟡 Active

- [ ] TRL GRPOTrainer 集成 (替代 SimplePolicy)
- [ ] Rollout Worker 异步采集
- [ ] 自对弈 League 调度
- [ ] Promotion Gate 自动晋级

### Phase 4: 生产化 ⬜

- [ ] 训练曲线可视化
- [ ] 优秀对局自动提取
- [ ] Godot replay 回放器
- [ ] 长程训练启动脚本

## 关键架构

```
League Scheduler
  ├── Agent Pool: [ScriptAI, GRPO-v1, GRPO-v2, ...]
  ├── Match Scheduler: round-robin N×(N+1)/2 per seed
  ├── Simulation Pool: asyncio N workers
  └── Promotion Gate: 100 games, >55% → promote

Rollout Worker
  ├── asyncio 32 workers
  ├── Shared RolloutBuffer
  └── ~500 games/hr on 4 cores

GRPO Trainer (TRL)
  ├── Sample group of rollouts
  ├── Compute group-relative advantage
  ├── PPO-clip update
  └── New checkpoint → add to League pool
```

## 参考

- Harness benchmark: `harness/output/benchmark_stats.json`
- Phase 1 验证: `docs/exec-plans/active/2026-05-18-gap-fix-m2-prep.md`
- Phase 2 验证: git commits `973aa3b` `64ba9dc`
- GRPO 论文: DeepSeek-R1 GRPO technique