# M2 Playability Sprint 01

**Sprint goal:** 从关闭服务的环境开始，建立可启动、可渲染、可 attack-move、可人工评价并能走通 Terran 科技线的五分钟研究客户端。

**Source plan:** `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
**Execution model:** one ticket per fresh Hermes run; Hermes self-verifies; ChatGPT independently accepts or returns each ticket.
**Initial fixed point:** assigned in the S1 Hermes Task Unit after the S0 acceptance commit.

## Current Red-Capable Baseline

With ports 50051 and 8080 closed:

```bash
/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_start_game_bootstrap.gd
```

Current result: exit 1 with `[GrpcBridge] start_game failed (HTTP 0)` and `Start Game lost the backend connection`.

### S0 Freeze a recoverable project baseline

- Status: done
- Blocked by: none
- Source specification: `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
- What it delivers: 把现有 Harness evidence-hardening、ChatGPT/Hermes 编排文档、启动红测试和无关生成输出分组，形成一个可供后续任务引用的 clean fixed point，不改变游戏行为。
- Acceptance criteria:
  - `docs/reports/m2-playability-baseline.md` 记录当前 HEAD、分支、所有 dirty path 的 owner/disposition，以及 bootstrap 红测试原始结论。
  - Harness 相关改动通过 357 项测试、四个 validator 和 `git diff --check`。
  - SC1 replay、proto 生成物、HTML deck 和其他无关文件没有进入本 Sprint 的提交范围。
  - ChatGPT 给出一个实际 Git SHA 作为 S1-H1 的 fixed point。
- Verification seams:
  - `python3 -m pytest tests/harness -q`
  - `python3 harness/skills/validate_registry.py && python3 harness/skills/validate_tasks.py && python3 harness/skills/validate_held_out_suites.py && python3 harness/trace/validate_traces.py --strict`
  - `make lint-arch`
  - `git diff --check`
- Evidence outputs:
  - `docs/reports/m2-playability-baseline.md`
- Owner skill: gate-check

### S1 Start Game owns local backend readiness

- Status: ready
- Blocked by: S0
- Source specification: `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
- What it delivers: 在开发环境中关闭 50051/8080 后，Godot 主菜单 Start Game 自动启动受控的本地 gRPC/HTTP 服务，等待 readiness 后重试 start request；退出 Godot 后只清理由本次启动的服务。
- Acceptance criteria:
  - `godot/scripts/test_start_game_bootstrap.gd` 在端口关闭时收到非空 entities 和 fog-of-war。
  - bootstrap 连续运行三次均通过，第二次运行不因 stale PID、端口占用或日志锁失败。
  - 已存在的外部服务不会被重复启动或在 Godot 退出时被杀死。
  - 启动超时、Python 缺失和后端异常均转成可见错误状态，不进入空白 game view。
  - 默认路由不使用 shell 拼接用户输入，export/release 构建可关闭本地自动启动。
- Verification seams:
  - `python3 -m pytest tests/godot/test_frontend_bootstrap_contract.py -q`
  - `python3 scripts/verify_frontend_bootstrap.py --runs 3 --require-cleanup`
  - `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --check-only`
- Evidence outputs:
  - `docs/reports/godot-start-game-bootstrap-qa.md`
  - `harness/output/godot/bootstrap-runs.json`
- Owner skill: godot-specialist

S0 acceptance evidence: `docs/reports/m2-playability-baseline.md`. S1 may start only from the fixed point recorded in its ChatGPT-generated Hermes Task Unit; the status change here does not authorize an agent to infer a SHA.

### S2 Render initial entities and fog in the real GameView

- Status: blocked
- Blocked by: S1
- Source specification: `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
- What it delivers: 启动实际 `game_view.tscn`，证明服务状态不仅到达 bridge，还创建了实体 Sprite2D、资源贴图、fog grid 和可交互 SelectionManager 数据。
- Acceptance criteria:
  - live smoke 中 `_ents`、`_sprite_pool`、`_entity_cache_by_id` 均非空，且己方可见实体都有可显示 Sprite2D。
  - `_fog_w * _fog_h` 等于 fog tile 数，unexplored/explored/visible 至少出现两种状态。
  - SCV、Drone、Probe 三种固定启动各通过一次，缺失贴图时测试失败而不是静默画 fallback 圆点。
  - GameView 在服务连接失败时显示错误 overlay，不把空 HUD 当作正常对局。
- Verification seams:
  - `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_live_game_render.gd`
  - `python3 -m pytest tests/godot/test_live_game_render_contract.py tests/godot/test_presentation_manifest.py -q`
  - `python3 scripts/verify_presentation_scene.py`
- Evidence outputs:
  - `docs/reports/godot-live-render-smoke-qa.md`
  - `harness/output/godot/live-render-matrix.json`
- Owner skill: godot-specialist

### S3 Implement true attack-move end to end

- Status: blocked
- Blocked by: S2
- Source specification: `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
- What it delivers: A+左键发出独立 attack-move 命令；单位向目标点移动、沿途获取合法可见敌人、完成交战后恢复原路径，stop/move/explicit attack 能正确覆盖该 order。
- Acceptance criteria:
  - `proto/cmd.proto` 包含独立 `AttackMoveCommand`，生成 binding 由 `make proto` 产生而非手改。
  - 同 seed、命令和 `PYTHONHASHSEED` 下 attack-move 的 state hash 序列一致。
  - 单位不会获取中立资源、战争迷雾外敌人或超出 acquisition radius 的目标。
  - 目标死亡或离开合法范围后，单位恢复原 attack-move 目标点；玩家 move/stop 命令立即取消该 order。
  - Godot 不再把 attack-move 降级成 `action: move`，输入反馈仍在本地一帧内出现。
- Verification seams:
  - `make proto`
  - `python3 -m pytest tests/proto/test_attack_move_proto.py tests/simcore/test_attack_move.py tests/integration/test_attack_move_e2e.py -q`
  - `python3 -m pytest tests/integration/test_cross_hashseed_determinism.py -q`
  - `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_attack_move_pipeline.gd`
  - `make lint-arch`
- Evidence outputs:
  - `docs/reports/attack-move-e2e-qa.md`
  - `harness/output/replays/attack-move-seed-4242.jsonl`
- Owner skill: team-simcore

### S4 Close live operation-feel and manual gates

- Status: blocked
- Blocked by: S3
- Source specification: `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
- What it delivers: 在实际 GameView/HTTP 状态循环中测量输入到反馈、命令提交、选择成功率和编队召回，而不是只测试纯函数；生成双分辨率、三种族的人工验收证据。
- Acceptance criteria:
  - live input-to-feedback P95 <= 1 frame，empty command rate <= 1%，control-group recall success = 100%。
  - Terran、Zerg、Protoss 的 click target success >= 95%，box selection expected set >= 95%。
  - 1280x720 与 1920x1080 的 camera pan、edge scroll、click、box select、right-click、group recall 六项均有记录。
  - Hermes 完成自动化和截图证据；ChatGPT/用户完成产品门后才把 ticket 从 `verification` 转为 `done`。
- Verification seams:
  - `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_live_operation_feel.gd`
  - `python3 scripts/summarize_feel_metrics.py harness/output/godot/live-feel-metrics.jsonl --enforce-gates`
  - `python3 -m pytest tests/godot -q`
- Evidence outputs:
  - `docs/reports/godot-operation-feel-live-qa-2026-08.md`
  - `harness/output/godot/live-feel-metrics.jsonl`
  - `harness/output/godot/screenshots/operation-feel/`
- Owner skill: godot-specialist

### S5 Close combat readability using real event-driven VFX

- Status: blocked
- Blocked by: S4
- Source specification: `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
- What it delivers: 使用现有权威 CombatEvent 和 12 单位 weapon catalog，修正真实对局中的弹道、命中、死亡、护盾和密集战斗特效容量，使五组代表 matchup 肉眼可区分。
- Acceptance criteria:
  - Marine、Vulture、Mutalisk、Dragoon、Reaver 五组代表攻击都产生与 weapon profile 一致的 attack/projectile/impact 证据。
  - 30v30 运行中 active effects/projectiles 采样值大于 0 且不超过配置上限，不出现 duplicate death 或 orphan projectile。
  - `run_matchup_acceptance.py` 保持 10/10 PASS，SimCore 伤害和冷却数值不因纯视觉调优改变。
  - 五组人工 readability 的攻击来源、弹道、命中、死亡四项均不低于 4/5。
- Verification seams:
  - `python3 scripts/run_matchup_acceptance.py`
  - `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_combat_event_pipeline.gd`
  - `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_vfx_runtime_caps.gd`
  - `python3 -m pytest tests/godot/test_weapon_visual_catalog.py tests/simcore/test_sc1_representative_weapons.py -q`
- Evidence outputs:
  - `docs/reports/sc1-combat-readability-live-qa.md`
  - `harness/output/godot/combat-vfx-runtime-metrics.json`
  - `harness/output/godot/screenshots/combat-readability/`
- Owner skill: godot-shader-specialist

### S6 Prove the Terran five-minute tech path

- Status: blocked
- Blocked by: S5
- Source specification: `docs/plans/2026-08-05-project-next-iteration-roadmap.md`
- What it delivers: 从新对局开始，通过同一 HUD/SimCore 权威建造链完成 Barracks、Factory、Starport，并分别生产 Marine、Vulture、Wraith，最后使用 attack-move 进入战斗。
- Acceptance criteria:
  - HUD 只显示满足资源和 prerequisite 的可用项，Factory 需要 Barracks，Starport 需要 Factory。
  - 每次 build/train 都有 accepted、progress、completed 或 rejected 的可见反馈，不出现按键成功但后端无命令。
  - 固定 seed 4242 的自动场景在 3000 tick 内建成三座生产建筑并产生三种目标单位。
  - replay 重放得到相同 completion tick、实体 ID 集合和最终 state hash。
- Verification seams:
  - `python3 -m pytest tests/integration/test_terran_tech_path_e2e.py tests/simcore/test_construction.py tests/simcore/test_production.py -q`
  - `/Applications/Godot.app/Contents/MacOS/Godot --headless --path godot --script scripts/test_terran_build_ui.gd`
  - `python3 scripts/verify_terran_five_minute_slice.py --seed 4242 --max-ticks 3000 --verify-replay`
- Evidence outputs:
  - `docs/reports/terran-five-minute-slice-qa.md`
  - `harness/output/replays/terran-five-minute-seed-4242.jsonl`
- Owner skill: team-simcore

### H1 Run the first real Hermes SkillEvolver evidence pilot

- Status: blocked
- Blocked by: S0
- Source specification: `docs/plans/2026-08-04-agent-skills-workflow-alignment-execution-plan.md`
- What it delivers: 从固定提交启动 fresh Hermes code-review candidate run，记录非零 token/turn/duration、runner provenance、output hash 和 held-out scenario evidence，并得到一次正确 promotion 或 rejection。
- Acceptance criteria:
  - baseline 与 candidate 使用不同且唯一的 `agent_run_id`，都绑定实际读取的 `SKILL.md` hash。
  - candidate 覆盖 code-review suite 的全部 held-out scenario，未复用 training fixture。
  - `validate_held_out_candidate()` 返回带场景明细的结果，promotion 必须经过 manual approval；证据不足时 fail closed。
  - SkillEvolver 未修改 `simcore/`、`agents/`、`godot/scripts/` 或 `proto/`。
- Verification seams:
  - `python3 -m pytest tests/harness -q`
  - `python3 harness/trace/validate_traces.py --strict`
  - `python3 harness/skills/validate_held_out_suites.py`
- Evidence outputs:
  - `harness/trace/trials/2026-08-05-hermes-pilot.jsonl`
  - `docs/reports/skill-evolver-real-hermes-pilot.md`
- Owner skill: harness-run

## Sprint Exit Gate

Sprint 结束需要 S0-S6 全部由 ChatGPT 标记 `ACCEPTED`，H1 至少得到一个证据完整的正确 `ACCEPTED` 或正确 `REJECTED` 结论。任何人工视觉门仍为 `PENDING` 时，不得把 Sprint 标记为 done。
