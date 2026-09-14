#!/usr/bin/env bash
# =============================================================================
# bridge-up.sh — phơi toàn bộ MCP server đã cấu hình ra MỘT điểm cuối duy nhất
# -----------------------------------------------------------------------------
# OpenClaw, acpx, LangGraph và n8n đều trỏ vào đây thay vì tự khởi động server
# MCP riêng. Lợi ích: một nơi giữ kết nối, một nơi giữ token, một nơi ghi log.
#
# Lệnh đúng là `mcporter serve --http <port>`:
#   • điểm cuối gộp        : /mcp        (tên tool có tiền tố <server>__<tool>)
#   • điểm cuối từng server: /mcp/<server>  (giữ nguyên tên tool gốc)
#
# LƯU Ý BẢO MẬT — đọc kỹ:
#   `mcporter serve` KHÔNG có xác thực. Mặc định nó nghe 127.0.0.1 chính vì lý do
#   đó. Khi phơi ra network của Docker/K8s, biện pháp bảo vệ là TẦNG MẠNG:
#     - Docker : không map cổng ra host (compose không có `ports:` cho dịch vụ này)
#     - K8s    : NetworkPolicy chỉ cho agent-runner / gateway / langgraph gọi tới
#   Đừng phơi cổng này ra ngoài cụm trong bất kỳ trường hợp nào.
# =============================================================================
set -Eeuo pipefail

PORT="${MCPORTER_BRIDGE_PORT:-7420}"
BIND="${MCPORTER_BRIDGE_BIND:-0.0.0.0}"
LOG_DIR="${FLEET_LOG_DIR:-/var/log/fleet}"
SERVERS="${MCPORTER_BRIDGE_SERVERS:-}"   # để trống = phơi toàn bộ server

mkdir -p "$LOG_DIR"

echo "[bridge] mcporter $(mcporter --version 2>/dev/null || echo '?')"

# --- Bật daemon giữ kết nối sống (pool) --------------------------------------
# Không bắt buộc, nhưng nhờ nó server stdio không phải khởi động lại mỗi lần gọi.
mcporter daemon start --log-file "$LOG_DIR/mcporter-daemon.log" 2>/dev/null \
  || echo "[bridge] daemon không bật được — vẫn chạy tiếp, chỉ chậm hơn"

SERVE_ARGS=()
[[ -n "$SERVERS" ]] && SERVE_ARGS+=(--servers "$SERVERS")

# --- Nghe trên đúng địa chỉ cần thiết ----------------------------------------
# Bản mcporter mới có thể hỗ trợ cờ đổi địa chỉ nghe; bản cũ thì không.
# Dò `--help` lúc chạy thay vì đoán, rồi chọn đường phù hợp.
HELP="$(mcporter serve --help 2>&1 || true)"

# --- Xác thực cho cầu nối, NẾU bản mcporter này hỗ trợ -----------------------
# `MCPORTER_BRIDGE_TOKEN` đã được cấp trong fleet-service-tokens từ lâu nhưng
# script này chưa bao giờ dùng tới. Một chốt bảo mật tồn tại trong secret mà
# không tồn tại trong luồng chạy còn nguy hiểm hơn là không có: người đọc cấu
# hình tưởng cầu nối có auth, và nới NetworkPolicy dựa trên niềm tin đó.
#
# Dò cờ theo đúng lối đã dùng cho --host/--bind bên dưới, thay vì đoán tên cờ.
# Nếu bản này không có auth thì NÓI THẲNG ra log — im lặng là cách để sáu tháng
# sau không ai còn nhớ rằng cách ly mạng là lớp bảo vệ DUY NHẤT ở đây.
TOKEN="${MCPORTER_BRIDGE_TOKEN:-}"
if [[ -n "$TOKEN" ]]; then
  if grep -qE -- '--auth-token' <<<"$HELP"; then
    SERVE_ARGS+=(--auth-token "$TOKEN")
    echo "[bridge] bật xác thực Bearer (--auth-token)"
  elif grep -qE -- '--token' <<<"$HELP"; then
    SERVE_ARGS+=(--token "$TOKEN")
    echo "[bridge] bật xác thực Bearer (--token)"
  else
    echo "[bridge] CẢNH BÁO: mcporter $(mcporter --version 2>/dev/null || echo '?') KHÔNG có cờ xác thực." >&2
    echo "[bridge] MCPORTER_BRIDGE_TOKEN đang được cấp nhưng KHÔNG có tác dụng." >&2
    echo "[bridge] Lớp bảo vệ DUY NHẤT của cầu nối lúc này là cách ly tầng mạng." >&2
    echo "[bridge] Đừng mở thêm ai vào cổng $PORT cho tới khi có xác thực thật." >&2
  fi
else
  echo "[bridge] CẢNH BÁO: chưa đặt MCPORTER_BRIDGE_TOKEN — cầu nối không xác thực." >&2
fi

if [[ "$BIND" == "127.0.0.1" || "$BIND" == "localhost" ]]; then
  echo "[bridge] nghe loopback :$PORT"
  exec mcporter serve --http "$PORT" "${SERVE_ARGS[@]}"

elif grep -qE -- '--host' <<<"$HELP"; then
  echo "[bridge] mcporter hỗ trợ --host → nghe $BIND:$PORT"
  exec mcporter serve --http "$PORT" --host "$BIND" "${SERVE_ARGS[@]}"

elif grep -qE -- '--bind' <<<"$HELP"; then
  echo "[bridge] mcporter hỗ trợ --bind → nghe $BIND:$PORT"
  exec mcporter serve --http "$PORT" --bind "$BIND" "${SERVE_ARGS[@]}"

else
  # Bản mcporter này chỉ nghe được loopback. Chạy nó ở cổng nội bộ rồi dùng
  # socat chuyển tiếp ra network của container. Một tiến trình phụ, không có
  # thư viện lạ, và giữ nguyên hành vi "không tự phơi ra ngoài" của mcporter.
  INNER=$((PORT + 1))
  echo "[bridge] mcporter chỉ nghe loopback → serve :$INNER, socat chuyển tiếp $BIND:$PORT"

  mcporter serve --http "$INNER" "${SERVE_ARGS[@]}" &
  MCP_PID=$!
  trap 'kill "$MCP_PID" 2>/dev/null || true' EXIT INT TERM

  for _ in $(seq 1 60); do
    if (exec 3<>"/dev/tcp/127.0.0.1/$INNER") 2>/dev/null; then exec 3<&- 3>&-; break; fi
    kill -0 "$MCP_PID" 2>/dev/null || { echo "[bridge] mcporter serve đã thoát" >&2; exit 1; }
    sleep 1
  done

  command -v socat >/dev/null || {
    echo "[bridge] LỖI: thiếu socat trong ảnh container. Thêm 'socat' vào Dockerfile.agent-runner." >&2
    exit 1
  }
  exec socat "TCP-LISTEN:$PORT,fork,reuseaddr,bind=$BIND" "TCP:127.0.0.1:$INNER"
fi
