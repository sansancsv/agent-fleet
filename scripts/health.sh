#!/usr/bin/env bash
# =============================================================================
# health.sh — chờ và kiểm tra sức khoẻ toàn bộ ngăn xếp
# -----------------------------------------------------------------------------
# Vì sao phải CHỜ chứ không kiểm ngay: `docker compose up -d` trả về khi
# container đã *khởi động*, không phải khi dịch vụ đã *sẵn sàng*. n8n mất 20–40
# giây chạy migration lần đầu; LangGraph phải kết nối Postgres và tạo bảng
# checkpoint. Kiểm ngay lập tức sẽ báo "Connection reset by peer" — một lỗi giả
# khiến người ta đi tìm sai chỗ.
#
# Chạy:  make health   (hoặc ./scripts/health.sh)
# =============================================================================
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPOSE=(docker compose -f deploy/docker/docker-compose.yml --env-file .env)
TIMEOUT="${FLEET_HEALTH_TIMEOUT:-180}"

C_OK=$'\033[32m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
FAIL=0

# wait_http <nhãn> <url>
wait_http () {
  local label="$1" url="$2" waited=0
  printf '  %-22s' "$label"
  while (( waited < TIMEOUT )); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      echo "${C_OK}sẵn sàng${C_OFF} ${C_DIM}(${waited}s)${C_OFF}"; return 0
    fi
    sleep 3; waited=$((waited + 3))
    printf '.'
  done
  echo " ${C_ERR}KHÔNG phản hồi sau ${TIMEOUT}s${C_OFF}"
  FAIL=1; return 1
}

# wait_exec <nhãn> <service> <lệnh trong container...>
wait_exec () {
  local label="$1" svc="$2"; shift 2
  local waited=0
  printf '  %-22s' "$label"
  while (( waited < TIMEOUT )); do
    if "${COMPOSE[@]}" exec -T "$svc" "$@" >/dev/null 2>&1; then
      echo "${C_OK}sẵn sàng${C_OFF} ${C_DIM}(${waited}s)${C_OFF}"; return 0
    fi
    sleep 3; waited=$((waited + 3))
    printf '.'
  done
  echo " ${C_ERR}KHÔNG phản hồi sau ${TIMEOUT}s${C_OFF}"
  FAIL=1; return 1
}

echo "Chờ các dịch vụ sẵn sàng (tối đa ${TIMEOUT}s mỗi dịch vụ):"
wait_exec "mcporter bridge"   mcporter nc -z 127.0.0.1 7420
wait_exec "agent-runner API"  agent-runner curl -fsS http://127.0.0.1:8787/healthz
wait_http "OpenClaw gateway"  "http://127.0.0.1:${OPENCLAW_GATEWAY_PORT:-18789}/healthz"
wait_http "LangGraph"         "http://127.0.0.1:${LANGGRAPH_PORT:-2024}/ok"
wait_http "n8n"               "http://127.0.0.1:${N8N_PORT:-5678}/healthz"

echo
echo "Trạng thái container:"
"${COMPOSE[@]}" ps --format '  {{.Service}}\t{{.State}}\t{{.Status}}' 2>/dev/null

if (( FAIL )); then
  echo
  echo "${C_ERR}Có dịch vụ chưa lên.${C_OFF}"
  # In luôn log của dịch vụ hỏng thay vì bắt người dùng chạy thêm một lệnh nữa.
  # Đặc biệt hữu ích khi container đang RESTART LOOP: nó luôn hiện "Up 7 seconds"
  # nên nhìn `ps` sẽ tưởng đang khởi động bình thường.
  for svc in openclaw-gateway langgraph n8n mcporter; do
    state=$("${COMPOSE[@]}" ps --format '{{.Service}} {{.Status}}' 2>/dev/null | awk -v s="$svc" '$1==s{$1="";print}')
    [[ "$state" == *"healthy"* ]] && continue
    echo
    echo "${C_DIM}── $svc —$state ──${C_OFF}"
    "${COMPOSE[@]}" logs --tail 25 --no-log-prefix "$svc" 2>/dev/null | sed 's/^/  /'
  done
  echo
  echo "Mẹo đọc: container 'Up vài giây' lặp đi lặp lại = đang khởi động lại liên tục,"
  echo "không phải đang khởi động. Nguyên nhân nằm ở những dòng cuối log trên."
  exit 1
fi
echo
echo "${C_OK}Toàn bộ ngăn xếp đã sẵn sàng.${C_OFF}"
