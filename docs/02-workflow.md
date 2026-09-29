# Quy trình xác định và quy trình phi xác định

Đây là chương quan trọng nhất của toàn bộ tài liệu. Hầu hết các dự án agent thất
bại không phải vì model yếu, mà vì **đặt sai ranh giới** giữa phần cần chắc chắn
và phần cần linh hoạt.

---

## 1. Hai loại quy trình

**Quy trình xác định** (deterministic workflow): cùng đầu vào cho cùng đầu ra.
Các bước biết trước, nhánh rẽ đếm được, ai đọc cũng hiểu quy trình chạy thế nào.
Ví dụ: "PR mở → chạy test → nếu xanh thì gắn nhãn → thông báo kênh #eng".

**Quy trình phi xác định** (non-deterministic workflow): kết quả phụ thuộc phán
đoán. Không liệt kê trước được các bước. Ví dụ: "tìm nguyên nhân tại sao trang
thanh toán chậm".

Hầu hết công việc thật là **cả hai**, lồng vào nhau.

---

## 2. Nguyên tắc: xác định bọc ngoài, phi xác định bên trong

> **Khung quy trình quyết định *thứ tự* và *điều kiện*. Agent quyết định *cách làm*
> trong một bước.**

Cụ thể trong repo này:

```
┌─ n8n / LangGraph / acpx flow ────────────── XÁC ĐỊNH ─┐
│                                                       │
│   bước 1 ──► bước 2 ──► [nhánh?] ──► bước 3           │
│                │                                      │
│                └──► ┌───────────────────────┐         │
│                     │  một lượt agent       │  PHI    │
│                     │  (acpx / OpenClaw)    │  XÁC    │
│                     └───────────────────────┘  ĐỊNH   │
└───────────────────────────────────────────────────────┘
```

Ba hệ quả thực tế:

1. **Quyết định chặn/không chặn phải nằm trong code, không nằm trong prompt.**
   Model *nêu phát hiện*; hàm `gate()` trong `graph.py` *quyết định*. Nhờ vậy hai
   lần chạy giống nhau cho cùng kết quả, và kiểm toán viên đọc được luật.

2. **Nhánh rẽ phải ép về tập hữu hạn.** Dùng `decision(choices=[...])` của acpx
   flow, hoặc ép model chỉ in một nhãn rồi `risk_from_text()` chuẩn hoá. Không
   bao giờ rẽ nhánh bằng `if "có vẻ nguy hiểm" in response`.

3. **Khi không chắc thì nghiêng về phía kiểm soát chặt hơn.** `risk_from_text()`
   trả `"risky"` khi không nhận dạng được nhãn — chứ không trả `"trivial"`.

---

## 3. Chọn công cụ điều phối nào

| | **n8n** | **LangGraph** | **acpx flow** |
|---|---|---|---|
| Ai sở hữu | Phòng ban nghiệp vụ, ops | Kỹ sư nền tảng | Nhóm dev của repo |
| Sửa bằng | Kéo–thả trên trình duyệt | Python trong git | TypeScript trong repo |
| Kích hoạt | webhook, lịch, sự kiện app | HTTP API / SDK | CLI, CI |
| Lưu trạng thái | Bản ghi execution (Postgres) | Checkpointer Postgres, **từng bước** | Gói run trên đĩa |
| Chờ người | Node Wait (giờ) | `interrupt()` — ngày, bền vững | Node `checkpoint` |
| Sống sót pod restart | Có (queue mode) | **Có, chính xác từ bước đang dở** | Không — chạy lại từ đầu |
| Tích hợp SaaS | **400+ node sẵn** | Tự viết | Qua mcporter |
| Ai đọc hiểu được | Người không lập trình | Lập trình viên | Lập trình viên |

**Quy tắc chọn trong ba câu:**

- Quy trình đi qua nhiều hệ thống SaaS, người nghiệp vụ cần tự sửa → **n8n**.
- Quy trình dừng chờ người hàng giờ/ngày và phải chạy tiếp đúng từ điểm dừng → **LangGraph**.
- Quy trình chỉ sống trong một repo, cần versioned cùng code → **acpx flow**.

Ba cái này **không thay thế nhau**. Trong repo này chúng xếp chồng:
n8n tiếp nhận và định tuyến → LangGraph chạy quy trình dài → acpx thực thi từng
lượt agent.

---

## 4. Bốn cấp độ tự động hoá

Đừng nhảy thẳng lên cấp 4. Đi tuần tự, mỗi cấp phải chạy ổn định vài tuần.

| Cấp | Tên | Con người làm gì | Công cụ |
|---|---|---|---|
| 0 | Thủ công có ghi chép | Làm tay, ghi lại từng bước | — |
| 1 | Agent hỗ trợ | Hỏi agent, tự quyết định | OpenClaw chat |
| 2 | **Agent đề xuất, người duyệt** | Duyệt/từ chối ở checkpoint | LangGraph + `interrupt()` |
| 3 | Agent tự chạy, người giám sát | Xem báo cáo, can thiệp khi lệch | n8n + cảnh báo |
| 4 | Tự chạy hoàn toàn | Chỉ xem số liệu tổng hợp | Chỉ cho việc rủi ro thấp |

**Cấp 2 là nơi hầu hết công việc kỹ thuật nên dừng lại.** Cấp 4 chỉ dành cho
việc mà sai cũng không thiệt hại: gắn nhãn issue, tổng hợp standup, dọn nhánh cũ.

---

## 5. Mẫu quy trình có sẵn trong repo

### `feature-delivery.flow.ts` — giao hàng tính năng
```
chuẩn bị worktree → phân loại rủi ro → [risky? viết ADR] → hiện thực
→ viết test → thẩm định chéo → [thẩm định không hoàn tất? DỪNG CHỜ NGƯỜI]
→ [có mục chặn? sửa lại, tối đa 2 vòng] → CHỜ NGƯỜI DUYỆT → mở PR nháp
```
Điểm đáng chú ý: `implement` dùng Claude, `review` dùng Codex. Khác nhà cung cấp.
`gate` kiểm từng bước thẩm định bắt buộc đã hoàn tất chưa (`flows/fleet-status.ts`,
cùng định nghĩa với `turn_problem()`) **trước** khi đếm mục chặn.

### `incident-triage.flow.ts` — xử lý sự cố
```
thu thập bối cảnh (lệnh cố định) → nêu giả thuyết → chọn hành động
→ CHỜ NGƯỜI DUYỆT (kể cả SEV1) → thực thi → viết postmortem
```
Điểm đáng chú ý: agent **không được tự gõ lệnh vào cụm**. Nó chọn một trong bốn
hành động đã định nghĩa sẵn; ánh xạ hành động → lệnh nằm trong code.

### `dept-request.flow.ts` — yêu cầu phòng ban (đa dụng)
```
nạp hồ sơ phòng ban → kiểm quyền (trước khi tiêu token) → phân loại
→ soạn thảo → thẩm định chéo → [không hoàn tất? dừng chờ người] → [sửa lại]
→ CHỜ DUYỆT → phát hành
```
Điểm đáng chú ý: không có gì riêng cho phòng ban nào trong code. Tất cả nằm
trong `profiles/*.yaml`.

### `02-pr-review-gate.json` (n8n) — cổng thẩm định pull request
```
PR mở/cập nhật → lấy mã nguồn → 3 lượt thẩm định (reviewer · security · analyst)
→ chờ đủ cả ba → hợp nhất bằng luật → nhận xét + trạng thái commit fleet/cross-review
```
Điểm đáng chú ý: **fail closed**. Lượt nào không hoàn tất (runner lỗi, thoát mã
≠ 0, thiếu khối `fleet-status`, `outcome: blocked`/`rejected`) thì trạng thái là
`error`, không bao giờ `success`: một lượt hỏng cũng cho ra 0 phát hiện, y hệt
một PR sạch. `scripts/validate.sh` bước 5e chạy code của node hợp nhất với mọi
tổ hợp kết quả mẫu để giữ tính chất này.

---

## 6. Ba lỗi hay gặp

**Lỗi 1 — để agent tự lặp không giới hạn.**
Agent "thử lại cho tới khi xong" là cách đốt ngân sách nhanh nhất, và nó che
giấu vấn đề thật. Mọi vòng lặp trong repo này đều có `maxStepRuns` /
`max_revisions`. Hết lượt thì leo thang cho người, không thử tiếp.

**Lỗi 2 — nhồi cả quy trình vào một prompt dài.**
"Hãy phân tích, rồi viết code, rồi test, rồi review, rồi mở PR" trong một prompt
sẽ cho kết quả tệ ở mọi bước và không debug được bước nào hỏng. Tách bước, mỗi
bước một lượt agent, mỗi bước có đầu ra kiểm tra được.

**Lỗi 3 — dùng cùng một model cho cả viết và chấm.**
Model bỏ sót loại lỗi nào thì bỏ sót ổn định. Bắt buộc khác **nhà cung cấp**, không
chỉ khác tên model. `scripts/validate.sh` kiểm tra điều này cho mọi hồ sơ phòng ban.
