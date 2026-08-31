---
name: fleet-release-gate
description: Danh mục kiểm tra bắt buộc trước khi triển khai lên production. Dùng khi chuẩn bị phát hành, deploy, cut release, hoặc khi có migration cơ sở dữ liệu và feature flag cần xác nhận.
version: 2.0.0
user-invocable: true
metadata:
  openclaw:
    requires:
      bins: ["gh", "kubectl"]
---

# Cổng phát hành (release gate)

Không có mục nào trong danh sách này được bỏ qua bằng lời hứa. Mỗi mục hoặc
**xanh**, hoặc **có lý do được ghi lại**, hoặc **chặn phát hành**.

## 1. Trạng thái mã nguồn
- [ ] CI xanh trên đúng commit sẽ phát hành (không phải commit khác)
- [ ] Đủ phê duyệt theo `CODEOWNERS`
- [ ] Không có mục `BLOCKER` chưa xử lý từ reviewer và security
- [ ] Nhánh đã rebase/merge với `main` trong vòng 24 giờ

## 2. Cơ sở dữ liệu
- [ ] Migration **thuận nghịch** (có script rollback đã chạy thử)
- [ ] Migration **tương thích ngược** với phiên bản code đang chạy
      (bắt buộc, vì trong lúc rolling update hai phiên bản cùng tồn tại)
- [ ] Thời gian chạy migration ước lượng < 30 giây, hoặc có kế hoạch chạy tách

## 3. Cờ tính năng (feature flag)
- [ ] Tính năng mới nằm sau cờ, mặc định **tắt**
- [ ] Đã kiểm thử cả hai trạng thái cờ
- [ ] Đã ghi ai được phép bật và bật cho nhóm nào trước

## 4. Khả năng quan sát
- [ ] Có chỉ số/log/alert cho đường đi mới
- [ ] Bảng điều khiển đã có sẵn **trước** khi phát hành, không phải sau

## 5. Kế hoạch rút lui
- [ ] Lệnh rollback đã viết sẵn và đã chạy thử ở staging
- [ ] **Ngưỡng kích hoạt rollback** ghi bằng số:
      ví dụ "tỉ lệ lỗi > 1% trong 5 phút" — không ghi "nếu thấy tệ"
- [ ] Người trực đã biết, có kênh liên lạc

## 6. Con người
- [ ] Không phát hành vào chiều thứ Sáu hoặc trước kỳ nghỉ, trừ khi là bản vá sự cố
- [ ] Có người theo dõi trong 30 phút đầu sau phát hành

## Đầu ra
Trả về bảng: mục | trạng thái (PASS/FAIL/MIỄN) | bằng chứng (URL/lệnh/số).
Nếu có bất kỳ FAIL nào: `outcome: blocked`.
