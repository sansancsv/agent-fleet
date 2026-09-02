#!/usr/bin/env bash
# =============================================================================
# session-pool.sh — quản lý vòng đời phiên (session) dài hạn cho từng vai trò.
# -----------------------------------------------------------------------------
# Phiên có trạng thái = agent nhớ ngữ cảnh repo giữa các lượt → rẻ hơn và
# chính xác hơn so với exec một lượt. Nhưng phiên sống mãi sẽ phình ngữ cảnh,
# nên fleet xoay vòng phiên theo ngày.
#
# Dùng:
#   ./session-pool.sh ensure reviewer /srv/repos/api
#   ./session-pool.sh ask    reviewer "Xem lại file X"
#   ./session-pool.sh rotate reviewer
# =============================================================================
set -Eeuo pipefail
CMD="${1:?ensure|ask|rotate|list}"; ROLE="${2:-}"; ARG="${3:-}"
NAME="fleet-${ROLE}-$(date +%Y%m%d)"

# THỨ TỰ THAM SỐ (đối chiếu acpx 0.13.2): --cwd/--format là tuỳ chọn TOÀN CỤC
# của `acpx`, đứng TRƯỚC tên agent — `sessions new` không có cờ --cwd riêng,
# nó dùng cwd hiện tại của tiến trình (tức global --cwd). Xem run-role.sh.
case "$CMD" in
  ensure)
    acpx --format json claude sessions list --local | grep -q "\"$NAME\"" \
      || acpx --cwd "$ARG" claude sessions new --name "$NAME"
    echo "$NAME" ;;
  ask)
    acpx --format quiet claude -s "$NAME" "$ARG" ;;
  rotate)
    acpx claude sessions export "$NAME" > "/var/log/fleet/${NAME}.json"
    acpx claude sessions close "$NAME" ;;
  list)
    acpx claude sessions list --local ;;
  *) echo "lệnh không hợp lệ" >&2; exit 64 ;;
esac
