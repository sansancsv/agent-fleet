# n8n trong kiến trúc Agent Fleet

## n8n chịu trách nhiệm phần nào

n8n là **tầng quy trình nghiệp vụ** — nơi các phòng ban nhìn thấy và tự sửa được
quy trình của mình mà không cần lập trình viên. Nó **không** phải nơi chạy agent.

```
Sự kiện bên ngoài ──► n8n ──► (gọi) ──► OpenClaw / acpx / LangGraph ──► Agent
   webhook, cron,      xác thực,                   phi xác định
   form, email        phân quyền,
                      định tuyến,
                      ghi audit
```

## Ranh giới ba công cụ điều phối

| | **n8n** | **LangGraph** | **acpx flow** |
|---|---|---|---|
| Ai sở hữu | Phòng ban nghiệp vụ, ops | Kỹ sư nền tảng | Nhóm dev của repo |
| Sửa bằng | Kéo–thả trên trình duyệt | Python trong git | TypeScript trong repo |
| Kích hoạt | webhook, lịch, sự kiện app | HTTP API / SDK | CLI, CI |
| Lưu trạng thái | Bản ghi execution | Checkpointer PostgreSQL | Gói run trên đĩa |
| Chờ người | Node Wait (giờ) | `interrupt()` (ngày, bền vững) | Node `checkpoint` |
| Sống sót restart | Có (queue mode) | **Có, chính xác từng bước** | Không (chạy lại từ đầu) |
| Hợp nhất tích hợp SaaS | **Xuất sắc — 400+ node** | Phải tự viết | Qua mcporter |
| Phù hợp nhất cho | Quy trình liên phòng ban, nhiều tích hợp | Quy trình dài, cần tái hiện & kiểm toán | Pipeline gắn liền mã nguồn |

**Quy tắc chọn trong một câu:** nếu quy trình đi qua nhiều hệ thống SaaS → n8n;
nếu quy trình cần dừng chờ người hàng ngày và phải chạy lại được đúng từ điểm
dừng → LangGraph; nếu quy trình chỉ sống trong một repo và cần versioned cùng
code → acpx flow.

## Cài đặt (queue mode — bắt buộc cho môi trường thật)

Chế độ mặc định (`regular`) chạy mọi workflow trong một tiến trình. Một agent
chạy 20 phút sẽ chặn toàn bộ n8n. Vì vậy production **phải** dùng queue mode:

```bash
# Biến môi trường then chốt (xem deploy/docker/docker-compose.yml)
EXECUTIONS_MODE=queue
QUEUE_BULL_REDIS_HOST=redis
DB_TYPE=postgresdb
N8N_ENCRYPTION_KEY=<32+ ký tự, KHÔNG được đổi sau khi đã lưu credential>
N8N_RUNNERS_ENABLED=true          # tách việc chạy Code node ra tiến trình riêng
OFFLOAD_MANUAL_EXECUTIONS_TO_WORKERS=true
```

Cấu hình gồm ba tiến trình: `n8n` (giao diện + trigger), `n8n-worker` (chạy thật,
nhân bản được), `n8n-webhook` (nhận webhook, tách khỏi giao diện).

## Nhập workflow

```bash
# Nhập tất cả workflow mẫu
docker compose exec n8n n8n import:workflow --separate --input=/workflows

# Xuất ngược để commit vào git (workflow PHẢI nằm trong git, không chỉ trong DB)
docker compose exec n8n n8n export:workflow --all --separate --output=/workflows
```

## Bốn quy tắc bắt buộc khi viết workflow gọi agent

0. **Không có node executeCommand.** Worker n8n không có acpx, và ghép dữ liệu
   webhook vào chuỗi shell là chèn lệnh thật sự (`$( )` sống sót trong nháy kép).
   Mọi lượt agent đi qua HTTP tới agent-runner:
   `POST $AGENT_RUNNER_URL/run` với `{ role, cwd, prompt, write?, timeoutS? }`,
   kèm `Authorization: Bearer $AGENT_RUNNER_TOKEN`. Clone PR dùng
   `POST /pr/checkout { repo, pr }` và dọn bằng `POST /pr/cleanup { path }`.
   `scripts/validate.sh` từ chối mọi workflow có executeCommand.

1. **Kiểm quyền trước khi gọi model.** Một lượt agent tốn tiền thật; xác thực và
   phân quyền phải xong trước node đầu tiên chạm tới agent. Prompt có thể bị dẫn
   dụ, HTTP 403 thì không.

2. **Mọi dữ liệu ngoài đều là dữ liệu không tin cậy.** Nội dung webhook, email,
   issue, kết quả tìm kiếm — khi đưa vào prompt phải bọc trong thẻ
   `<untrusted source="...">`. Đây là phòng thủ chính chống chèn lệnh qua prompt.

3. **Quyết định chặn/không chặn nằm ở node Code, không nằm ở model.** Model nêu
   phát hiện; luật trong Code node quyết định có chặn merge hay không. Chỉ như vậy
   hai lần chạy giống nhau mới cho cùng kết quả, và mới kiểm toán được.

## Timeout

Agent chạy lâu hơn workflow thông thường rất nhiều. Đặt rõ:

```
EXECUTIONS_TIMEOUT=3600
EXECUTIONS_TIMEOUT_MAX=7200
```

và đặt `timeout` trên từng node HTTP gọi LangGraph (mặc định 300 giây là quá ngắn).
