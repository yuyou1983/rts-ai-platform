#!/bin/bash

# Start the local SimCore services required by the Godot frontend.
# Only services started by this script are stopped when the owning Godot
# process exits; independently managed services are left untouched.

set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
GRPC_PORT="${1:-50051}"
HTTP_PORT="${2:-8080}"
PARENT_PID="${3:-0}"
LOG_FILE="${RTS_BACKEND_LOG:-/tmp/rts_frontend_backend.log}"

resolve_python() {
	if [ -n "${RTS_PYTHON:-}" ] && [ -x "$RTS_PYTHON" ]; then
		printf '%s\n' "$RTS_PYTHON"
		return 0
	fi
	for candidate in \
		"$ROOT/.venv/bin/python3" \
		"/usr/local/bin/python3" \
		"/opt/homebrew/bin/python3" \
		"/usr/bin/python3"; do
		if [ -x "$candidate" ]; then
			printf '%s\n' "$candidate"
			return 0
		fi
	done
	command -v python3
}

PYTHON="$(resolve_python)" || {
	printf 'No usable Python 3 interpreter found.\n' >> "$LOG_FILE"
	exit 1
}

port_open() {
	"$PYTHON" -c 'import socket, sys; s=socket.socket(); s.settimeout(0.2); rc=s.connect_ex(("127.0.0.1", int(sys.argv[1]))); s.close(); raise SystemExit(0 if rc == 0 else 1)' "$1"
}

wait_for_port() {
	port="$1"
	attempts=0
	while [ "$attempts" -lt 40 ]; do
		if port_open "$port"; then
			return 0
		fi
		attempts=$((attempts + 1))
		sleep 0.1
	done
	return 1
}

cd "$ROOT" || exit 1
PIDS=""

cleanup() {
	for pid in $PIDS; do
		kill "$pid" 2>/dev/null || true
	done
	for pid in $PIDS; do
		wait "$pid" 2>/dev/null || true
	done
}
trap cleanup EXIT INT TERM

if ! port_open "$GRPC_PORT"; then
	"$PYTHON" -m simcore.grpc_server --port "$GRPC_PORT" --tick-rate 20 >> "$LOG_FILE" 2>&1 &
	PIDS="$PIDS $!"
fi

if ! wait_for_port "$GRPC_PORT"; then
	printf 'SimCore gRPC service did not become ready on port %s.\n' "$GRPC_PORT" >> "$LOG_FILE"
	exit 1
fi

if ! port_open "$HTTP_PORT"; then
	"$PYTHON" -m simcore.http_gateway --grpc-port "$GRPC_PORT" --http-port "$HTTP_PORT" >> "$LOG_FILE" 2>&1 &
	PIDS="$PIDS $!"
fi

if ! wait_for_port "$HTTP_PORT"; then
	printf 'SimCore HTTP gateway did not become ready on port %s.\n' "$HTTP_PORT" >> "$LOG_FILE"
	exit 1
fi

# Nothing was launched because another process completed startup first.
if [ -z "${PIDS// }" ]; then
	exit 0
fi

while [ "$PARENT_PID" -le 0 ] || kill -0 "$PARENT_PID" 2>/dev/null; do
	for pid in $PIDS; do
		if ! kill -0 "$pid" 2>/dev/null; then
			exit 1
		fi
	done
	sleep 1
done
