#!/usr/bin/env bash
# =============================================================================
# oc-validate.sh — kiểm chứng cấu hình OpenClaw bằng CHÍNH binary OpenClaw
# -----------------------------------------------------------------------------
# Vì sao cần script riêng thay vì chỉ kiểm cú pháp JSON:
#   Schema của OpenClaw là NGHIÊM NGẶT. Một khoá thừa, một giá trị sai kiểu, hay
#   một SecretRef thiếu trường `provider` đều làm gateway TỪ CHỐI KHỞI ĐỘNG.
#   Kiểm bằng mắt hay bằng JSON schema tự chép lại đều không đủ — chỉ có chính
#   binary mới biết phiên bản này chấp nhận gì.
#
# Script chạy validate trên một BẢN SAO trong thư mục tạm, nên không đụng tới
# cấu hình OpenClaw thật của máy bạn.
#
# Chạy:  make oc-validate
# =============================================================================
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_DIM=$'\033[2m'; C_OFF=$'\033[0m'

# --- 1. Ưu tiên binary trên máy; nếu không có thì mượn container ------------
if command -v openclaw >/dev/null 2>&1; then
  RUNNER="host"
elif docker compose -f deploy/docker/docker-compose.yml ps openclaw-gateway 2>/dev/null | grep -q .; then
  RUNNER="container"
else
  echo "${C_WARN}!${C_OFF} Không tìm thấy openclaw trên máy và container cũng chưa chạy."
  echo "  Cài:  npm install -g openclaw@latest --allow-scripts=openclaw   (cần Node >= 22.22.3)"
  echo "  Hoặc: make up   rồi chạy lại lệnh này."
  exit 0
fi

echo "Kiểm chứng cấu hình OpenClaw (${RUNNER})…"

if [[ "$RUNNER" == "host" ]]; then
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  # Dùng HOME tạm: đó là cách chắc chắn để không đụng ~/.openclaw thật của máy.
  mkdir -p "$TMP/.openclaw"
  cp control-plane/openclaw.json "$TMP/.openclaw/"
  cp -r control-plane/config.d "$TMP/.openclaw/"
  chmod 600 "$TMP/.openclaw/openclaw.json" "$TMP/.openclaw/config.d/"*.json
  OUT="$(HOME="$TMP" openclaw config validate 2>&1)" || true
else
  OUT="$(docker compose -f deploy/docker/docker-compose.yml exec -T openclaw-gateway \
          openclaw config validate 2>&1)" || true
fi

echo "$OUT" | sed 's/^/  /'

if grep -q "Config valid" <<<"$OUT"; then
  WARNS=$(grep -c '^\s*!' <<<"$OUT" || true)
  echo
  echo "${C_OK}Cấu hình hợp lệ${C_OFF} ${C_DIM}(${WARNS} cảnh báo)${C_OFF}"
  echo "${C_DIM}Cảnh báo \"Missing env var\" là bình thường khi chạy ngoài container —"
  echo "biến được tiêm lúc chạy qua docker-compose.${C_OFF}"
  exit 0
fi

echo
echo "${C_ERR}Cấu hình KHÔNG hợp lệ — gateway sẽ từ chối khởi động.${C_OFF}"
echo "Tra schema thật để biết khoá nào hợp lệ:"
echo "  openclaw config schema | jq '.properties.<khối>.properties | keys'"
echo "ĐỪNG chạy 'openclaw doctor --fix' trên cấu hình trong git: nó sửa tại chỗ và"
echo "âm thầm bỏ những khoá bạn cố ý đặt. Sửa tay theo thông báo lỗi ở trên."
exit 1
