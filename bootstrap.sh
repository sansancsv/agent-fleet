#!/usr/bin/env bash
# =============================================================================
# bootstrap.sh — dựng Agent Fleet từ số 0
# -----------------------------------------------------------------------------
# Chạy được nhiều lần (idempotent): mỗi bước tự kiểm tra trước khi làm.
# =============================================================================
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_OFF=$'\033[0m'
ok ()   { echo "${C_OK}✓${C_OFF} $*"; }
warn () { echo "${C_WARN}!${C_OFF} $*"; }
die ()  { echo "${C_ERR}✗${C_OFF} $*" >&2; exit 1; }

echo "=== Agent Fleet · bootstrap ==="

# --- 1. Điều kiện tiên quyết ------------------------------------------------
echo; echo "1) Kiểm tra công cụ cần có"
need () { command -v "$1" >/dev/null 2>&1 && ok "$1" || die "thiếu $1 — $2"; }
need docker "cài Docker Engine + Compose v2"
need node   "cài Node.js 24+ (nvm install 24)"
need python3 "cài Python 3.12+"
need git    "cài git"
need jq     "cài jq"

NODE_MAJOR=$(node -p "process.versions.node.split('.')[0]")
(( NODE_MAJOR >= 22 )) || die "cần Node >= 22 (đang có $NODE_MAJOR)"
ok "Node $(node -v)"

command -v yq  >/dev/null || warn "thiếu yq — cần cho flow theo hồ sơ phòng ban"
command -v opa >/dev/null || warn "thiếu opa — không chạy được test chính sách"
command -v gh  >/dev/null || warn "thiếu gh — không tự mở PR được"

# --- 2. Công cụ fleet -------------------------------------------------------
echo; echo "2) Cài công cụ fleet (toàn cục)"
install_npm () {
  if command -v "$1" >/dev/null 2>&1; then ok "$1 đã có ($("$1" --version 2>/dev/null | head -1))"
  else echo "   cài $2..."; npm install -g "$2" >/dev/null && ok "$1 đã cài"; fi
}
install_npm acpx     acpx@latest
install_npm mcporter mcporter@latest
install_npm clawhub  clawhub@latest
install_npm openclaw "openclaw@latest --allow-scripts=openclaw"

# --- 3. Tệp môi trường ------------------------------------------------------
echo; echo "3) Tệp môi trường"
if [[ -f .env ]]; then ok ".env đã có (không ghi đè)"
else
  cp .env.example .env
  gen () { openssl rand -hex 32; }
  for KEY in OPENCLAW_GATEWAY_TOKEN MCPORTER_BRIDGE_TOKEN HOOK_SECRET_N8N \
             HOOK_SECRET_GITHUB HOOK_TOKEN_ALERTS LANGGRAPH_TOKEN \
             N8N_ENCRYPTION_KEY PG_PASSWORD; do
    V=$(gen); sed -i.bak "s|^${KEY}=.*|${KEY}=${V}|" .env && rm -f .env.bak
  done
  chmod 600 .env
  ok ".env đã tạo, khoá nội bộ sinh ngẫu nhiên"
  warn "CẦN LÀM: điền ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY và các token tích hợp"
fi

# --- 4. Quyền thư mục -------------------------------------------------------
echo; echo "4) Quyền thư mục"
chmod 700 control-plane 2>/dev/null || true
find . -name '*.sh' -exec chmod +x {} \;
# `openclaw security audit` coi tệp cấu hình 644 là CRITICAL: chúng có thể chứa
# token và thiết lập riêng tư. Git không giữ được quyền này nên phải đặt lại ở đây.
chmod 600 control-plane/openclaw.json control-plane/config.d/*.json 2>/dev/null || true
ok "script có quyền chạy, cấu hình đặt quyền 600"

# --- 5. Kiểm chứng cấu hình -------------------------------------------------
echo; echo "5) Kiểm chứng cấu hình"
./scripts/validate.sh || die "cấu hình chưa hợp lệ — sửa xong chạy lại"

# --- 6. Hướng dẫn tiếp theo -------------------------------------------------
cat <<'NEXT'

=== Bootstrap xong ===

Việc cần làm tiếp, theo đúng thứ tự:

  1. Điền khoá API vào .env
       ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY

  2. Khởi động ngăn xếp
       make up

  3. Kiểm tra sức khoẻ
       make health

  4. Xem đội hình agent và luật định tuyến
       make agents

  5. Sinh CLI công cụ từ MCP server
       make capability

  6. Nhập workflow n8n
       make import-workflows
       Mở http://localhost:5678

  7. Rà soát bảo mật trước khi cho người thật dùng
       make audit

  8. Chạy thử một vòng đầy đủ
       make demo-flow

Tài liệu: docs/ (tiếng Việt)
NEXT
