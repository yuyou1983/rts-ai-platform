#!/bin/bash
# Launch SimCore gRPC server with auto-step mode
# Usage: run_server.sh <port>
cd "$(dirname "$0")/../../"
PORT="${1:-50051}"
exec python3 -m simcore.grpc_server --port "$PORT" --auto-step --tick-rate 20 &