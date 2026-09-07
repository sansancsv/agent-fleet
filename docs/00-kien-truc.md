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
   • review   : acpx codex,  quyền deny-all               ← khác nhà cung cấp
     (mỗi lượt agent = một POST /run tới dịch vụ agent-runner)
   • gate     : hàm thuần tuý đếm mục chặn                ← xác định
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

Điểm cần chú ý ở bước 4: **mọi lần agent chạm vào hệ thống ngoài đều đi qua
mcporter**. Đó là lý do có tầng năng lực: một chỗ giám sát, một chỗ thu hồi
quyền, một chỗ giữ credential.

**Đừng đọc câu trên thành "agent không có đường ra Internet".** Rà soát ngày
07/09/2026 cho thấy khẳng định đó, vốn có trong bản trước của tài liệu này, là
sai ở hai chỗ:

- `openclaw-gateway` phải mở kết nối ra ngoài cho Socket Mode của Slack. Vậy
  namespace có **hai** đường ra Internet, không phải một.
- Chừng nào chưa có `llm-egress-gateway`, `agent-runner` phải tự gọi API model,
  tức là cũng cần ra 443. Rule tạm thời này nằm trong
  `deploy/k8s/20-networkpolicy.yaml`, có đánh dấu ⚠️.

Cách ly mạng ở đây là **một lớp làm chậm, không phải ranh giới tin cậy**. Sự cố
Hugging Face tháng 07/2026 cho thấy một môi trường chỉ có đúng một cửa ra vẫn
thoát được, bằng cách khai thác lỗ hổng trong chính cái proxy giữ cửa. Lý do
đầy đủ và điều kiện xem lại: `docs/adr/0002`.

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
