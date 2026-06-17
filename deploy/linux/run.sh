#!/usr/bin/env bash
# VM Panel — Linux 版快速启动
# 用法: ./run.sh [--port PORT] [--debug]

PORT=${2:-80}
DEBUG="false"

if [ "$1" = "--debug" ] || [ "$1" = "-d" ]; then
    DEBUG="true"
    PORT=${2:-5000}
fi

cd "$(dirname "$0")/../.."

echo "=== VM Panel Linux Edition ==="
echo "Port: $PORT  Debug: $DEBUG"
echo ""

VM_PANEL_PORT=$PORT \
VM_PANEL_DEBUG=$DEBUG \
VM_PANEL_HOST="0.0.0.0" \
SIMULATE_LIBVIRT="false" \
python3 deploy/run.py
