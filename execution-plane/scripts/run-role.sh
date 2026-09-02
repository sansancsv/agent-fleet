#!/usr/bin/env bash
# =============================================================================
# run-role.sh — chạy MỘT vai trò agent một lượt, đầu ra máy đọc được.
# -----------------------------------------------------------------------------
# Đây là "nguyên thuỷ" (primitive) mà n8n và LangGraph gọi vào.
# Mọi thứ phức tạp hơn đều được ghép từ script này.
#
# Dùng:
#   ./run-role.sh reviewer    /srv/repos/api "Xem diff so với origin/main"
#   ./run-role.sh implementer /srv/repos/api "$(cat task.md)" --write
#
# Trả về trên stdout: JSON một dòng
#   {"role":"reviewer","exit":0,"session":"...","text":"..."}
# NDJSON đầy đủ và stderr được giữ tại $FLEET_LOG_DIR/<role>/<session>.*
# =============================================================================
set -Eeuo pipefail

ROLE="${1:?thiếu vai trò (role)}"; shift
CWD="${1:?thiếu thư mục làm việc}"; shift
PROMPT="${1:?thiếu prompt}"; shift || true

# --- Ánh xạ vai trò -> backend agent + quyền ---------------------------------
# Cố ý cho reviewer/security dùng backend KHÁC implementer để tránh mù lỗi đồng nhất.
case "$ROLE" in
  orchestrator) AGENT=claude;  PERM=--approve-reads ;;
  architect)    AGENT=claude;  PERM=--approve-reads ;;
  implementer)  AGENT=claude;  PERM=--approve-all   ;;
  tester)       AGENT=claude;  PERM=--approve-all   ;;
  reviewer)     AGENT=codex;   PERM=--deny-all      ;;
  security)     AGENT=codex;   PERM=--deny-all      ;;
  docs-writer)  AGENT=gemini;  PERM=--approve-reads ;;
  sre)          AGENT=claude;  PERM=--approve-reads ;;
  analyst)      AGENT=gemini;  PERM=--deny-all      ;;
  *) echo "Vai trò không hợp lệ: $ROLE" >&2; exit 64 ;;
esac

# Cờ --write ghi đè quyền, nhưng phải truyền TƯỜNG MINH — không có mặc định ngầm.
for arg in "$@"; do
  [[ "$arg" == "--write" ]] && PERM=--approve-all
done

SESSION="${FLEET_SESSION:-${ROLE}-$(date +%s)-$$}"
LOG_DIR="${FLEET_LOG_DIR:-/var/log/fleet}/${ROLE}"
mkdir -p "$LOG_DIR"
NDJSON="$LOG_DIR/$SESSION.ndjson"
ERRLOG="$LOG_DIR/$SESSION.err"

# --format json --json-strict: stdout chỉ chứa NDJSON thông điệp ACP thô,
# mỗi dòng một thông điệp JSON-RPC → phân tích được bằng máy, không cần regex.
#
# THỨ TỰ THAM SỐ QUAN TRỌNG (đối chiếu acpx 0.13.2 — đọc trước khi sửa):
#   `acpx [tuỳ-chọn-toàn-cục] <agent> exec [prompt]`
# --cwd/--format/--deny-all/--approve-*/--json-strict/--suppress-reads là tuỳ
# chọn TOÀN CỤC của lệnh gốc `acpx`, KHÔNG phải của lệnh con `<agent> exec`.
# Đặt sau "$AGENT exec" sẽ bị từ chối: "error: unknown option '--cwd'" — subcommand
# `exec` của từng agent chỉ nhận `-f/--file` và `-h/--help`.
set +e
acpx --cwd "$CWD" \
  "$PERM" \
  --format json --json-strict \
  --suppress-reads \
  "$AGENT" exec "$PROMPT" \
  > "$NDJSON" 2> "$ERRLOG"
EXIT=$?
set -e

# Trích văn bản trả lời và đóng gói thành JSON — làm hoàn toàn trong Python
# để không phải chèn chuỗi vào shell (tránh lỗi trích dẫn và chèn lệnh).
FLEET_ROLE="$ROLE" FLEET_EXIT="$EXIT" FLEET_SESSION_ID="$SESSION" \
python3 - "$NDJSON" <<'PY'
import json, os, sys

chunks = []
try:
    with open(sys.argv[1], encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            update = (msg.get("params") or {}).get("update") or {}
            if update.get("sessionUpdate") == "agent_message_chunk":
                content = update.get("content") or {}
                if content.get("type") == "text":
                    chunks.append(content.get("text", ""))
except FileNotFoundError:
    pass

text = "".join(chunks)

# Trích khối fleet-status nếu agent tuân thủ hiến chương (xem _shared/AGENTS.md).
status = {}
if "```fleet-status" in text:
    block = text.split("```fleet-status", 1)[1].split("```", 1)[0]
    for row in block.splitlines():
        if ":" in row:
            k, _, v = row.partition(":")
            status[k.strip()] = v.strip()

print(json.dumps({
    "role": os.environ["FLEET_ROLE"],
    "exit": int(os.environ["FLEET_EXIT"]),
    "session": os.environ["FLEET_SESSION_ID"],
    "status": status,
    "text": text,
}, ensure_ascii=False))
PY

exit "$EXIT"
