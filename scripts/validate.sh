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

# --- 5b. Node (API của agent-runner) ----------------------------------------
echo; echo "5b) Cú pháp Node"
if command -v node >/dev/null 2>&1; then
  for f in execution-plane/runner/*.mjs; do
    if node --check "$f" 2>/dev/null; then pass "$f"; else fail "$f — lỗi cú pháp"; fi
  done
else
  echo "  (chưa cài node — bỏ qua)"
fi

# --- 5c. n8n KHÔNG được chạy lệnh shell -------------------------------------
# Node executeCommand chạy trong container n8n-worker (không có acpx) và ghép
# dữ liệu webhook vào chuỗi shell — chèn lệnh thật sự. Mọi lượt agent phải đi
# qua API của agent-runner (POST /run) bằng node httpRequest.
echo; echo "5c) n8n — không dùng executeCommand"
for f in orchestration/n8n/workflows/*.json; do
  if grep -q '"n8n-nodes-base.executeCommand"' "$f"; then
    fail "$f dùng executeCommand — chuyển sang httpRequest tới \$env.AGENT_RUNNER_URL/run"
  else
    pass "$f"
  fi
done

# --- 5d. Khoá model phải được thu hẹp theo backend --------------------------
# acpx truyền môi trường xuống MỌI tiến trình con, kể cả lệnh
# do chính agent quyết định chạy — nên một lượt `implementer` không được nhìn
# thấy khoá của nhà cung cấp mà nó không dùng. Logic này tồn tại ở HAI nơi
# (shell và Python) và cả hai đều dễ bị gỡ mất trong một lần refactor vô tình.
# Phép kiểm này chặn đúng chuyện đó — nó bảo vệ một biện pháp BẢO MẬT, không
# phải một quy ước về phong cách.
echo; echo "5d) Thu hẹp khoá model theo backend"
RR=execution-plane/scripts/run-role.sh
AC=orchestration/langgraph/src/fleet/acpx_client.py
if grep -q 'unset "ACPX_AUTH_${PROVIDER}_API_KEY"' "$RR"; then
  pass "$RR gỡ khoá của nhà cung cấp không dùng"
else
  fail "$RR KHÔNG còn gỡ khoá model — đây là biện pháp bảo mật, đừng bỏ"
fi
if grep -q 'def provider_env' "$AC" && grep -q 'provider_env(backend)' "$AC"; then
  pass "$AC có provider_env() và thực sự dùng nó"
else
  fail "$AC thiếu provider_env() hoặc khai mà không gọi — hai nhánh chạy phải khớp nhau"
fi

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

# --- 6c. OpenClaw: ${BIẾN} chỉ hợp lệ ở đúng vài chỗ ------------------------
# Quy tắc đã đối chiếu với binary OpenClaw 2026.8.1:
#   • Trường credential (token, botToken, apiKey…) CHẤP NHẬN mẫu "${BIẾN}".
#   • Khối `mcp` cũng có thay thế ${BIẾN}.
#   • MỌI CHỖ KHÁC bị đọc nguyên văn — "${X}" là chuỗi "${X}", không phải giá trị.
#   • Cú pháp ${BIẾN:-mặc-định} KHÔNG được hỗ trợ ở bất kỳ đâu.
# `make oc-validate` chạy chính binary và bắt được nhiều hơn; phép kiểm này để
# bắt sớm hai lỗi mà binary chỉ cảnh báo nhẹ hoặc không nói gì.
echo; echo "6c) OpenClaw — vị trí hợp lệ của \${BIẾN}"
if python3 scripts/check-oc-placeholders.py control-plane/openclaw.json control-plane/config.d/*.json; then
  pass "\${BIẾN} chỉ xuất hiện ở trường credential; không có cú pháp :- ; không có env.vars"
else
  FAIL=1
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

# --- 8a. NHẤT QUÁN: mức nhạy cảm dữ liệu quyết định backend model -----------
# Nguồn sự thật là policy/model-routing.yaml. agents.* của mọi hồ sơ phải nằm
# trong allowedBackends của dataClass tương ứng; MODEL_POLICY (bảng mà chốt lúc
# chạy trong server.py tra) và fleet.rego phải khớp nguồn sự thật; backend của
# từng vai trò trong ROLE_BACKENDS phải trùng run-role.sh — nếu không, chốt kiểm
# một backend trong khi agent-runner chạy backend khác. Trước bước này,
# support.yaml (confidential) khai Gemini mà script vẫn xanh.
echo; echo "8a) Mức nhạy cảm dữ liệu ↔ backend model"
if OUT=$(python3 scripts/check-model-policy.py 2>&1); then
  pass "agents.* nằm trong allowedBackends; MODEL_POLICY, fleet.rego, run-role.sh khớp model-routing.yaml ($OUT)"
else
  fail "lệch chính sách dataClass (nguồn sự thật: policy/model-routing.yaml):"
  echo "$OUT"
fi
# Cửa vào của n8n nhận yêu cầu của MỌI hồ sơ, nên mọi lượt agent từ đó phải
# qua chốt dataClass của LangGraph (POST /profiles/<tên>/run). Gọi thẳng
# agent-runner là đi vòng qua chốt — đúng đường đã đưa dữ liệu restricted tới Gemini.
INTAKE=orchestration/n8n/workflows/01-intake-router.json
if grep -q 'AGENT_RUNNER_URL' "$INTAKE"; then
  fail "$INTAKE gọi thẳng agent-runner — yêu cầu phòng ban phải qua POST \$LANGGRAPH_URL/profiles/<tên>/run"
else
  pass "$INTAKE không gọi thẳng agent-runner — yêu cầu phòng ban qua chốt dataClass"
fi

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

# --- 8c. Quyền của named volume gắn vào thư mục con -------------------------
echo; echo "8c) Docker — quyền của volume"
if python3 scripts/check-volume-perms.py deploy/docker/docker-compose.yml; then
  pass "không có volume nào gắn vào thư mục con của image ngoài mà thiếu init chown"
else
  FAIL=1
fi

# --- 8d. K8s: tham chiếu treo và NetworkPolicy thiếu -------------------------
# Đây là loại lỗi chỉ lộ ra lúc `kubectl apply` lên cụm thật, tức là lúc đắt
# nhất để phát hiện. Ba lỗi phòng ở đây:
#   1. `fleet-mcp-credentials` được envFrom nhưng chưa từng được định nghĩa
#      → pod kẹt CreateContainerConfigError.
#   2. default-deny chặn cả hai chiều nhưng thiếu ingress cho mcporter và
#      thiếu egress cho langgraph → cụm im lặng không chạy.
#   3. readinessProbe httpGet /healthz trên dịch vụ không có endpoint đó
#      → Deployment không bao giờ Ready.
# NetworkPolicy là CỘNG DỒN và HAI CHIỀU: A tới được B chỉ khi A có egress rule
# VÀ B có ingress rule. Phép kiểm dưới đây bắt đúng vế hay bị quên.
echo; echo "8d) Kubernetes — tham chiếu treo và NetworkPolicy"
python3 - <<'PYK8S'
import glob, sys
import yaml

docs = []
for path in sorted(glob.glob("deploy/k8s/*.yaml")):
    try:
        with open(path, encoding="utf-8") as fh:
            docs += [(path, d) for d in yaml.safe_load_all(fh) if isinstance(d, dict)]
    except yaml.YAMLError as exc:
        print(f"  {path}: YAML hỏng — {exc}")
        sys.exit(1)

bad = []

# --- Nguồn secret và configMap có trong repo ---------------------------------
have_secrets = {
    d["metadata"]["name"]
    for _, d in docs
    if d.get("kind") in ("ExternalSecret", "Secret", "SealedSecret")
}
# ExternalSecret đặt tên Secret sinh ra ở spec.target.name; lấy cả tên đó.
have_secrets |= {
    (d.get("spec", {}).get("target") or {}).get("name")
    for _, d in docs
    if d.get("kind") == "ExternalSecret"
} - {None}
have_cms = {d["metadata"]["name"] for _, d in docs if d.get("kind") == "ConfigMap"}

workloads = [(p, d) for p, d in docs if d.get("kind") in ("Deployment", "StatefulSet", "DaemonSet")]

for path, d in workloads:
    name = d["metadata"]["name"]
    spec = d["spec"]["template"]["spec"]
    for c in spec.get("containers", []) + spec.get("initContainers", []):
        for ef in c.get("envFrom", []) or []:
            ref = (ef.get("secretRef") or {}).get("name")
            if ref and ref not in have_secrets:
                bad.append(f"{path}: {name} envFrom secret '{ref}' không có nguồn trong repo")
            ref = (ef.get("configMapRef") or {}).get("name")
            if ref and ref not in have_cms:
                bad.append(f"{path}: {name} envFrom configMap '{ref}' không có nguồn trong repo")
        for e in c.get("env", []) or []:
            vf = e.get("valueFrom") or {}
            ref = (vf.get("secretKeyRef") or {}).get("name")
            if ref and ref not in have_secrets:
                bad.append(f"{path}: {name} env {e['name']} → secret '{ref}' không có nguồn")
        # readinessProbe httpGet trên dịch vụ không phơi HTTP là lỗi im lặng:
        # Deployment không bao giờ Ready mà log thì sạch.
        for probe in ("readinessProbe", "livenessProbe", "startupProbe"):
            p = c.get(probe) or {}
            if "httpGet" in p and c.get("name") == "mcporter":
                bad.append(f"{path}: {name}.{probe} dùng httpGet — mcporter serve không có endpoint HTTP nào; dùng tcpSocket")

# --- NetworkPolicy: mọi workload phải được cả hai chiều chọn tới -------------
policies = [d for _, d in docs if d.get("kind") == "NetworkPolicy"]

def selects(pol, labels: dict) -> bool:
    """Policy có nhắm ĐÍCH DANH workload này không.

    podSelector rỗng (chọn mọi pod) KHÔNG tính. Nếu tính, thì `allow-dns` —
    vốn chỉ mở cổng 53 cho toàn namespace — sẽ làm mọi workload trông như đã
    có đường ra, và phép kiểm này trở nên vô dụng đúng lúc cần nhất.
    """
    sel = (pol.get("spec", {}) or {}).get("podSelector", {})
    match = (sel or {}).get("matchLabels") or {}
    if not match:
        return False
    return all(labels.get(k) == v for k, v in match.items())

for path, d in workloads:
    name = d["metadata"]["name"]
    labels = ((d["spec"]["template"].get("metadata") or {}).get("labels")) or {}
    for direction, key in (("Ingress", "ingress"), ("Egress", "egress")):
        # Chỉ tính policy có RULE thật; default-deny chọn mọi pod nhưng không
        # mở đường nào, nên không được tính là đã có đường.
        opened = any(
            direction in (p["spec"].get("policyTypes") or [])
            and (p["spec"].get(key) or [])
            and selects(p, labels)
            for p in policies
        )
        if not opened:
            bad.append(f"{path}: {name} không có NetworkPolicy {direction} nào mở đường — "
                       f"default-deny sẽ chặn hết")

print("\n".join("  " + b for b in bad))
sys.exit(1 if bad else 0)
PYK8S
if [[ $? -eq 0 ]]; then pass "tham chiếu secret/configMap và NetworkPolicy đầy đủ"; else FAIL=1; fi

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
