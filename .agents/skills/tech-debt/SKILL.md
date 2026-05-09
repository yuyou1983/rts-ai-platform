---
name: tech-debt
description: "技术债识别和优先级排序: 扫描代码库，识别技术债，给出偿还优先级建议。"
argument-hint: "[system-name or 'full']"
user-invocable: true
allowed-tools: Read, Glob, Grep, Bash
---

当此 skill 被调用时：

1. 扫描代码中的 TODO/FIXME/HACK/XXX
2. 识别架构违规:
   - 循环依赖
   - 层级穿透 (Agent 直接访问 State 对象)
   - 硬编码配置 (应该外置为数据文件)
3. 识别性能隐患:
   - 热路径中的字符串操作
   - 每帧分配模式
   - 缺少对象池
4. 排序: 影响 × 紧急度
5. 输出技术债清单到 `production/tech-debt.md`
