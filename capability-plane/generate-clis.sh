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
# =============================================================================
set -Eeuo pipefail
OUT="${FLEET_BIN_DIR:-/usr/local/bin}"

gen () {
  local server="$1"; local name="$2"; shift 2
  echo "→ sinh CLI '$name' từ server '$server'"
  mcporter generate-cli "$server" \
    --name "$name" \
    --out "$OUT/$name" \
    ${*:+--tools "$*"}
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
echo "Xong. Kiểm tra:  fleet-github --help"
echo "Nhắc agent dùng qua skill 'fleet-tooling' thay vì nạp toàn bộ tool MCP."
