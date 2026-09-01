# Sổ tay vận hành (runbook)

## Nhịp vận hành

| Tần suất | Việc | Lệnh |
|---|---|---|
| Hằng ngày | Xem sức khoẻ dịch vụ | `make health` |
| Hằng ngày | Xem chi phí theo phòng ban | dashboard chi phí |
| Hằng tuần | Rà nhật ký kiểm toán tìm hành vi bất thường | truy vấn Loki |
| Hằng tuần | Xem tỉ lệ leo thang (agent bó tay) | báo cáo LangGraph |
| Hằng tháng | Rà quyền: vai trò nào có quyền không dùng đến | `make audit` |
| Hằng tháng | Cập nhật ảnh, quét lỗ hổng | CI |
| Hằng quý | Diễn tập xoay vòng khoá | thủ công |

---

## Bốn chỉ số cần theo dõi

**1. Tỉ lệ leo thang** — bao nhiêu % công việc kết thúc bằng `outcome: blocked`.
Tăng đột ngột = model xuống cấp, hoặc quy trình gặp loại việc mới chưa xử lý được.

**2. Số vòng sửa lại trung bình.** Gần 0 = thẩm định quá dễ dãi. Gần giới hạn
(2) = model viết code chưa đủ tốt cho loại việc này.

**3. Tỉ lệ đồng thuận khi thẩm định chéo.** Mục 3/3 gần như chắc chắn là lỗi
thật. Nếu hầu hết mục chỉ 1/3, tiêu chí thẩm định đang quá mơ hồ.

**4. Chi phí trên mỗi công việc hoàn thành.** Chỉ số duy nhất nói được fleet có
đáng tiền không. Tính theo *công việc hoàn thành*, không theo *lượt gọi*.

---

## Sự cố thường gặp

### Gateway không khởi động
```bash
make logs S=openclaw-gateway
```
| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| `config validation failed` | JSON5 sai cú pháp | `python3 scripts/json5_to_json.py <file>` để biết dòng nào |
| `bind: address in use` | cổng 18789 đã bị chiếm | đổi `OPENCLAW_GATEWAY_PORT` |
| `auth token missing` | thiếu biến trong `.env` | `openssl rand -hex 32` rồi điền |

### `mcporter` không khởi động

Bốn nguyên nhân, xếp theo tần suất gặp. Cả bốn đều bị `./scripts/validate.sh`
bắt trước khi container chạy — nếu bạn gặp ở runtime nghĩa là đã bỏ qua bước đó.

**1. `Unknown daemon subcommand`** — lệnh phơi cầu nối là `mcporter serve --http <port>`.
`mcporter daemon` chỉ có `start` / `stop` / `restart` / `status`, và nó **không nhận
`--config`** (luôn đọc `~/.mcporter/mcporter.json`).

**2. `expected object, received string` tại `mcpServers.//--- ... ---`**
Mỗi khoá trong `mcpServers` phải trỏ tới một object. Khoá chú thích kiểu
`"//--- nhóm ---": ""` chỉ dùng được ở **cấp gốc**, không dùng được bên trong
`mcpServers`.

**3. `Invalid input` tại `<server>.lifecycle`**
`lifecycle` là `"keep-alive"` | `"ephemeral"` | `{ mode, idleTimeoutMs }`.
Viết `{ idleTimeoutMs: 600000 }` mà thiếu `mode` sẽ hỏng.

**4. `unresolved env placeholder`**
Một `${VAR}` chưa đặt làm **hỏng toàn bộ** việc nạp cấu hình, không chỉ server
thiếu biến đó — nghĩa là thiếu một token Grafana cũng đủ để cả cầu nối không lên.
Luôn viết `${VAR:-giá-trị-mặc-định}`. Khi làm đúng, server thiếu credential chỉ
hiện là `offline` hoặc `auth required`, phần còn lại vẫn chạy.

### Ba hành vi của mcporter dễ mất thời gian nếu không biết trước

**`serve` chỉ phơi server `keep-alive`.** Đặt `lifecycle: ephemeral` nghĩa là
server đó vô hình với cầu nối, dù `mcporter list` vẫn thấy. Kiểm tra bằng
`make mcp-status` và `mcporter daemon status`.

**`allowedTools` / `blockedTools` là tên tool CHÍNH XÁC, không phải glob.**
`"*_delete_*"` không khớp gì cả — nó im lặng vô hiệu, và bạn tưởng đã chặn.
Quy trình đúng là hai bước: khai báo server → `make tools S=<server>` để xem tên
thật → chép vào `allowedTools`. Không được khai báo cả hai danh sách trên cùng
một server.

**`mcporter call` dùng `key=value`, không có `--arg`.**
```bash
mcporter call github.search_code q="rate limit" --output json
mcporter call notion.notion-create-pages parentPageId=abc content=@/tmp/body.md
```
`key=@path` đọc giá trị từ tệp — dùng cho nội dung dài để khỏi thoát chuỗi trong shell.

### Gateway báo `Invalid --bind`

`gateway.bind` nhận **một trong năm giá trị**, không phải địa chỉ IP:
`loopback` | `lan` | `tailnet` | `auto` | `custom`.

Trong Docker phải là `lan` thì container khác mới gọi tới gateway được
(`loopback` chỉ nghe 127.0.0.1 *bên trong* container). Muốn một IP cụ thể thì
dùng `bind: "custom"` kèm `gateway.customBindHost`. Biến môi trường đúng tên là
`OPENCLAW_GATEWAY_BIND`. `./scripts/validate.sh` nay kiểm giá trị này.

### LangGraph báo `executable file not found in $PATH`

Gói `langgraph` (thư viện) **không kèm** lệnh `langgraph` — CLI nằm ở gói riêng
`langgraph-cli`. Và kể cả cài đúng, `langgraph up` dựng Docker Compose nên chạy
nó bên trong một container là sai tầng.

Fleet này không dùng LangGraph Server. Nó phục vụ đồ thị bằng một FastAPI mỏng
(`src/fleet/server.py`) chạy qua `uvicorn`, phơi đúng những endpoint mà n8n gọi:

| Endpoint | Dùng để |
|---|---|
| `GET /ok` | healthcheck |
| `GET /profiles/<tên>/authorize?requester=` | n8n kiểm quyền **trước khi** tiêu token |
| `POST /runs/wait` | chạy tới khi xong hoặc tới điểm chờ người duyệt |
| `POST /runs/<thread_id>/resume` | người duyệt trả lời → chạy tiếp đúng chỗ đã dừng |
| `GET /runs/<thread_id>` | đọc trạng thái hiện tại |

Nếu thiếu `FLEET_CHECKPOINT_DSN`, server vẫn chạy nhưng dùng bộ nhớ trong và in
cảnh báo — quy trình sẽ mất khi container khởi động lại.

### Agent trả lời "không có tool đó"
```bash
make mcp-status               # server nào kết nối được, server nào offline
make tools S=github           # tên tool CHÍNH XÁC mà server đó phơi ra
make capability               # sinh lại CLI sau khi sửa cấu hình
```
Nguyên nhân hay gặp nhất: tool bị lọc bởi `allowedTools`, hoặc bị chặn bởi
`blockedTools` ở tầng gateway (`config.d/mcp.json`).

### Lượt agent bị treo
```bash
docker compose exec agent-runner acpx claude sessions list
docker compose exec agent-runner acpx claude sessions rm <tên-phiên>
```
Timeout mặc định 30 phút. Treo thường xuyên = bước quá lớn, cần tách nhỏ.

### LangGraph mất trạng thái sau khi khởi động lại
Kiểm tra `FLEET_CHECKPOINT_DSN` đã trỏ đúng PostgreSQL chưa. Nếu để trống,
LangGraph chạy checkpoint trong bộ nhớ và **mọi lần chờ người duyệt sẽ mất** khi
pod restart. Đây là lỗi cấu hình hay gặp nhất khi lên production.

### n8n mất toàn bộ credential
`N8N_ENCRYPTION_KEY` đã bị đổi. Không khôi phục được. Khôi phục từ backup của
`n8ndata` volume, hoặc nhập lại credential thủ công. **Không bao giờ đổi khoá này.**

### Chi phí tăng vọt
```bash
grep '"event":"model.select"' /var/log/fleet/fleet-audit.jsonl \
  | jq -r '.model' | sort | uniq -c | sort -rn
```
Ba nguyên nhân thường gặp, theo thứ tự: vòng lặp sửa lại không giới hạn; dùng
model suy luận sâu cho việc phân loại; ngữ cảnh phình vì phiên không xoay vòng.

---

## Vận hành theo mùa vụ

### Thêm một vai trò agent
1. Thêm mục vào `control-plane/config.d/agents.json`
2. Thêm vai trò tương ứng vào `policy/tool-policy.yaml` **và** `policy/opa/fleet.rego`
3. Thêm ánh xạ trong `execution-plane/scripts/run-role.sh` và `acpx_client.py::ROLE_BACKENDS`
4. Tạo `workspaces/<vai-trò>/SOUL.md`
5. `./scripts/validate.sh` — script sẽ báo nếu bốn nơi trên không khớp

### Đổi model của một vai trò
Sửa `agents.entries.<vai-trò>.model` trong `agents.json`. Gateway tự nạp lại.
**Kiểm tra lại quy tắc đa dạng hoá:** nếu đổi model của `implementer` sang cùng
nhà cung cấp với `reviewer`, `validate.sh` sẽ báo lỗi.

### Cập nhật phiên bản công cụ
```bash
npm view acpx version && npm view mcporter version && npm view openclaw version
```
Cập nhật ARG trong `Dockerfile.agent-runner` và tag ảnh trong compose/K8s.
Chạy `make validate && make audit` trên staging trước.

### Xoay vòng khoá
```bash
# 1. Sinh khoá mới trong Vault
# 2. ExternalSecret tự đồng bộ sau <= 1 giờ (refreshInterval)
# 3. Khởi động lại để tiến trình nhận biến mới
kubectl -n fleet rollout restart deploy/agent-runner deploy/mcporter deploy/openclaw-gateway
# 4. Thu hồi khoá cũ ở phía nhà cung cấp
```

---

## Sao lưu

| Dữ liệu | Nơi | Tần suất | Vì sao |
|---|---|---|---|
| PostgreSQL (`fleet_checkpoints`) | PVC | hằng ngày | mất = mất mọi quy trình đang chờ duyệt |
| PostgreSQL (`n8n`) | PVC | hằng ngày | mất = mất workflow và credential |
| `openclaw-state` | PVC | hằng ngày | mất = mất lịch sử phiên và ghép đôi kênh |
| `N8N_ENCRYPTION_KEY` | Vault | — | mất = credential n8n thành vô dụng |
| Workflow n8n | **git** | mỗi lần sửa | `make export-workflows` sau khi sửa trên UI |

Workflow n8n chỉ nằm trong database là một điểm hỏng đơn lẻ. Xuất ra git sau mỗi
lần sửa — đó là lý do `make export-workflows` tồn tại.

---

## Cầu dao khẩn cấp

```bash
# Dừng mọi hoạt động agent, giữ nguyên dữ liệu để điều tra
docker compose stop agent-runner langgraph n8n-worker

# Kubernetes
kubectl -n fleet scale deploy/agent-runner deploy/langgraph --replicas=0
```

Gateway vẫn chạy để người dùng nhận được thông báo, nhưng không lượt agent nào
mới được khởi tạo.
