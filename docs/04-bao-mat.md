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
| 3 | OPA | `role_capabilities.reviewer` không có `write` |
| 4 | Kubernetes | không mount PVC repo ở chế độ ghi |

`scripts/validate.sh` kiểm tra tầng 1 và 3 khớp nhau. Một tầng cấu hình sai thì
ba tầng còn lại vẫn giữ.

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

**c. Chặn mạng.** `agent-runner` không ra được Internet trực tiếp
(`20-networkpolicy.yaml`). Chỉ `mcporter` ra được, và chỉ cổng 443, và có chặn
`169.254.169.254` (metadata endpoint của cloud — đường tuồn thông tin xác thực
kinh điển).

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
| Ghi log | `redact: ["**.apiKey","**.token", ...]` | log nguyên request |

Cấu hình OpenClaw dùng `{ source: "env", id: "TÊN_BIẾN" }` thay vì giá trị trực
tiếp — nhờ đó file cấu hình commit vào git được.

**Nếu nghi ngờ lộ khoá:** xoay vòng ngay, đừng điều tra trước. Xoay vòng mất 5
phút; điều tra mất 5 giờ và trong 5 giờ đó khoá vẫn dùng được.

---

## 5. Nhật ký kiểm toán

`config.d/security.json` ghi JSONL cho tám loại sự kiện: `tool.call`,
`tool.result`, `model.select`, `model.fallback`, `agent.handoff`,
`permission.decision`, `session.create`, `config.change`.

Nhật ký này trả lời được ba câu hỏi mà kiểm toán viên luôn hỏi:

1. *Ai đã yêu cầu gì, khi nào?* → `session.create` + n8n audit node
2. *Agent đã chạm vào hệ thống nào?* → `tool.call` + `tool.result`
3. *Vì sao một hành động bị chặn?* → `permission.decision` + `deny_reason` của OPA

Đẩy vào Loki/OpenSearch/Splunk. Giữ tối thiểu 12 tháng nếu thuộc phạm vi SOC 2
hoặc ISO 27001.

---

## 6. Sandbox

Hai lớp, dùng cả hai:

**Lớp ứng dụng** — `agents.defaults.sandbox` của OpenClaw:
```json5
sandbox: { mode: "all", scope: "agent", network: "none",
           limits: { cpus: 2, memoryMb: 4096, timeoutMs: 900000 } }
```
`scope: "agent"` là quan trọng: agent này không thấy được filesystem của agent khác.

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
