---
name: harness-run
description: "调度并运行 Harness 批量对战任务，监控进度，收集结果。"
argument-hint: "[test_matrix_file] [--parallel N] [--timeout minutes]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, Bash
---

# Harness 运行

此技能调度并执行批量对战任务。

## 使用场景

- 执行测试矩阵
- 批量模型对比
- 回归测试
- 性能基准测试

## 运行流程

```
1. 加载 Test Matrix
   │
2. 验证构建可用
   │
3. 调度并行任务
   │
4. 监控执行进度
   │
5. 收集结果和回放
   │
6. 聚合指标
   │
7. 生成报告
```

## 进度监控

```
## Harness 运行进度: HR-20260507-001

### 状态: RUNNING (45%)

### 任务统计
| 状态 | 数量 | 百分比 |
|------|------|--------|
| 完成 | 172 | 45% |
| 运行中 | 64 | 17% |
| 排队 | 96 | 25% |
| 失败 | 12 | 3% |
| 等待 | 40 | 10% |

### 当前运行
- Worker 1: map_001, seed_42, vs_script_ai_v1
- Worker 2: map_002, seed_123, vs_model_v2.0.5
- ...

### 预计完成时间: 15 分钟
```

## 结果收集

```
### 收集的数据
- Replays: 172 个文件
- Event Logs: 172 个文件
- Metrics: 聚合到 mlflow run

### 存储位置
- Replays: s3://rts-platform/replays/HR-20260507-001/
- Metrics: mlflow:/experiments/123/runs/abc
```