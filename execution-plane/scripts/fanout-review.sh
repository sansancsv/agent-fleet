#!/usr/bin/env bash
# =============================================================================
# fanout-review.sh — thẩm định SONG SONG bằng nhiều model, rồi hợp nhất.
# -----------------------------------------------------------------------------
# Vì sao cần: một model bỏ sót loại lỗi nào thì nó bỏ sót ổn định.
# Ba model khác nhà cung cấp cùng soi một diff cho vùng phủ lỗi rộng hơn nhiều
# so với gọi cùng một model ba lần.
#
# Dùng:  ./fanout-review.sh /srv/repos/api
# =============================================================================
set -Eeuo pipefail
CWD="${1:?thiếu thư mục repo}"
OUT="$(mktemp -d)"
PROMPT='Vai trò Reviewer. CHỈ ĐỌC. Xem diff so với origin/main.
Mỗi phát hiện: file:dòng | mức độ (BLOCKER|MAJOR|MINOR|NIT) | kịch bản hỏng cụ thể.
Không nêu ý kiến thẩm mỹ. Không bịa phát hiện.'

# THỨ TỰ THAM SỐ (đối chiếu acpx 0.13.2): --cwd/--deny-all/--format là tuỳ chọn
# TOÀN CỤC của `acpx`, phải đứng TRƯỚC tên agent. Đặt sau "$A exec" bị từ chối
# "unknown option '--cwd'" — xem chú thích trong run-role.sh.
for A in codex gemini claude; do
  (
    acpx --cwd "$CWD" --deny-all --format quiet "$A" exec "$PROMPT" \
      > "$OUT/$A.txt" 2>"$OUT/$A.err" || echo "(backend $A lỗi)" > "$OUT/$A.txt"
  ) &
done
wait

# Hợp nhất bằng một model thứ tư: loại trùng, xếp hạng, bỏ phát hiện không có bằng chứng.
# `-f -` đọc prompt từ stdin — vị trí (bare "-") không được exec hiểu là stdin.
{
  echo "Hợp nhất ba bản thẩm định độc lập dưới đây thành MỘT danh sách."
  echo "Quy tắc: gộp mục trùng; giữ mức cao nhất; LOẠI mục không có file:dòng cụ thể;"
  echo "đánh dấu [đồng thuận N/3] cho mỗi mục."
  for A in codex gemini claude; do
    echo; echo "<review source=\"$A\">"; cat "$OUT/$A.txt"; echo "</review>"
  done
} | acpx --cwd "$CWD" --deny-all --format quiet claude exec -f -

rm -rf "$OUT"
