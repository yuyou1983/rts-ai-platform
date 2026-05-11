.PHONY: build test lint lint-arch format clean proto sim smoke-test play stop

# ─── Protocol Buffers ──────────────────────────────────────
proto:
	python -m grpc_tools.protoc -Iproto \
		--python_out=simcore/proto_out \
		--grpc_python_out=simcore/proto_out \
		proto/*.proto
	@sed -i '' 's/^from proto import/from simcore.proto_out.proto import/' simcore/proto_out/proto/service_pb2.py simcore/proto_out/proto/service_pb2_grpc.py 2>/dev/null || true
	@touch simcore/proto_out/proto/__init__.py

# ─── Build & Install ───────────────────────────────────────
build: proto
	pip install -e ".[dev]"

# ─── Testing ────────────────────────────────────────────────
test:
	python -m pytest tests/ -q -n 4

smoke-test:
	@echo "Running headless smoke battle..."
	@python -m simcore.engine --seed 42 --max-ticks 1000 --ai baseline vs baseline
	@echo "✓ Smoke test passed"

smoke-test-mvp:
	@echo "=== MVP Smoke Test ==="
	@PYTHONPATH=. python3 scripts/smoke_mvp.py

# ─── Linting ────────────────────────────────────────────────
lint: lint-arch
	ruff check .
	mypy simcore/ agents/ --ignore-missing-imports

lint-arch:
	@echo "Checking architecture constraints..."
	@python3 scripts/lint_deps.py simcore/ agents/ proto/
	@python3 scripts/lint_quality.py simcore/ agents/
	@echo "✓ Architecture checks passed"

format:
	ruff format .

# ─── Run ────────────────────────────────────────────────────
sim:
	python -m simcore.engine

# ─── Play (MVP) ─────────────────────────────────────────────
# Launches backend servers + Godot for Human P1 vs AI P2
play: stop
	@echo "Starting RTS AI Platform (Human vs AI)..."
	@PYTHONPATH=. python3 -m simcore.grpc_server --port 50051 &>/tmp/rts_grpc.log &
	@sleep 1
	@PYTHONPATH=. python3 -m simcore.http_gateway --grpc-port 50051 --http-port 8080 &>/tmp/rts_http.log &
	@sleep 1
	@echo "Backend ready. Launching Godot..."
	@/Applications/Godot.app/Contents/MacOS/Godot --path godot &>/tmp/rts_godot.log &
	@echo "✓ Game launched! Close Godot to stop."
	@echo "  Use 'make stop' to clean up background processes."

stop:
	@pkill -f "simcore.grpc_server" 2>/dev/null || true
	@pkill -f "simcore.http_gateway" 2>/dev/null || true
	@pkill -f "Godot.*rts-ai" 2>/dev/null || true
	@echo "✓ Stopped all services"

# ─── Clean ──────────────────────────────────────────────────
clean:
	rm -rf __pycache__ .mypy_cache .pytest_cache .ruff_cache
	rm -rf simcore/proto_out
	rm -rf *.egg-info dist build