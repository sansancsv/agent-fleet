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
# Chạy lại mỗi khi mcporter.json đổi:  make capability
#
# LƯU Ý: bộ cờ của `mcporter generate-cli` thay đổi theo phiên bản. Script này
# đọc `--help` của bản THẬT đã cài rồi mới dựng dòng lệnh, thay vì giả định.
# Nếu không khớp, nó in ra help và dừng — không chạy lệnh sai rồi báo lỗi khó hiểu.
# =============================================================================
set -Eeuo pipefail

OUT="${FLEET_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$OUT"

command -v mcporter >/dev/null || { echo "Chưa cài mcporter." >&2; exit 1; }

HELP="$(mcporter generate-cli --help 2>&1 || true)"
if grep -qiE 'unknown (command|subcommand)' <<<"$HELP"; then
  echo "Bản mcporter đã cài không có 'generate-cli'. Bỏ qua bước này;" >&2
  echo "agent vẫn gọi tool được qua cầu nối MCP. Chạy 'mcporter --help' để xem lệnh có sẵn." >&2
  exit 0
fi

flag () { grep -qE -- "(^|[[:space:],])$1([[:space:],=]|$)" <<<"$HELP"; }

# Dò tên cờ đặt tên đầu ra — khác nhau giữa các bản.
NAME_FLAG=""
for f in --name --bin --command; do flag "$f" && { NAME_FLAG="$f"; break; }; done
OUT_FLAG=""
for f in --out --output --out-dir --outfile; do flag "$f" && { OUT_FLAG="$f"; break; }; done
TOOLS_FLAG=""
for f in --tools --only --include; do flag "$f" && { TOOLS_FLAG="$f"; break; }; done

if [[ -z "$OUT_FLAG" ]]; then
  echo "Không nhận ra cờ chỉ định đầu ra của 'mcporter generate-cli' trên bản này." >&2
  echo "----- mcporter generate-cli --help -----" >&2
  echo "$HELP" >&2
  echo "----------------------------------------" >&2
  echo "Gửi phần help ở trên để chỉnh script cho đúng phiên bản của bạn." >&2
  exit 2
fi

gen () {
  local server="$1" name="$2"; shift 2
  local args=(generate-cli "$server" "$OUT_FLAG" "$OUT/$name")
  [[ -n "$NAME_FLAG"  ]] && args+=("$NAME_FLAG" "$name")
  [[ -n "$TOOLS_FLAG" && $# -gt 0 ]] && args+=("$TOOLS_FLAG" "$*")
  echo "→ sinh CLI '$name' từ server '$server'"
  mcporter "${args[@]}" || echo "  (bỏ qua: '$server' chưa kết nối được)"
}

# Một CLI cho mỗi NHÓM NGHIỆP VỤ, không phải cho mỗi server.
gen github            fleet-github
gen linear            fleet-issues
gen context7          fleet-docs
gen grafana           fleet-metrics
gen postgres-readonly fleet-query
gen fleet-internal    fleet-svc
gen notion            fleet-wiki
gen google-drive      fleet-drive

echo
echo "Xong. Kiểm tra:  $OUT/fleet-github --help"
echo "Nhắc agent dùng qua skill 'fleet-tooling' thay vì nạp toàn bộ tool MCP."
