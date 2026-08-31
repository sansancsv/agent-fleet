---
name: fleet-adr
description: Viết biên bản quyết định kiến trúc (ADR). Dùng khi phải chọn giữa nhiều công nghệ, thay đổi ranh giới dịch vụ, đổi lược đồ dữ liệu, hoặc khi ai đó hỏi "nên dùng X hay Y".
version: 1.1.0
user-invocable: true
---

# ADR — Biên bản quyết định kiến trúc

Một quyết định không được ghi lại sẽ được tranh luận lại sau sáu tháng, bởi những
người không biết vì sao đã chọn như vậy. ADR tồn tại để chặn việc đó.

## Khi nào cần ADR
Cần, khi quyết định thoả **ít nhất một**: khó đảo ngược (> 1 tuần để rút lui);
ảnh hưởng nhiều hơn một nhóm; đưa vào một phụ thuộc hạ tầng mới; thay đổi hợp
đồng dữ liệu.

Không cần, khi: chọn tên biến, chọn thư viện tiện ích nhỏ, thay đổi nội bộ một
module mà không lộ ra ngoài.

## Vị trí và tên file
`docs/adr/NNNN-<slug-ngan-gon>.md` — NNNN tăng dần, không tái sử dụng số.

## Khuôn mẫu bắt buộc

```markdown
# NNNN. <Quyết định, viết ở thể khẳng định>

- Trạng thái: đề xuất | đã chấp thuận | đã thay thế bởi ADR-NNNN
- Ngày: YYYY-MM-DD
- Người quyết định: <tên>

## Bối cảnh
Sự thật, ràng buộc, số liệu. Không có ý kiến ở mục này.

## Các phương án đã cân nhắc
### A. <tên> — đánh đổi, và **lý do loại bỏ**
### B. <tên> — đánh đổi, và **lý do loại bỏ**
(Bắt buộc tối thiểu 2 phương án. Một phương án không phải là quyết định.)

## Quyết định
Chọn phương án nào, và tiêu chí quyết định là gì.

## Hệ quả
- Tích cực:
- Tiêu cực: (bắt buộc có — mọi quyết định đều có giá)
- Chi phí đảo ngược: <giờ/ngày/quý>

## Điều kiện xem lại
Quyết định này nên được mở lại khi: <ngưỡng định lượng cụ thể>
```

## Kỷ luật
- Ưu tiên phương án **nhàm chán và đã kiểm chứng**, trừ khi có lý do định lượng.
- Không thiết kế cho quy mô chưa tồn tại. Ghi ngưỡng sẽ kích hoạt thiết kế lại.
- Mục "Hệ quả tiêu cực" trống = ADR chưa hoàn thành.
