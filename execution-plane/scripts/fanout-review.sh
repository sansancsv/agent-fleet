#!/usr/bin/env bash
# =============================================================================
# fanout-review.sh — thẩm định SONG SONG bằng nhiều model, rồi hợp nhất.
# -----------------------------------------------------------------------------
# Vì sao cần: một model bỏ sót loại lỗi nào thì nó bỏ sót ổn định.
# Ba model khác nhà cung cấp cùng soi một diff cho vùng phủ lỗi rộng hơn nhiều
# so với gọi cùng một model ba lần.
#
# Diff được CHÍNH SCRIPT này chạy (git ở đây có toàn quyền, không phải agent)
# rồi nhúng thẳng vào prompt qua stdin. Lý do: reviewer chạy với --deny-all
# (không được chạy lệnh gì, kể cả git diff) để giữ đúng nghĩa "chỉ đọc" ở tầng
# tool, không chỉ ở tầng lời văn prompt — nếu để agent tự gọi `git diff`, nó
# cần quyền chạy lệnh và --deny-all sẽ chặn ngay từ bước đó (PERMISSION_DENIED).
#
# Dùng:  ./fanout-review.sh /srv/repos/api
# =============================================================================
set -Eeuo pipefail
CWD="${1:?thiếu thư mục repo}"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

# Nhánh mặc định thật của remote (origin/main hoặc origin/master...), không
# đoán cứng "main" — nhiều repo (kể cả tạo trước 2020) vẫn dùng "master".
BASE_REF="$(git -C "$CWD" symbolic-ref -q --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
DIFF="$(git -C "$CWD" diff "${BASE_REF}...HEAD" 2>&1)"

if [[ -z "$DIFF" ]]; then
  echo "Không có thay đổi nào so với ${BASE_REF} — không có gì để thẩm định." >&2
  exit 0
fi

PROMPT_HEADER='Vai trò Reviewer. CHỈ ĐỌC. Diff dưới đây đã được trích sẵn — không cần và
không thể chạy git (không có quyền chạy lệnh), chỉ đọc nội dung diff mà đánh giá.
Mỗi phát hiện: file:dòng | mức độ (BLOCKER|MAJOR|MINOR|NIT) | kịch bản hỏng cụ thể.
Không nêu ý kiến thẩm mỹ. Không bịa phát hiện.'

for A in codex gemini claude; do
  (
    { echo "$PROMPT_HEADER"; echo; echo "So với ${BASE_REF}:"; echo '```diff'; echo "$DIFF"; echo '```'; } \
      | acpx --cwd "$CWD" --deny-all --format quiet "$A" exec -f - \
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
