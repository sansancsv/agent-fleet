#!/usr/bin/env bash
# =============================================================================
# oc-validate.sh — kiểm chứng cấu hình OpenClaw bằng CHÍNH RUNTIME SẼ CHẠY NÓ
# -----------------------------------------------------------------------------
# Vì sao phải nói rõ "runtime sẽ chạy nó":
#   Schema của OpenClaw thay đổi giữa các phiên bản. Kiểm bằng CLI trên host là
#   sai nếu host cài bản khác với image container — và đó là chuyện rất dễ xảy
#   ra, vì `bootstrap.sh` bỏ qua việc cài khi thấy binary đã tồn tại, còn image
#   thì `docker compose pull` kéo bản mới. Kết quả: cấu hình "hợp lệ" theo CLI
#   host nhưng gateway vẫn từ chối khởi động (hoặc ngược lại).
#
# Vì vậy thứ tự ưu tiên là:
#   1. Container đang chạy       — đúng thứ đang phục vụ
#   2. Container tạm từ IMAGE    — đúng thứ SẼ phục vụ (dùng trước khi `make up`)
#   3. CLI trên host             — chỉ khi không có Docker, và có CẢNH BÁO
#
# Chạy:  make oc-validate
# =============================================================================
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'
COMPOSE_FILE=deploy/docker/docker-compose.yml

# Tag image thật sự dùng — đọc từ .env, mặc định như compose.
OPENCLAW_TAG="$(grep -E '^OPENCLAW_TAG=' .env 2>/dev/null | cut -d= -f2- || true)"
OPENCLAW_TAG="${OPENCLAW_TAG:-latest}"
IMAGE="ghcr.io/openclaw/openclaw:${OPENCLAW_TAG}"

prepare_tmp () {
  TMP="$(mktemp -d)"
  mkdir -p "$TMP/.openclaw"
  cp control-plane/openclaw.json "$TMP/.openclaw/"
  cp -r control-plane/config.d "$TMP/.openclaw/"
  # Bản sao dùng một lần rồi xoá; để 644 cho user trong container đọc được.
  chmod -R a+r "$TMP/.openclaw"
  chmod a+rx "$TMP" "$TMP/.openclaw" "$TMP/.openclaw/config.d"
}

# Có binary docker chưa đủ — daemon phải chạy được. `docker info` là phép thử đúng.
HAS_DOCKER=0
command -v docker >/dev/null 2>&1 && timeout 15 docker info >/dev/null 2>&1 && HAS_DOCKER=1

RUNNER=""
if (( HAS_DOCKER )) && docker compose -f "$COMPOSE_FILE" ps --status running openclaw-gateway 2>/dev/null | grep -q openclaw; then
  RUNNER="container-running"
elif (( HAS_DOCKER )) && docker image inspect "$IMAGE" >/dev/null 2>&1; then
  RUNNER="container-image"
elif (( HAS_DOCKER )); then
  RUNNER="container-pull"
elif command -v openclaw >/dev/null 2>&1; then
  RUNNER="host"
else
  echo "${C_WARN}!${C_OFF} Không có Docker và cũng không có openclaw trên máy — bỏ qua kiểm chứng."
  exit 0
fi

case "$RUNNER" in
  container-running)
    VER=$(docker compose -f "$COMPOSE_FILE" exec -T openclaw-gateway openclaw --version 2>/dev/null | head -1)
    echo "Kiểm chứng bằng container đang chạy — ${VER}"
    OUT="$(docker compose -f "$COMPOSE_FILE" exec -T openclaw-gateway openclaw config validate 2>&1)" || true
    ;;
  container-image|container-pull)
    [[ "$RUNNER" == "container-pull" ]] && { echo "Kéo image ${IMAGE}…"; timeout 600 docker pull -q "$IMAGE" >/dev/null 2>&1 || true; }
    prepare_tmp; trap 'rm -rf "$TMP"' EXIT
    VER=$(docker run --rm "$IMAGE" openclaw --version 2>/dev/null | head -1)
    echo "Kiểm chứng bằng image sẽ chạy (${IMAGE}) — ${VER}"
    OUT="$(docker run --rm -v "$TMP/.openclaw:/home/node/.openclaw:ro" "$IMAGE" \
             openclaw config validate 2>&1)" || true
    ;;
  host)
    prepare_tmp; trap 'rm -rf "$TMP"' EXIT
    VER=$(openclaw --version 2>/dev/null | head -1)
    echo "${C_WARN}!${C_OFF} Không có Docker — kiểm bằng CLI trên host (${VER})."
    echo "${C_DIM}  Nếu image container là phiên bản khác, kết quả ở đây KHÔNG đại diện${C_OFF}"
    echo "${C_DIM}  cho thứ gateway thật sự chấp nhận.${C_OFF}"
    OUT="$(HOME="$TMP" openclaw config validate 2>&1)" || true
    ;;
esac

echo "$OUT" | grep -v '^\[config\]' | sed 's/^/  /'

if grep -q "Config valid" <<<"$OUT"; then
  echo
  echo "${C_OK}Cấu hình hợp lệ${C_OFF} ${C_DIM}(cảnh báo \"Missing env var\" là bình thường —"
  echo "biến được tiêm lúc chạy qua docker-compose)${C_OFF}"

  # Cảnh báo lệch phiên bản: CLI host cũ hơn image là nguồn của những lỗi
  # "Invalid input" khó hiểu khi người ta chạy openclaw bằng tay.
  if [[ "$RUNNER" != "host" ]] && command -v openclaw >/dev/null 2>&1; then
    HOSTVER=$(openclaw --version 2>/dev/null | head -1)
    if [[ -n "$VER" && "$HOSTVER" != "$VER" ]]; then
      echo
      echo "${C_WARN}!${C_OFF} CLI trên host là ${HOSTVER}, còn runtime là ${VER}."
      echo "  Chạy 'openclaw ...' bằng tay có thể cho kết quả khác. Đồng bộ bằng:"
      echo "    npm install -g openclaw@latest --allow-scripts=openclaw"
    fi
  fi
  exit 0
fi

echo
echo "${C_ERR}Cấu hình KHÔNG hợp lệ — gateway sẽ từ chối khởi động.${C_OFF}"
echo
echo "Nếu thông báo chỉ nói cụt lủn \"Invalid input\", nhiều khả năng phiên bản đang"
echo "kiểm khác với phiên bản cấu hình này nhắm tới. Xem chi tiết hơn:"
echo "  openclaw config validate --json"
echo "Tra schema thật của đúng phiên bản đó:"
echo "  openclaw config schema | jq '.properties.<khối>.properties | keys'"
echo
echo "ĐỪNG chạy 'openclaw doctor --fix' trên cấu hình trong git: nó sửa tại chỗ và"
echo "âm thầm bỏ những khoá bạn cố ý đặt. Sửa tay theo thông báo lỗi."
exit 1
