#!/usr/bin/env bash
# =============================================================================
# bridge-up.sh — bật daemon mcporter, phơi MỘT cầu nối MCP duy nhất.
# -----------------------------------------------------------------------------
# OpenClaw, acpx, LangGraph và n8n đều trỏ vào cầu nối này thay vì tự
# khởi động server MCP riêng. Lợi ích: một nơi giữ kết nối, một nơi giữ token,
# một nơi ghi log gọi tool.
# =============================================================================
set -Eeuo pipefail
PORT="${MCPORTER_BRIDGE_PORT:-7420}"

exec mcporter daemon \
  --bridge \
  --port "$PORT" \
  --bind "${MCPORTER_BRIDGE_BIND:-0.0.0.0}" \
  --auth-token-env MCPORTER_BRIDGE_TOKEN \
  --log-format json \
  --log-file "${FLEET_LOG_DIR:-/var/log/fleet}/mcporter-bridge.jsonl"
