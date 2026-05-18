# M2 里程碑：训练生产闭环

**周期**: 6 周
**状态**: 🟡 **进行中** (Phase 1 验证完成)
**前置**: M1 Multi-Agent

---

## 目标

建设 GRPO 自对弈训练闭环 + League 版本池 + Promotion Gate 自动晋级，让 Agent 能通过自我博弈持续进化。

## 核心交付物

| 交付物 | 优先级 | 状态 | 验收标准 |
|--------|--------|------|----------|
| Gym 环境 (SimCoreGym) | P0 | ✅ | step/reset/reward 符合 Gymnasium API |
| GRPO smoke-test | P0 | ✅ | 1 episode 完成无 NaN |
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

### Phase 2: 训练闭环 🟡

- [ ] TRL GRPOTrainer 集成 (替代 SimplePolicy)
- [ ] Rollout Worker 异步采集
- [ ] 自对弈 League 调度
- [ ] Promotion Gate 自动晋级

### Phase 3: 生产化 ⬜

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
- Phase1 验证: `docs/milestones/../exec-plans/`
- GRPO 论文: DeepSeek-R1 GRPO technique