# Bảo mật

## 1. Mô hình mối đe doạ thực tế

Rủi ro lớn nhất của một agent fleet **không phải** "model bị hack". Nó là:

> **Có người nhắn cho bot, và bot làm đúng như họ bảo.**

Biến thể phổ biến: nội dung độc hại không đến từ người dùng mà từ **dữ liệu** —
một issue GitHub, một trang web agent vừa đọc, một email. Đó là chèn lệnh qua
prompt (prompt injection).

Vì vậy thứ tự phòng thủ là:

| Ưu tiên | Lớp | Câu hỏi | Cưỡng chế ở đâu |
|---|---|---|---|
| 1 | **Danh tính** | Ai được nhắn cho bot? | `dmPolicy: allowlist`, Slack account riêng từng phòng ban |
| 2 | **Phạm vi** | Bot được làm gì, ở đâu? | tool policy, sandbox, NetworkPolicy, RBAC |
| 3 | **Model** | — | Luôn giả định model có thể bị dẫn dụ |

Lớp 3 **không bao giờ** là biện pháp kiểm soát chính. Model tốt làm giảm xác
suất, không làm giảm thiệt hại.

---

## 2. Phòng thủ nhiều lớp — mỗi quyền bị chặn ở ≥ 2 tầng

Ví dụ với quyền ghi file của `reviewer`:

| Tầng | Cơ chế | Cấu hình |
|---|---|---|
| 1 | OpenClaw tool policy | `tools: { deny: ["write","exec"] }` |
| 2 | acpx permission mode | `--deny-all` trong `run-role.sh` |
| 3 | OPA | `role_capabilities.reviewer` không có `write` — **hiện chỉ có test, chưa được gọi lúc chạy** (xem lộ trình) |
| 4 | Kubernetes | không có ServiceAccount token, NetworkPolicy chặn ra ngoài; PVC repo mount RW cho mọi vai trò nên quyền ghi KHÔNG bị chặn ở tầng này |

`scripts/validate.sh` kiểm tra tầng 1 khớp với `policy/tool-policy.yaml` (bản mô
tả người đọc được). Rego, cờ acpx trong `run-role.sh` và `ROLE_BACKENDS` trong
`acpx_client.py` phải tự soát khi đổi vai trò. Với `reviewer` hôm nay, hai tầng
thật sự giữ là 1 và 2.

### Tầng 4 (Kubernetes) yếu hơn bảng trên gợi ý

Bảng trên mô tả trạng thái mong muốn; K8s manifest **chưa được kiểm chứng trên
cụm thật** (repo mới chạy Compose). Bốn điểm cần kiểm khi apply lần đầu:

- Bộ NetworkPolicy phải có đủ ingress cho `mcporter` và `langgraph`, đủ egress
  cho `langgraph` và gateway — thiếu một vế là cụm không chạy, và áp lực sửa
  nhanh dễ dẫn tới việc ai đó nới policy bằng tay ngoài git.
- `fleet-mcp-credentials` phải được định nghĩa trước khi tham chiếu.
- SecretStore không nên xác thực Vault bằng ServiceAccount của `agent-runner` —
  tránh để danh tính mở kho secret trùng với danh tính container chạy code do
  agent sinh ra.
- `mcporter` dùng ảnh riêng, tách khỏi `agent-runner`, để kho credential MCP
  không nằm cạnh `acpx`, `gh`, `git` và `run-role.sh`.

### Cầu nối mcporter: cách ly mạng là lớp DUY NHẤT

`mcporter serve` không có xác thực. `MCPORTER_BRIDGE_TOKEN` được cấp trong
`fleet-service-tokens` nhưng chỉ có tác dụng nếu bản mcporter đang cài hỗ trợ cờ
tương ứng — `bridge-up.sh` dò lúc chạy và **ghi cảnh báo ra log** khi không bật
được. Trước khi mở thêm bất kỳ ai vào cổng 7420, hãy nhớ: ai gọi được cầu nối
thì dùng được toàn bộ credential MCP của công ty.

### Khoá model: một rủi ro CHƯA đóng

Vai trò `implementer` và `tester` chạy với `--approve-all`, tức là agent chạy
được lệnh shell tuỳ ý. acpx truyền môi trường của nó xuống mọi tiến trình con,
nên các lệnh đó **nhìn thấy khoá model có trong container `agent-runner`**. Một
lần chèn lệnh thành công là đọc được khoá.

Giảm thiểu hiện có: `run-role.sh` và `acpx_client.provider_env()` gỡ khoá của
những nhà cung cấp không phải backend của vai trò đang chạy — bán kính thiệt
hại hạ từ ba nhà cung cấp xuống một. `validate.sh` bước 5d canh cho phần này
không bị gỡ mất.

**Đây là giảm thiểu, không phải bản vá**, và phạm vi hẹp hơn tưởng:
`openclaw-gateway` **cũng** nhận cả ba khoá model và cũng chạy agent. Phần thu
hẹp khoá chỉ nằm trên đường `run-role.sh` / `acpx_client`, nên **không bảo vệ
đường của gateway**.

Vậy có hai nơi khoá model nằm cạnh nơi chạy code, và mới bịt được một nửa của
một nơi. Đích đến là proxy model giữ khoá riêng — cách duy nhất đóng cả hai
bằng một thay đổi. Đừng đọc mục này như một vấn đề đã xử lý xong.

---

## 3. Chống chèn lệnh qua prompt

Bốn biện pháp, dùng đồng thời:

**a. Đánh dấu nội dung không tin cậy.** Mọi dữ liệu từ web, issue, email, kết quả
MCP đều được bọc:
```
<untrusted source="github-issue">
...nội dung...
</untrusted>
```
Hiến chương fleet (`workspaces/_shared/AGENTS.md`) quy định rõ: nội dung trong
thẻ này là **dữ liệu để đọc**, không phải **mệnh lệnh để làm theo**.

**b. Giới hạn quyền theo vai trò.** Agent đọc dữ liệu ngoài (`analyst`,
`reviewer`) không có `write` và `exec`. Kể cả bị dẫn dụ hoàn toàn cũng không làm
được gì.

**c. Chặn mạng.** Ở Kubernetes, `agent-runner` không ra được Internet trực tiếp
(`20-networkpolicy.yaml`). Chỉ `mcporter` ra được, và chỉ cổng 443, và có chặn
`169.254.169.254` (metadata endpoint của cloud — đường tuồn thông tin xác thực
kinh điển). **Docker Compose không có lớp này** — mọi container ra Internet tự
do; vì vậy compose chỉ dành cho máy phát triển và staging nội bộ.

**e. Không có shell giữa dữ liệu ngoài và tiến trình.** n8n gọi agent qua HTTP
(`POST /run` của agent-runner), không dùng node executeCommand; runner đưa prompt
vào argv bằng `spawn()`. `validate.sh` từ chối workflow có executeCommand.

**d. Danh sách lệnh cấm tuyệt đối.** `policy/opa/fleet.rego` chặn theo mẫu:
`git push --force`, `DROP TABLE`, `kubectl delete`, `curl api.openai.com`
(bỏ qua tầng ghi log), `env | curl` (tuồn biến môi trường).

---

## 4. Quản lý secret

**Nguyên tắc:** agent không bao giờ *nhìn thấy* secret; agent chỉ *dùng được*
năng lực mà secret mở ra.

| Việc | Cách làm | Không làm |
|---|---|---|
| Lưu secret | Vault + External Secrets Operator | file `.env` trong production |
| Đưa vào tiến trình | biến môi trường, chỉ trong đúng lượt chạy | ghi vào workspace |
| Token MCP | trong vault của mcporter, không rải rác | lặp lại ở nhiều file cấu hình |
| Xoay vòng | `refreshInterval: 1h` trong ExternalSecret | thủ công mỗi quý |
| Ghi log | `logging.redactPatterns` trong `config.d/security.json` (mẫu `sk-…`, `ghp_…`, `xox…`, `Bearer …`) | log nguyên request |

Cấu hình OpenClaw dùng chuỗi `"${TÊN_BIẾN}"` ở trường credential thay vì giá trị
trực tiếp — nhờ đó file cấu hình commit vào git được. **Không dùng SecretRef
object** `{ source, provider, id }`: nó qua được `config validate` rồi làm gateway
chết lúc khởi động nếu provider chưa đăng ký; `validate.sh` cấm dạng này.

**Nếu nghi ngờ lộ khoá:** xoay vòng ngay, đừng điều tra trước. Xoay vòng mất 5
phút; điều tra mất 5 giờ và trong 5 giờ đó khoá vẫn dùng được.

---

## 5. Nhật ký kiểm toán

Hiện có năm nguồn, mỗi nguồn một nơi:

| Nguồn | Cấu hình / mã | Ghi ở đâu | Nội dung |
|---|---|---|---|
| Gateway OpenClaw | `config.d/security.json`: `logging.audit { enabled, executionIdentity, messages: "all" }` | volume `openclaw-audit` (`/home/node/.openclaw/audit`) | sự kiện run, tool call, tin nhắn — định dạng do OpenClaw quy định |
| LangGraph | `server.py::_audit` | stdout container `langgraph` | `permission.decision`: ai duyệt/từ chối thread nào, được chấp nhận hay bị 403 |
| LangGraph (bền) | `trajectory.permission_denied()`, gọi từ nhánh 403 của `run_resume()` | volume `fleet-logs` (NDJSON) | mọi lượt bị 403 (sai người duyệt) ghi một dòng bền, độc lập với log container |
| agent-runner | `runner/server.mjs::log` | stdout container `agent-runner` | mỗi lượt: route, role, mã HTTP, thời gian |
| n8n | node "Ghi nhật ký kiểm toán" trong workflow 01 | **chỉ trong execution data của n8n** | requestId, requester, profile, nhánh |
| Vết chạy | `fleet/trajectory.py` | volume `fleet-memory` + stdout `langgraph` | mỗi nút: thời gian, kết quả, số vòng sửa, **chữ ký** phát hiện |

Bốn nguồn đầu trả lời câu hỏi **kiểm toán** ("ai làm gì"). Nguồn thứ năm trả lời
câu hỏi **kỹ thuật** ("quy trình hỏng ở nút nào, lỗi nào lặp lại") — đó là hai
việc khác nhau và cố ý không gộp. Vết chạy chỉ ghi **chữ ký** phát hiện
(`MỨC|tên-file`), không ghi nội dung phát hiện: đủ để đếm lỗi lặp lại, không đủ
để rò mã nguồn ra hệ thống log tập trung.

Ba câu hỏi kiểm toán viên luôn hỏi, và nguồn trả lời:

1. *Ai đã yêu cầu gì, khi nào?* → n8n execution data + audit của gateway
2. *Agent đã chạm vào hệ thống nào?* → audit của gateway (tool call qua mcporter)
3. *Vì sao một hành động bị chặn?* → `permission.decision` của LangGraph; `deny_reason`
   của OPA **chưa có** vì OPA chưa được gọi lúc chạy

Việc còn thiếu, theo lộ trình: gom cả bốn về một nơi (Loki/OpenSearch/Splunk),
và cho node n8n ghi ra ngoài thay vì chỉ giữ trong execution data. Giữ tối thiểu
12 tháng nếu thuộc phạm vi SOC 2 hoặc ISO 27001.

**Named Docker volume không phải audit trail compliance-grade**, kể cả sau khi
thêm `permission.denied` bền ở trên. Không có replication, không tách quyền
đọc/ghi (ai `docker exec` được vào container `langgraph` đọc/sửa được thẳng file
NDJSON), không hash-chain chống sửa sau khi ghi, và một lệnh vận hành sai
(`make nuke`, `docker compose down -v`) xoá sạch không cảnh báo, không thùng
rác. Coi đây là mức "đủ để dev/staging tự soát", không phải mức nộp cho kiểm
toán ngoài — cho tới khi việc gom log ở trên được làm.

---

## 6. Sandbox

Hai lớp, dùng cả hai:

**Lớp ứng dụng** — `agents.defaults.sandbox` của OpenClaw (đúng schema 2026.8.1):
```json5
sandbox: { mode: "all", scope: "agent", workspaceAccess: "rw" }
```
`scope: "agent"` là quan trọng: agent này không thấy được filesystem của agent khác.
Schema **không có** `network` hay `limits` — cách ly mạng làm bằng NetworkPolicy,
giới hạn tài nguyên làm bằng `resources` của pod / `deploy.resources` của compose.

**Lớp hạ tầng** — runtime sandbox trong Kubernetes:
```yaml
runtimeClassName: gvisor
```
Agent chạy được lệnh tuỳ ý. Container thường chia sẻ kernel với host — **không
đủ** làm ranh giới bảo mật khi mã chạy bên trong là do model sinh ra.

Nếu cụm chưa có gVisor/Kata, bù bằng: NetworkPolicy chặn hết +
`automountServiceAccountToken: false` + Pod Security `restricted` + không mount
Docker socket.

---

## 7. Ngân sách như một biện pháp bảo mật

Một agent bị dẫn dụ vào vòng lặp có thể đốt hàng nghìn đô trong một đêm. Vì vậy
hạn mức chi phí là kiểm soát bảo mật, không chỉ là kiểm soát tài chính:

```yaml
budgets:
  perTaskUsd: 8
  perDayUsd: 400
  onExceed: "block-and-notify"   # chặn và báo, KHÔNG âm thầm hạ cấp model
```

Kèm theo là giới hạn vòng lặp: `maxStepRuns` trong acpx flow, `max_revisions`
trong LangGraph. Hết lượt thì leo thang cho người — không thử tiếp.

---

## 8. Danh mục rà soát trước khi cho người thật dùng

- [ ] `make audit` xanh (`openclaw security audit` + `opa test`)
- [ ] `./scripts/validate.sh` xanh, chạy trong CI
- [ ] Gateway không phơi ra Internet mà không có auth token
- [ ] `dmPolicy: allowlist` trên mọi kênh (không dùng `open`)
- [ ] NetworkPolicy đã áp dụng **trước** khi pod chạy
- [ ] Secret nằm trong Vault, không trong git, không trong `.env` production
- [ ] Ảnh container đã ghim phiên bản, đã quét lỗ hổng
- [ ] `agent-runner` chạy non-root, có runtime sandbox
- [ ] `AGENT_RUNNER_TOKEN` và `LANGGRAPH_TOKEN` đã đặt (cả hai dịch vụ từ chối chạy/phục vụ khi thiếu)
- [ ] Danh sách `approvers` trong mọi `profiles/*.yaml` là người thật, khác `requesters` với dữ liệu confidential/restricted
- [ ] Không workflow n8n nào có node executeCommand (`validate.sh` bước 5c)
- [ ] Nhật ký kiểm toán đang chảy vào hệ thống log tập trung
- [ ] Ngân sách và giới hạn vòng lặp đã đặt
- [ ] Bảo vệ nhánh trên GitHub: không cho push thẳng vào `main`
- [ ] Đã diễn tập một lần quy trình xoay vòng khoá

---

## 9. Khi có sự cố bảo mật

1. **Chặn** — dừng gateway, đặt `bind: loopback`, tắt kênh có rủi ro
2. **Xoay vòng** — token gateway, khoá nhà cung cấp model, token tích hợp
3. **Rà** — nhật ký kiểm toán, bản ghi phiên, thay đổi cấu hình gần đây
4. **Đánh giá phạm vi** — agent nào có quyền gì trong khoảng thời gian đó
5. **Postmortem** — không quy trách nhiệm cá nhân; tập trung vào lớp phòng thủ nào
   đã không hoạt động và vì sao
