---
name: test-matrix
description: "生成 RTS 测试矩阵，包括 seed × map × opponent × patch 组合。"
argument-hint: "[candidate_model] [baseline_model] [--maps map1,map2] [--seeds N]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, Edit, Bash
---

# Test Matrix 生成

此技能生成完整的测试矩阵，用于批量对战测试。

## 使用场景

- 新模型发布前验证
- 地图/单位平衡性测试
- 补丁影响评估
- 泛化性测试

## Matrix 结构

```yaml
test_matrix:
  id: "TM-20260507-001"
  created: "2026-05-07T16:00:00Z"
  
  candidate:
    model_id: "model_v2.1.0"
    build_id: "build_20260507_001"
    
  baseline:
    model_id: "model_v2.0.5"
    build_id: "build_20260506_003"
  
  dimensions:
    maps:
      - map_standard_001
      - map_standard_002
      - map_procedural_001
      - map_procedural_002
    
    seeds: [1, 42, 123, 456, 789, 1024, 2048, 4096]
    
    opponents:
      - type: baseline
        models: [script_ai_v1, script_ai_v2]
      - type: historical
        models: [model_v2.0.0, model_v2.0.5]
      - type: self_play
        modes: [mirror, cross]
    
    modes:
      - standard    # 标准测试
      - ood         # 未见地图测试
      - stress      # 压力测试
  
  total_games: 384  # 计算得出
```

## 生成流程

1. **解析参数**：候选模型、基线模型、可选参数
2. **加载地图池**：从配置加载可用地图
3. **生成种子**：使用指定种子或自动生成
4. **构建矩阵**：计算所有组合
5. **输出矩阵**：写入 `production/test-matrices/`

## 输出示例

```
## Test Matrix: TM-20260507-001

### 配置
- 候选模型: model_v2.1.0
- 基线模型: model_v2.0.5
- 地图数: 4
- 种子数: 8
- 对手数: 4

### 总对局数: 384

### 维度明细
| 维度 | 值 |
|------|-----|
| maps | map_standard_001, map_standard_002, map_procedural_001, map_procedural_002 |
| seeds | 1, 42, 123, 456, 789, 1024, 2048, 4096 |
| opponents | script_ai_v1, script_ai_v2, model_v2.0.0, model_v2.0.5 |

### 输出文件
已写入: production/test-matrices/TM-20260507-001.yaml
```