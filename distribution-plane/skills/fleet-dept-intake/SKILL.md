---
name: fleet-dept-intake
description: Tiếp nhận và định tuyến yêu cầu từ các phòng ban vào đúng vai trò agent và đúng loại quy trình. Dùng khi nhận một yêu cầu chưa rõ ràng, cần phân rã, hoặc khi phải quyết định chạy quy trình xác định hay để agent tự do xử lý.
version: 1.0.0
user-invocable: true
---

# Tiếp nhận yêu cầu phòng ban (department intake)

## Bước 1 — Yêu cầu này thuộc loại quy trình nào?

Đây là quyết định quan trọng nhất, và phải làm **trước** khi tiêu bất kỳ token nào.

| Dấu hiệu | Loại | Hành động |
|---|---|---|
| Đã làm ≥ 3 lần, các bước giống nhau, đầu ra có khuôn | **Xác định** | Chạy flow/n8n có sẵn |
| Có nhánh rẽ nhưng đếm được, cần lưu trạng thái lâu, có người duyệt giữa chừng | **Xác định, bền vững** | LangGraph |
| Chưa từng làm, phạm vi mơ hồ, cần khám phá | **Phi xác định** | Phiên agent tự do |
| Lặp lại nhưng chưa có quy trình | **Sắp thành xác định** | Làm tay lần này, **ghi lại các bước** để lần sau tự động hoá |

Nói rõ lựa chọn và lý do trước khi làm.

## Bước 2 — Đủ thông tin chưa?

Hỏi **tối đa một** câu, và chỉ hỏi khi thiếu nó thì chắc chắn làm sai.
Thiếu thông tin không chặn thì cứ giả định, ghi rõ giả định, rồi làm.

Bốn thứ hầu như luôn cần biết: **ai dùng kết quả**, **hạn khi nào**,
**định dạng đầu ra**, **được chạm vào dữ liệu nào**.

## Bước 3 — Giao cho ai

| Loại yêu cầu | Vai trò | Ghi chú |
|---|---|---|
| Thiết kế, chọn công nghệ | `architect` | Đầu ra là ADR |
| Viết/sửa code | `implementer` | Luôn trên worktree riêng |
| Đánh giá code | `reviewer` | Backend khác implementer |
| Rủi ro bảo mật/tuân thủ | `security` | Chỉ đọc |
| Sự cố production | `sre` | Chặn thiệt hại trước |
| Số liệu, báo cáo | `analyst` | Luôn kèm nguồn và cỡ mẫu |
| Tài liệu, thông báo | `docs-writer` | |

## Bước 4 — Ràng buộc theo phòng ban

Đọc `profiles/<phòng-ban>.yaml` để biết: nguồn dữ liệu được phép, người duyệt,
model được phép (một số phòng ban chỉ được dùng model tự host), và đích phát hành.
**Không suy đoán** các ràng buộc này.
