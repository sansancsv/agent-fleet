#!/usr/bin/env bash
# =============================================================================
# validate.sh — kiểm tra cú pháp và TÍNH NHẤT QUÁN của mọi cấu hình
# -----------------------------------------------------------------------------
# Kiểm tra tính nhất quán quan trọng hơn kiểm tra cú pháp: cấu hình đúng cú pháp
# nhưng mâu thuẫn giữa các tầng là cách mà quyền bị rò ra trong thực tế.
# =============================================================================
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

FAIL=0
C_OK=$'\033[32m'; C_ERR=$'\033[31m'; C_OFF=$'\033[0m'
pass () { echo "${C_OK}✓${C_OFF} $*"; }
fail () { echo "${C_ERR}✗${C_OFF} $*"; FAIL=1; }

echo "=== Kiểm chứng cấu hình Agent Fleet ==="

# --- 1. JSON5 / JSONC (cho phép comment) ------------------------------------
echo; echo "1) Cấu hình OpenClaw (JSON5)"
for f in control-plane/openclaw.json control-plane/config.d/*.json; do
  if python3 scripts/json5_to_json.py "$f" >/dev/null 2>&1; then pass "$f"
  else fail "$f — JSON5 không hợp lệ: $(python3 scripts/json5_to_json.py "$f" 2>&1 | tail -1)"; fi
done

# --- 2. JSON thuần -----------------------------------------------------------
echo; echo "2) Cấu hình JSON"
for f in capability-plane/mcporter.json capability-plane/packs/*.json \
         execution-plane/config/acpx.global.json execution-plane/config/.acpxrc.json \
         orchestration/n8n/workflows/*.json orchestration/langgraph/langgraph.json; do
  [[ -f "$f" ]] || continue
  if jq -e . "$f" >/dev/null 2>&1; then pass "$f"; else fail "$f — JSON không hợp lệ"; fi
done

# --- 3. YAML -----------------------------------------------------------------
echo; echo "3) YAML"
for f in profiles/*.yaml policy/*.yaml deploy/k8s/*.yaml deploy/docker/docker-compose.yml; do
  [[ -f "$f" ]] || continue
  if python3 -c "
import sys,yaml
list(yaml.safe_load_all(open('$f',encoding='utf-8')))
" 2>/dev/null; then pass "$f"; else fail "$f — YAML không hợp lệ"; fi
done

# --- 4. Script shell ---------------------------------------------------------
echo; echo "4) Cú pháp shell"
while IFS= read -r f; do
  if bash -n "$f" 2>/dev/null; then pass "$f"; else fail "$f — lỗi cú pháp"; fi
done < <(find . -name '*.sh' -not -path './node_modules/*')

# --- 5. Python ---------------------------------------------------------------
echo; echo "5) Cú pháp Python"
while IFS= read -r f; do
  if python3 -m py_compile "$f" 2>/dev/null; then pass "$f"; else fail "$f — lỗi cú pháp"; fi
done < <(find orchestration/langgraph -name '*.py')

# --- 6. NHẤT QUÁN: vai trò trong openclaw phải khớp policy và script ---------
echo; echo "6) Nhất quán vai trò giữa các tầng"
ROLES_OC=$(python3 scripts/json5_to_json.py control-plane/config.d/agents.json \
  | python3 -c "import json,sys; print(','.join(sorted(json.load(sys.stdin)['agents']['entries'])))")
ROLES_POLICY=$(python3 -c "
import yaml
d=yaml.safe_load(open('policy/tool-policy.yaml',encoding='utf-8'))
print(','.join(sorted(d['roles'].keys())))
")
if [[ "$ROLES_OC" == "$ROLES_POLICY" ]]; then
  pass "vai trò khớp giữa openclaw và tool-policy ($ROLES_OC)"
else
  fail "vai trò LỆCH: openclaw=[$ROLES_OC] policy=[$ROLES_POLICY]"
fi

# --- 7. NHẤT QUÁN: hồ sơ phòng ban trỏ tới gói năng lực có thật -------------
echo; echo "7) Hồ sơ phòng ban ↔ gói năng lực"
for f in profiles/*.yaml; do
  base=$(basename "$f" .yaml); [[ "$base" == _schema ]] && continue
  pack=$(python3 -c "import yaml;print(yaml.safe_load(open('$f',encoding='utf-8')).get('capabilityPack',''))")
  if [[ -f "capability-plane/packs/$pack.json" ]]; then pass "$base → packs/$pack.json"
  else fail "$base trỏ tới gói không tồn tại: $pack"; fi
done

# --- 8. NHẤT QUÁN: thẩm định chéo phải khác nhà cung cấp --------------------
echo; echo "8) Đa dạng hoá nhà cung cấp khi thẩm định chéo"
for f in profiles/*.yaml; do
  base=$(basename "$f" .yaml); [[ "$base" == _schema ]] && continue
  read -r drafter reviewer dc < <(python3 -c "
import yaml
d=yaml.safe_load(open('$f',encoding='utf-8'))
a=d.get('agents',{})
print(a.get('drafter',''), a.get('reviewer',''), d.get('dataClass',''))
")
  if [[ "$dc" == "restricted" ]]; then
    pass "$base — dữ liệu hạn chế, chấp nhận cùng backend nội bộ"
  elif [[ "$drafter" == "$reviewer" ]]; then
    fail "$base — drafter và reviewer cùng là '$drafter' (mù lỗi đồng nhất)"
  else
    pass "$base — $drafter soạn, $reviewer thẩm định"
  fi
done

# --- 9. Không có secret bị lộ trong git -------------------------------------
echo; echo "9) Quét secret bị commit"
if grep -rInE '(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{30,}|xox[bap]-[0-9]{10,})' \
     --include='*.json' --include='*.yaml' --include='*.yml' --include='*.sh' \
     --include='*.ts' --include='*.py' . 2>/dev/null; then
  fail "phát hiện secret trong mã nguồn — gỡ ngay và xoay vòng khoá"
else
  pass "không thấy secret bị commit"
fi

# --- 10. .env không được nằm trong git --------------------------------------
echo; echo "10) Vệ sinh .env"
if [[ -f .env ]] && git check-ignore -q .env 2>/dev/null; then pass ".env đã được gitignore"
elif [[ ! -f .env ]]; then pass "chưa có .env (bootstrap sẽ tạo)"
else fail ".env KHÔNG được gitignore — thêm ngay vào .gitignore"; fi

echo
if (( FAIL )); then echo "${C_ERR}KIỂM CHỨNG THẤT BẠI${C_OFF}"; exit 1; fi
echo "${C_OK}Mọi kiểm tra đã qua${C_OFF}"
