# Cài đặt

## A. Máy phát triển / staging (Docker Compose)

### 1. Điều kiện tiên quyết
```bash
node --version      # cần >= 22, khuyến nghị 24
python3 --version   # cần >= 3.12
docker compose version
```

### 2. Bootstrap
```bash
./bootstrap.sh
```
Script này: kiểm tra công cụ → cài `acpx`, `mcporter`, `clawhub`, `openclaw`
toàn cục → tạo `.env` với khoá nội bộ sinh ngẫu nhiên (`openssl rand -hex 32`)
→ đặt quyền file → chạy kiểm chứng cấu hình.

Chạy lại nhiều lần được: mỗi bước tự kiểm tra trước khi làm, và **không ghi đè
`.env` đã có**.

### 2b. Đối chiếu CLI thật

```bash
./scripts/preflight.sh
```

`acpx`, `mcporter`, `openclaw` và `clawhub` đang phát hành rất nhanh. Một cờ có
trong tài liệu hôm nay có thể chưa có, hoặc đã đổi tên, trong bản bạn vừa cài.
Script này dò `--help` của bản **thật** trên máy bạn và báo ngay chỗ lệch — thay
vì để bạn phát hiện lúc container đã chạy. Nó cũng cảnh báo nếu repo đang nằm
trên ổ Windows trong WSL.

### 2c. Kiểm chứng cấu hình OpenClaw bằng chính binary

```bash
make oc-validate
```

Schema của OpenClaw nghiêm ngặt — một khoá thừa là gateway từ chối khởi động, và
thông báo lỗi chỉ xuất hiện lúc container chạy. Lệnh này chạy `openclaw config
validate` trên một bản sao tạm, nên không đụng tới `~/.openclaw` thật của bạn.
`make up` gọi nó trước khi khởi động, nên loại lỗi này không lọt tới runtime nữa.

### 3. Điền khoá nhà cung cấp model
```bash
$EDITOR .env
# ANTHROPIC_API_KEY=sk-ant-...
# OPENAI_API_KEY=sk-...
# GEMINI_API_KEY=...
```

Nếu có dữ liệu mức `confidential`/`restricted` (tài chính, nhân sự, pháp chế),
cần thêm một model tự host:
```bash
# LOCAL_LLM_BASE_URL=http://vllm:8000/v1
```

### 4. Khởi động
```bash
make up        # dựng ảnh + khởi động 8 dịch vụ (+1 container init dọn quyền)
make health    # 5 kiểm tra sức khoẻ: mcporter · agent-runner · gateway · LangGraph · n8n
```

Cổng mở ra (chỉ trên loopback, không ra ngoài máy):
- `18789` — OpenClaw Gateway
- `5678`  — n8n
- `2024`  — LangGraph

### 5. Cấu hình sau khi chạy
```bash
make agents             # xem đội hình + luật định tuyến
make capability         # sinh CLI từ MCP server
make import-workflows   # nhập workflow n8n từ git
make audit              # rà soát bảo mật + test chính sách OPA
```

### 6. Kết nối Slack

⚠️ Ở bản OpenClaw đang dùng, `openclaw plugins install` từ chối ghi cấu hình
plugin khi `control-plane/openclaw.json` dùng `$include` — mục này hiện **chưa
làm được** trên repo ở dạng đang commit. Kênh vào thật đang dùng thay thế là
webhook n8n (`make import-workflows` rồi xem `orchestration/n8n/workflows/01-intake-router.json`).
Xem `docs/00-kien-truc.md` và `CLAUDE.md` mục "Bẫy cấu hình cần biết".

```bash
docker compose -f deploy/docker/docker-compose.yml exec openclaw-gateway \
  openclaw channels login --channel slack --account acc-engineering
```
Rồi thêm ID kênh Slack thật vào `control-plane/config.d/bindings.json`
(thay `C_FLEET_ARCH`, `C_FLEET_REVIEW`, …), rồi `make restart-gateway` (lệnh này
chạy `oc-validate` trước khi khởi động lại).

---

## B. Kubernetes (production)

### Thứ tự áp dụng
```bash
kubectl apply -f deploy/k8s/00-namespace.yaml
kubectl apply -f deploy/k8s/10-rbac.yaml
kubectl apply -f deploy/k8s/20-networkpolicy.yaml   # TRƯỚC khi có pod nào chạy
kubectl apply -f deploy/k8s/30-secrets.yaml         # cần External Secrets Operator
# Tạo ConfigMap từ cấu hình trong git:
kubectl -n fleet create configmap openclaw-config  --from-file=control-plane/openclaw.json
kubectl -n fleet create configmap openclaw-configd --from-file=control-plane/config.d/
kubectl -n fleet create configmap mcporter-config  --from-file=capability-plane/mcporter.json
kubectl -n fleet create configmap acpx-config      --from-file=config.json=execution-plane/config/acpx.global.json
kubectl -n fleet create configmap fleet-skills     --from-file=distribution-plane/skills/
kubectl apply -f deploy/k8s/60-mcporter.yaml
kubectl apply -f deploy/k8s/40-openclaw-gateway.yaml
kubectl apply -f deploy/k8s/50-agent-runner.yaml
kubectl apply -f deploy/k8s/70-langgraph.yaml
```

### Năm điểm bắt buộc trước khi cho người thật dùng

1. **Ghim phiên bản ảnh.** Không dùng `:latest`. Sự cố với `latest` không tái
   hiện được, và đó là loại sự cố tệ nhất.

2. **Runtime sandbox.** `runtimeClassName: gvisor` (hoặc Kata) cho
   `agent-runner`. Agent chạy được lệnh tuỳ ý — container thường không đủ ranh
   giới. Nếu cụm chưa có, tối thiểu phải: NetworkPolicy chặn hết +
   `automountServiceAccountToken: false` + Pod Security `restricted`.

3. **NetworkPolicy áp dụng trước.** Áp dụng sau khi pod đã chạy là để hở một
   khoảng thời gian. Áp dụng trước.

4. **Secret không nằm trong git.** Dùng External Secrets Operator kéo từ Vault.
   `30-secrets.yaml` có sẵn cấu hình mẫu.

5. **PVC `fleet-repos` phải là ReadWriteMany.** Nhiều `agent-runner` cùng đọc/ghi
   worktree. RWO sẽ khiến pod thứ hai không khởi động được.

### Gateway không scale ngang
`openclaw-gateway` giữ phiên trong SQLite trên PVC → `replicas: 1`,
`strategy: Recreate`. Cần chịu tải cao hơn thì chạy nhiều gateway, mỗi gateway
một tập phòng ban, không phải nhiều bản sao của cùng một gateway.

---

## C. Kiểm chứng sau khi cài

```bash
./scripts/validate.sh
```

16 nhóm kiểm tra. Ngoài cú pháp (JSON5, JSON, YAML, shell, Python, Node), phần
đáng giá là các **kiểm tra nhất quán và quy ước** — quan trọng hơn cú pháp:

- Vai trò trong `agents.json` phải khớp `policy/tool-policy.yaml`
- Mỗi hồ sơ phòng ban phải trỏ tới một gói năng lực có thật
- Người soạn và người thẩm định trong hồ sơ phải khác backend
- `${BIẾN}` trong cấu hình OpenClaw chỉ ở trường credential; không SecretRef; không `env.vars`
- `${VAR}` trong mcporter phải có mặc định; tên tool chính xác; `lifecycle` có `mode`
- Named volume gắn vào thư mục con của image ngoài phải có init container
- Workflow n8n không được có node executeCommand

Cấu hình đúng cú pháp nhưng mâu thuẫn giữa các tầng là cách quyền bị rò trong
thực tế. Chạy script này trong CI (`.github/workflows/fleet-ci.yml` đã có sẵn).
