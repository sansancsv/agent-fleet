# 0001. Thu hẹp khoá model theo backend, chưa tách hẳn khỏi container chạy code

- Trạng thái: đã chấp thuận
- Ngày: 2026-09-06 (bổ sung 2026-09-07)
- Người quyết định: chủ sở hữu nền tảng fleet
- Liên quan: ADR-0002 (một cửa ra Internet)

> **Bổ sung 07/09/2026 — phạm vi rộng hơn bản đầu.** ADR này ban đầu chỉ nói về
> `agent-runner`. Rà soát sau đó cho thấy **`openclaw-gateway` cũng nhận cả ba
> khoá model** (`40-openclaw-gateway.yaml`, `envFrom: fleet-model-keys`; compose
> cũng vậy), và gateway cũng chạy agent qua sandbox của OpenClaw. Vậy có **hai**
> nơi khoá model nằm cạnh nơi chạy code, không phải một.
>
> Phần thu hẹp khoá theo backend hiện chỉ áp dụng cho `run-role.sh` và
> `acpx_client.py` — tức là **không bảo vệ đường của gateway**. Gateway chọn
> backend theo cấu hình OpenClaw, không qua hai file đó, nên không có chỗ nào
> để chèn cùng logic mà không sửa hành vi của OpenClaw.
>
> Điều này làm phương án A (proxy model) đáng giá hơn bản đầu đánh giá: nó là
> cách duy nhất đóng được **cả hai** đường bằng một thay đổi.

## Bối cảnh

Sự thật, không có ý kiến:

1. Container `agent-runner` nhận cả ba khoá nhà cung cấp model qua biến môi
   trường: `ACPX_AUTH_ANTHROPIC_API_KEY`, `ACPX_AUTH_OPENAI_API_KEY`,
   `ACPX_AUTH_GEMINI_API_KEY` (`deploy/docker/docker-compose.yml` mục
   `agent-runner`, `deploy/k8s/50-agent-runner.yaml` các dòng 48–53).
2. Cùng container đó chạy `run-role.sh` → `acpx <backend> exec`. Vai trò
   `implementer` và `tester` chạy với `--approve-all`, tức là agent được chạy
   lệnh shell tuỳ ý trong worktree.
3. `execution-plane/runner/server.mjs` hàm `run()` truyền
   `{ ...process.env }` xuống tiến trình con; acpx truyền tiếp xuống các lệnh
   mà agent gọi. Chuỗi kế thừa là liên tục từ biến môi trường của container tới
   lệnh do model quyết định chạy.
4. Hệ quả: một lần prompt injection thành công trong một lượt `implementer`
   (ví dụ qua nội dung file trong repo, qua issue được kéo về, qua kết quả
   tool) là đọc được cả ba khoá.
5. Đây đúng là kịch bản mà `tien-hoa-agentic-patterns-vi.md` §3.3 mô tả là bài
   học đã trả giá: *"credential không bao giờ được nằm trong tầm với của
   sandbox nơi code do agent sinh ra được chạy."*
6. Các lớp phòng thủ hiện có KHÔNG chặn được đường này. NetworkPolicy chỉ cho
   mcporter ra Internet, nhưng khoá bị lộ có thể mang ra ngoài qua chính
   mcporter, hoặc đơn giản là ghi vào file trong repo rồi đi theo pull request.

## Các phương án đã cân nhắc

### A. Proxy model đứng riêng (bản vá đầy đủ)

Dựng một dịch vụ giữ toàn bộ khoá nhà cung cấp; `agent-runner` chỉ nhận một
token phạm vi hẹp và một base URL trỏ tới proxy. Khoá thật không bao giờ nằm
trong container chạy code.

- Ưu: giải quyết triệt để. Thêm được hạn mức chi tiêu và đếm token theo vai trò
  — đúng thứ mà `fleet.metrics` đang thiếu (chỉ số 2 hiện để trống).
- Nhược: cần biết chính xác acpx đọc base URL từ biến nào cho từng backend.
  Repo có `LOCAL_LLM_BASE_URL` nên khả năng cao là có hỗ trợ, nhưng chưa ai kiểm
  chứng trên acpx 0.13.2.
- **Lý do chưa chọn bây giờ:** `CLAUDE.md` mục "Bẫy cấu hình đã trả giá" ghi rõ
  loại lỗi tốn thời gian nhất ở repo này là cấu hình *qua được validate rồi chết
  lúc khởi động*. Đoán tên biến của acpx là đúng cái bẫy đó. Cần một buổi
  `./scripts/preflight.sh` đối chiếu CLI thật trước, không phải đoán trong ADR.

### B. Thu hẹp khoá theo backend (đã chọn)

Trước khi gọi acpx, gỡ khỏi môi trường khoá của những nhà cung cấp không phải
backend của vai trò đang chạy.

- Ưu: làm được ngay, không phụ thuộc hành vi chưa kiểm chứng của acpx, kiểm thử
  được bằng unit test (`provider_env()`), không đổi kiến trúc.
- Nhược: **không giải quyết được vấn đề gốc.** Lượt `implementer` vẫn thấy khoá
  Anthropic. Chỉ hạ bán kính thiệt hại từ ba nhà cung cấp xuống một.

### C. Chấp nhận rủi ro, không làm gì

- Ưu: không tốn công.
- **Lý do loại bỏ:** rủi ro không cân xứng với chi phí giảm thiểu. Phương án B
  tốn khoảng hai chục dòng và chặn được 2/3 bề mặt. Không làm gì là bỏ phần dễ
  nhất chỉ vì chưa làm được phần khó.

## Quyết định

Chọn **B ngay bây giờ**, và giữ **A là đích đến**, không phải là "sẽ cân nhắc".

Tiêu chí quyết định: ưu tiên phần giảm thiểu **kiểm chứng được ngay** hơn phần
sửa triệt để dựa trên giả định chưa kiểm chứng. Đúng kỷ luật "ưu tiên phương án
nhàm chán và đã kiểm chứng" của skill `fleet-adr`.

Triển khai:

- `execution-plane/scripts/run-role.sh` — gỡ khoá sau khi chọn `$AGENT`.
- `orchestration/langgraph/src/fleet/acpx_client.py::provider_env()` — cùng
  logic cho nhánh chạy tại chỗ (dev/test).
- `scripts/validate.sh` bước 5d — chặn việc gỡ mất phần này mà không ai biết.
- Backend lạ → gỡ **tất cả** khoá (fail closed).

## Hệ quả

- Tích cực: một lượt agent bị chiếm quyền chỉ lộ được khoá của **một** nhà cung
  cấp. Việc xoay khoá sau sự cố hẹp lại tương ứng.
- Tích cực: `provider_env()` là hàm thuần tuý có test — phần bảo mật này không
  còn là quy ước trong tài liệu.
- **Tiêu cực:** rủi ro gốc VẪN CÒN. Lượt `implementer` vẫn đọc được khoá
  Anthropic, và đó là khoá đắt nhất. ADR này không được đọc như "đã xử lý xong".
- Tiêu cực: hai bản sao của cùng một logic (shell và Python) phải giữ đồng bộ.
  Đã có phép kiểm ở `validate.sh`, nhưng vẫn là nợ.
- Tiêu cực: nếu sau này thêm backend thứ tư mà quên cập nhật hai bảng, backend
  đó chạy với **không có khoá nào** và hỏng ngay lượt đầu. Cố ý — hỏng ồn ào
  hơn là phơi khoá im lặng.
- Chi phí đảo ngược: dưới một giờ (gỡ hai đoạn, gỡ phép kiểm).

## Điều kiện xem lại

Mở lại và chuyển sang phương án A khi xảy ra **một** trong các điều sau:

1. `./scripts/preflight.sh` xác nhận acpx 0.13.2+ đọc được base URL cho cả ba
   backend từ biến môi trường — lúc đó rào cản kỹ thuật của A biến mất.
2. Cần số token thật cho chỉ số "chi phí trung bình / tác vụ" trong
   `fleet.metrics`. Proxy là chỗ tự nhiên nhất để đếm, nên hai việc này nên làm
   cùng lúc.
3. Có bất kỳ sự cố nào liên quan tới rò khoá model, ở đây hoặc ở nơi khác trong
   tổ chức.
4. Số vai trò có quyền `exec` vượt quá hai (hiện là `implementer` và `tester`;
   `security` và `sre` có exec nhưng không có write) — bề mặt rộng ra thì phần
   giảm thiểu B không còn đủ.
