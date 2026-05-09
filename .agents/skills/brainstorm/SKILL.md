---
name: brainstorm
description: "RTS 专向头脑风暴: 生成 3-5 个创意方向，使用 MDA/SDT 等设计理论评估。"
argument-hint: "[topic]"
user-invocable: true
allowed-tools: Read, Glob, Grep, Write, WebSearch
---

当此 skill 被调用时：

1. **理解主题**: 用户想探索什么？
2. **发散**: 生成 3-5 个创意方向
3. **评估**: 每个方向的 MDA (机制-动态-美学) 分析
4. **对齐**: 与项目支柱的对齐度
5. **推荐**: 推荐最值得深入的 1-2 个方向
6. **输出**: 写入 `design/brainstorm/[topic]-[date].md`
