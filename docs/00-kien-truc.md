# Kiến trúc

## Vì sao phải tách bốn tầng

Cách làm phổ biến là cài một agent CLI, cắm vài MCP server, viết một prompt dài,
rồi gọi đó là "AI team". Cách đó hỏng ở đúng ba điểm khi lên quy mô doanh nghiệp:

1. **Không phân quyền được.** Một agent vạn năng có mọi quyền. Không trả lời được
   câu hỏi kiểm toán "ai được sửa file gì".
2. **Không thay thế được thành phần.** Đổi nhà cung cấp model phải viết lại mọi thứ.
3. **Không kiểm toán được.** Không biết tháng trước agent đã gọi tool nào, cho ai.

Bốn tầng giải quyết đúng ba điểm đó, bằng cách mỗi tầng trả lời **một** câu hỏi.

| Tầng | Công cụ | Câu hỏi | Thay thế được bằng |
|---|---|---|---|
| Điều khiển | OpenClaw Gateway | Ai được nói chuyện với đội agent? Tin nhắn đi tới vai trò nào? | Bất kỳ gateway nào có định tuyến + phiên |
| Thực thi | acpx | Agent chạy ở đâu, quyền gì, backend nào? | Bất kỳ client ACP nào |
| Năng lực | mcporter | Agent chạm được hệ thống nào? | Bất kỳ MCP gateway nào |
| Phân phối | ClawHub | Quy trình nội bộ phát hành ra sao? | Git riêng tư, registry nội bộ |

Ranh giới rõ nghĩa là: **đổi một tầng không phải sửa ba tầng kia**.

---

## Luồng một yêu cầu đi qua hệ thống

```
1. Người gõ trong Slack:  "@fleet thêm rate limit cho API public"
        │
2. OpenClaw Gateway
   • kiểm tra người gửi có trong allowlist không          ← chốt danh tính
   • tra binding: kênh #eng + account acc-engineering
     → agent "orchestrator"
   • mở/khôi phục phiên riêng của người đó
        │
3. orchestrator đọc skill "fleet-dept-intake"
   • phân loại: đây là việc lặp lại, có quy trình
   • gọi LangGraph thay vì tự làm
        │
4. LangGraph  (thread_id = mã công việc)
   • prepare  : tạo git worktree riêng                    ← xác định
   • triage   : phân loại rủi ro                          ← model, đầu ra ép về 3 nhãn
   • implement: acpx claude, quyền approve-all            ← phi xác định
     (không hoàn tất hoặc diff rỗng → leo thang ngay)     ← xác định
   • review   : acpx codex,  quyền deny-all               ← khác nhà cung cấp
     (diff do code trích sẵn; vượt trần → leo thang)      ← xác định
     (mỗi lượt agent = một POST /run tới dịch vụ agent-runner)
   • gate     : hàm thuần tuý: thẩm định không hoàn tất   ← xác định
                → leo thang; còn mục chặn → sửa lại
   • approval : interrupt() — ghi trạng thái, giải phóng pod
        │
5. Người duyệt → POST /runs/<id>/resume, `by` phải nằm trong approvers của hồ sơ
   → LangGraph chạy tiếp từ đúng đó
        │
6. open_pr : push + gh pr create --draft
        │
7. Dấu vết: audit của gateway (volume openclaw-audit), permission.decision của
   LangGraph và log từng lượt của agent-runner — xem docs/04 §5
```

**Đừng đọc bước 1–2 thành "kênh vào chính là Slack".** Kênh Slack cho OpenClaw
hiện chưa bật được (xem `CLAUDE.md` mục "Bẫy cấu hình cần biết"). Đường vào
thật đang dùng là webhook n8n (`orchestration/n8n/workflows/01-intake-router.json`),
không đi qua OpenClaw Gateway ở bước 2. Sơ đồ trên vẫn đúng là *thiết kế đích*;
chỉ chưa đúng là *đường đang chạy*.

Điểm cần chú ý ở bước 4: **mọi lần agent chạm vào hệ thống ngoài đều đi qua
mcporter**. Đó là lý do có tầng năng lực: một chỗ giám sát, một chỗ thu hồi
quyền, một chỗ giữ credential.

**Đừng đọc câu trên thành "agent không có đường ra Internet".** Cách ly mạng
ở đây là **một lớp làm chậm, không phải ranh giới tin cậy**: namespace có
**hai** đường ra Internet — `openclaw-gateway` cho Socket Mode của Slack, và
`agent-runner` (tạm thời, cho tới khi có `llm-egress-gateway`, đánh dấu ⚠️
trong `deploy/k8s/20-networkpolicy.yaml`).

---

## Vì sao chín vai trò chứ không phải một

Ba lý do, xếp theo mức quan trọng:

**1. Phân quyền.** `reviewer` không sửa được file. Đó không phải quy ước trong
prompt — đó là cấu hình được cưỡng chế ở bốn tầng (OpenClaw tool policy, cờ
quyền của acpx, allowedTools của mcporter, RBAC của Kubernetes). Một agent vạn
năng không làm được điều này.

**2. Đa dạng hoá model.** Vai trò tách rời cho phép gán backend khác nhau. Đây
không phải để tiết kiệm — đây là chất lượng: một model bỏ sót loại lỗi nào thì
bỏ sót ổn định, nên người chấm phải khác người viết.

**3. Ngữ cảnh gọn.** Mỗi vai trò chỉ nạp skill và tool của mình. Agent vạn năng
với 200 tool trong ngữ cảnh chọn nhầm tool thường xuyên hơn hẳn.

---

## Trạng thái nằm ở đâu

Đây là câu hỏi quyết định hệ thống có chạy được trong Kubernetes hay không.

| Thành phần | Trạng thái | Nơi lưu | Scale ngang được? |
|---|---|---|---|
| OpenClaw Gateway | phiên chat, SQLite | PVC | **Không** — 1 bản sao |
| acpx (agent-runner) | phiên trên đĩa, tạm | emptyDir + PVC repo | Có |
| mcporter | không (chỉ cache) | emptyDir | Có |
| LangGraph | **checkpoint từng bước** | PostgreSQL | Có |
| n8n | execution + credential | PostgreSQL + Redis | Có (queue mode) |

Quy tắc rút ra: **quy trình dài phải chạy trên LangGraph, không phải trong phiên
OpenClaw**, vì chỉ LangGraph có trạng thái nằm ngoài pod.
