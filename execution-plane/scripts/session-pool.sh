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

case "$CMD" in
  ensure)
    acpx claude sessions list --format json | grep -q "\"$NAME\"" \
      || acpx claude sessions new --name "$NAME" --cwd "$ARG"
    echo "$NAME" ;;
  ask)
    acpx claude -s "$NAME" "$ARG" --format quiet ;;
  rotate)
    acpx claude sessions export "$NAME" > "/var/log/fleet/${NAME}.json"
    acpx claude sessions rm "$NAME" ;;
  list)
    acpx claude sessions list ;;
  *) echo "lệnh không hợp lệ" >&2; exit 64 ;;
esac
