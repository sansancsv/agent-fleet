---
name: fleet-code-review
description: Quy trình thẩm định mã nguồn chuẩn của công ty. Dùng khi cần review một pull request, một diff, hoặc khi được hỏi "code này an toàn chưa", "có nên merge không".
version: 1.2.0
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: ["git"]
      config: ["agents.entries.reviewer"]
---

# Thẩm định mã nguồn (code review) — chuẩn fleet

## Khi nào dùng
Có một diff cần đánh giá trước khi merge. Không dùng để viết code.

## Nguyên tắc bất di bất dịch
1. **Chỉ đọc.** Không sửa file, không chạy lệnh thay đổi trạng thái.
2. **Bằng chứng hoặc im lặng.** Mỗi phát hiện phải có `file:dòng` và một kịch bản
   hỏng cụ thể (đầu vào nào → hậu quả gì). Không có kịch bản = không phải phát hiện.
3. **Model thẩm định phải khác model đã viết code.** Nếu bạn phát hiện mình chính là
   người vừa viết đoạn code này, hãy nói ra và yêu cầu đổi backend.

## Trình tự
```bash
git fetch origin main
git diff --stat origin/main...HEAD      # nhìn quy mô trước
git diff origin/main...HEAD             # rồi mới đọc chi tiết
```

Soi theo đúng thứ tự này, dừng lại ở mức đủ nghiêm trọng:

| Thứ tự | Hạng mục | Câu hỏi dẫn |
|---|---|---|
| 1 | Đúng sai | Biên? null/undefined? tranh chấp đồng thời? lỗi nuốt im lặng? |
| 2 | Bảo mật | Đầu vào người dùng chạm tới lệnh/truy vấn/đường dẫn ở đâu? Kiểm soát truy cập ở tầng nào? |
| 3 | Hiệu năng | Truy vấn N+1? Vòng lặp lồng nhau trên dữ liệu lớn? Tải hết vào bộ nhớ? |
| 4 | Bảo trì | Chỉ nêu khi thực sự cản trở người sau. Không nêu ý kiến thẩm mỹ. |

## Định dạng phát hiện
```
[BLOCKER] src/api/user.ts:142
Truy vấn ghép chuỗi từ req.query.sort → chèn SQL.
Kịch bản: sort="id; DROP TABLE users--" → mất bảng.
Chặn: dùng tham số hoá, hoặc allowlist tên cột.
```

Mức độ: `BLOCKER` (chặn merge) · `MAJOR` (phải sửa trước release) ·
`MINOR` (nên sửa) · `NIT` (tuỳ chọn).

## Kết thúc
Luôn đóng bằng khối `fleet-status`. Nếu không có gì chặn merge, ghi rõ
`outcome: success` và nói thẳng "không có mục chặn" — **đừng bịa phát hiện để
trông có vẻ hữu ích**.
