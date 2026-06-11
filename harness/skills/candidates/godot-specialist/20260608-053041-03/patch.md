## Runtime Boundary 修复

Godot skill 的失败轨迹触碰了 runtime business paths。后续 Godot VFX/resource alignment 任务必须先尝试 manifest、asset、test/harness 层修复；业务代码变更必须拆成单独 harness-executor 任务。
- observed: runtime file (game_view.gd)