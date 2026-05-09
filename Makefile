.PHONY: build test lint lint-arch format clean proto sim smoke-test

# ─── Protocol Buffers ──────────────────────────────────────
proto:
	python -m grpc_tools.protoc -Iproto \
		--python_out=simcore/proto_out \
		--grpc_python_out=simcore/proto_out \
		proto/*.proto

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

# ─── Clean ──────────────────────────────────────────────────
clean:
	rm -rf __pycache__ .mypy_cache .pytest_cache .ruff_cache
	rm -rf simcore/proto_out
	rm -rf *.egg-info dist build