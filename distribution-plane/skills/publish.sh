#!/usr/bin/env bash
# =============================================================================
# publish.sh — xuất bản skill nội bộ lên ClawHub
# -----------------------------------------------------------------------------
# ClawHub công khai là "mở theo mặc định": ai cũng tải lên được.
# => Với skill chứa quy trình nội bộ, DÙNG REGISTRY RIÊNG (CLAWHUB_REGISTRY_URL)
#    hoặc phân phối qua git riêng tư:
#       openclaw skills install git:cong-ty/fleet-skills@v1.2.0
#
# Chạy:  ./publish.sh 1.2.0
# =============================================================================
set -Eeuo pipefail
VERSION="${1:?thiếu số phiên bản, ví dụ 1.2.0}"
: "${CLAWHUB_TOKEN:?cần CLAWHUB_TOKEN}"

clawhub login --token "$CLAWHUB_TOKEN" ${CLAWHUB_REGISTRY_URL:+--registry "$CLAWHUB_REGISTRY_URL"}

for dir in */ ; do
  slug="${dir%/}"
  [[ -f "$slug/SKILL.md" ]] || continue
  name=$(grep -m1 '^description:' "$slug/SKILL.md" | cut -c14- | cut -c1-60)
  echo "→ xuất bản $slug@$VERSION"
  clawhub skill publish "./$slug" \
    --slug "$slug" \
    --name "$slug" \
    --version "$VERSION" \
    --tag fleet --tag internal \
    --changelog "Xem CHANGELOG.md"
done

echo
echo "Cài trên máy khác:  openclaw skills install @cong-ty/fleet-code-review"
echo "Ghim phiên bản:     openclaw skills pin @cong-ty/fleet-code-review@$VERSION"
