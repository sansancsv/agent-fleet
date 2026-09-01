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

# --- 6b. OpenClaw: gateway.bind là ENUM, không phải địa chỉ IP --------------
echo; echo "6b) OpenClaw — giá trị gateway.bind"
BIND=$(python3 scripts/json5_to_json.py control-plane/openclaw.json \
  | python3 -c "import json,sys; print((json.load(sys.stdin).get('gateway') or {}).get('bind',''))")
BIND_VAL="${BIND#*:-}"; BIND_VAL="${BIND_VAL%\}}"
case "$BIND_VAL" in
  loopback|lan|tailnet|auto|custom) pass "gateway.bind mặc định = '$BIND_VAL'" ;;
  *) fail "gateway.bind = '$BIND_VAL' không hợp lệ. Chỉ nhận: loopback | lan | tailnet | auto | custom (KHÔNG phải địa chỉ IP)" ;;
esac
# Trong bản Docker, bind phải cho phép container khác gọi tới.
case "$BIND_VAL" in
  lan|auto|tailnet|custom) pass "bind='$BIND_VAL' — container khác gọi tới gateway được" ;;
  loopback) fail "bind=loopback: gateway chỉ nghe 127.0.0.1 BÊN TRONG container, n8n/langgraph sẽ không gọi tới được. Dùng 'lan'." ;;
esac
if grep -q 'OPENCLAW_GATEWAY_BIND' deploy/docker/docker-compose.yml 2>/dev/null \
   && ! grep -q '# LƯU Ý: gateway.bind KHÔNG đọc từ biến môi trường' deploy/docker/docker-compose.yml; then
  fail "compose vẫn đặt OPENCLAW_GATEWAY_BIND — biến này KHÔNG có tác dụng; bind chỉ đọc từ openclaw.json"
fi

# --- 6c. OpenClaw KHÔNG thay thế ${BIẾN} (trừ khối `mcp`) ------------------
# Đây là lớp lỗi đắt nhất đã gặp: cấu hình đúng cú pháp JSON, gateway vẫn chết,
# và thông báo lỗi không hề nhắc tới biến môi trường.
#   • ngoài khối `mcp`: giá trị bị đọc NGUYÊN VĂN → "${X}" thành chuỗi "${X}"
#   • trong khối `mcp`: có thay thế ${X}, nhưng KHÔNG có ${X:-mặc-định}
echo; echo "6c) OpenClaw — không dùng \${BIẾN} sai chỗ"
OC_BAD=0
for f in control-plane/openclaw.json control-plane/config.d/*.json; do
  # Chỉ bỏ dòng chú thích NGUYÊN DÒNG. Không dùng 's|//.*||' vì nó sẽ cắt luôn
  # phần sau "https://" và làm lọt mất lỗi trong các URL.
  HITS=$(sed 's|^[[:space:]]*//.*$||' "$f" | grep -oE '\$\{[^}]*\}' | sort -u || true)
  [[ -z "$HITS" ]] && continue
  if [[ "$(basename "$f")" == "mcp.json" ]]; then
    while IFS= read -r h; do
      [[ -z "$h" ]] && continue
      if [[ "$h" == *":-"* ]]; then
        fail "$f: '$h' — khối mcp không hỗ trợ cú pháp \${BIẾN:-mặc-định}"; OC_BAD=1
      fi
    done <<< "$HITS"
  else
    fail "$f: cấu hình ngoài khối mcp bị đọc nguyên văn, bỏ \${BIẾN} đi:"
    echo "$HITS" | sed 's/^/     /'; OC_BAD=1
  fi
done
(( OC_BAD )) || pass "không có \${BIẾN} sai chỗ trong cấu hình OpenClaw"

# `env.vars` viết literal sẽ GHI ĐÈ khoá API thật mà Docker tiêm vào.
if python3 scripts/json5_to_json.py control-plane/openclaw.json \
   | python3 -c "import json,sys; sys.exit(0 if (json.load(sys.stdin).get('env') or {}).get('vars') else 1)" 2>/dev/null; then
  fail "openclaw.json khai báo env.vars — nó ghi thẳng ra biến môi trường và sẽ ghi đè khoá API do Docker tiêm vào. Bỏ khối này đi."
else
  pass "không khai báo env.vars (khoá API đến từ Docker/K8s)"
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

# --- 8b. mcporter: đối chiếu với SCHEMA THẬT của bản đã cài -----------------
# Đây là phép kiểm tra đắt giá nhất trong script: nó bắt đúng loại lỗi chỉ lộ ra
# lúc container khởi động (khoá chú thích trong mcpServers, lifecycle thiếu
# `mode`, biến môi trường không có giá trị mặc định, glob trong danh sách tool).
echo; echo "8b) mcporter — schema và quy ước"
MP_CFG=capability-plane/mcporter.json

if command -v mcporter >/dev/null 2>&1; then
  MP_SCHEMA="$(dirname "$(readlink -f "$(command -v mcporter)")")/../dist/config-schema.js"
  if [[ -f "$MP_SCHEMA" ]]; then
    if OUTPUT=$(node -e "
      const { RawConfigSchema } = require('$MP_SCHEMA');
      const cfg = JSON.parse(require('fs').readFileSync('$MP_CFG', 'utf8'));
      const r = RawConfigSchema.safeParse(cfg);
      if (!r.success) {
        for (const i of r.error.issues) console.log('  ' + i.path.join('.') + ': ' + i.message);
        process.exit(1);
      }
    " 2>&1); then
      pass "khớp schema của mcporter $(mcporter --version 2>/dev/null)"
    else
      fail "mcporter.json KHÔNG khớp schema:"; echo "$OUTPUT"
    fi
  else
    echo "  (không tìm thấy schema trong gói mcporter — bỏ qua)"
  fi
else
  echo "  (chưa cài mcporter — bỏ qua kiểm tra schema)"
fi

python3 - "$MP_CFG" <<'PYCHK'
import json, sys, re
cfg = json.load(open(sys.argv[1], encoding="utf-8"))
servers = cfg.get("mcpServers", {})
bad = []

# Biến môi trường không có giá trị mặc định làm HỎNG TOÀN BỘ việc nạp cấu hình,
# không chỉ server thiếu biến đó. Chỉ quét trong mcpServers — khoá "//" ở cấp
# gốc là chú thích, không được resolve.
BARE = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}")
for name, entry in servers.items():
    for hit in BARE.findall(json.dumps(entry, ensure_ascii=False)):
        bad.append(f"{name}: {hit} thiếu giá trị mặc định — dùng ${{VAR:-mặc-định}}")

for name, entry in servers.items():
    if not isinstance(entry, dict):
        bad.append(f"{name}: mỗi mục trong mcpServers phải là object (không đặt được khoá chú thích ở đây)")
        continue
    lc = entry.get("lifecycle")
    if isinstance(lc, dict) and "mode" not in lc:
        bad.append(f"{name}.lifecycle: thiếu 'mode' (phải là keep-alive hoặc ephemeral)")
    mode = lc if isinstance(lc, str) else (lc or {}).get("mode")
    if mode == "ephemeral":
        bad.append(f"{name}: lifecycle ephemeral -> 'mcporter serve' KHONG phoi server nay ra cau noi")
    for key in ("allowedTools", "blockedTools"):
        for tool in entry.get(key, []) or []:
            if re.search(r"[*?\[]", tool):
                bad.append(f"{name}.{key}: '{tool}' — tên tool phải chính xác, không dùng glob")
    if "allowedTools" in entry and "blockedTools" in entry:
        bad.append(f"{name}: không được khai báo cả allowedTools lẫn blockedTools")
print("\n".join("  " + b for b in bad))
sys.exit(1 if bad else 0)
PYCHK
if [[ $? -eq 0 ]]; then pass "quy ước lifecycle và danh sách tool"; else FAIL=1; fi

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
