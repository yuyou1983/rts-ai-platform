## Silent-Bypass 修复

在 1 次失败中检测到 silent-bypass。
将以下规则从 '应该' 升级为 '必须'，并添加对应的 validation_commands：
- primary_action: must be invoked in every task execution
- Read SKILL.md: must be the first tool call
Run `godot --headless --check-only` before marking task complete.
