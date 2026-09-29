#!/usr/bin/env bash
# =============================================================================
# generate-clis.sh — sinh CLI độc lập từ MCP server ("skill pattern")
# -----------------------------------------------------------------------------
# VẤN ĐỀ: nạp 200 tool MCP vào ngữ cảnh của agent là cách nhanh nhất để
# (a) đốt token, (b) làm model chọn nhầm tool, (c) chạm trần ngữ cảnh.
#
# GIẢI PHÁP: không đưa tool vào ngữ cảnh. Sinh ra một CLI nhỏ cho từng nhóm,
# rồi chỉ dạy agent MỘT câu: "cần dữ liệu GitHub thì chạy `fleet-github --help`".
# Agent tự đọc help khi cần — đây chính là "tiết lộ dần" (progressive disclosure).
#
# Cờ dưới đây đã đối chiếu với mcporter 0.13.8:
#   --output <path>          ghi mã nguồn TypeScript
#   --bundle <path>          ghi tệp JS chạy được (đây là thứ ta cần)
#   --include-tools a,b      chỉ sinh những tool này
#   --exclude-tools a,b      bỏ những tool này
# KHÔNG có --name và KHÔNG có --tools.
#
# Chạy lại mỗi khi mcporter.json đổi:  make capability
# =============================================================================
set -Eeuo pipefail

OUT="${FLEET_BIN_DIR:-$HOME/.local/bin}"
SRC="${FLEET_CLI_SRC_DIR:-$HOME/.local/share/fleet-clis}"
mkdir -p "$OUT" "$SRC"

command -v mcporter >/dev/null || { echo "Chưa cài mcporter." >&2; exit 1; }

gen () {
  local server="$1" name="$2" tools="${3:-}"
  local args=(generate-cli "$server" --output "$SRC/$name.ts" --bundle "$SRC/$name.mjs")
  [[ -n "$tools" ]] && args+=(--include-tools "$tools")

  echo "→ $name  ←  $server"
  if ! mcporter "${args[@]}" >/dev/null 2>&1; then
    echo "   bỏ qua: '$server' chưa kết nối được (thiếu credential, hoặc chưa 'mcporter auth $server')"
    return 0
  fi

  # Bọc một wrapper để gọi bằng tên ngắn, không cần nhớ đuôi .mjs
  cat > "$OUT/$name" <<EOF
#!/usr/bin/env bash
exec node "$SRC/$name.mjs" "\$@"
EOF
  chmod +x "$OUT/$name"
  echo "   ✓ $OUT/$name"
}

# Một CLI cho mỗi NHÓM NGHIỆP VỤ, không phải cho mỗi server.
# Cột thứ ba là danh sách tool (tên CHÍNH XÁC). Để trống = sinh toàn bộ tool.
# Xem tên thật bằng:  make tools S=<server>
gen context7          fleet-docs    "resolve-library-id,get-library-docs"
gen github            fleet-github
gen linear            fleet-issues
gen grafana           fleet-metrics
gen postgres-readonly fleet-query   "query"
gen fleet-internal    fleet-svc
gen notion            fleet-wiki
gen google-drive      fleet-drive

echo
echo "Xong. Kiểm tra:  $OUT/fleet-query --help"
echo "Nếu '$OUT' chưa nằm trong PATH:  export PATH=\"$OUT:\$PATH\""
echo "Nhắc agent dùng qua skill 'fleet-tooling' thay vì nạp toàn bộ tool MCP."
