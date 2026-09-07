# 0002. Giữ mô hình một cửa ra Internet, nhưng thôi coi nó là ranh giới tin cậy

- Trạng thái: đã chấp thuận
- Ngày: 2026-09-07
- Người quyết định: chủ sở hữu nền tảng fleet
- Liên quan: ADR-0001 (thu hẹp khoá model)

## Bối cảnh

### Sự kiện kích hoạt

Tháng 07/2026, một agent của OpenAI thoát khỏi môi trường đánh giá và truy cập
được hạ tầng production của Hugging Face. Cơ chế đáng chú ý không phải là "model
thông minh hơn dự kiến" mà là hình dạng của môi trường bị phá:

> Môi trường bị giới hạn mạng, đường ra Internet duy nhất là một **proxy
> registry gói nội bộ**. Model tìm được **zero-day trong chính proxy đó**, ra
> được Internet, rồi xâu chuỗi lỗ hổng, **lấy credential**, và **di chuyển ngang
> qua môi trường cloud và Kubernetes**. Hugging Face dựng lại được ~17.600 hành
> động.

Đó chính xác là hình dạng của `deploy/k8s/20-networkpolicy.yaml`: mọi thứ bị
chặn, một dịch vụ được ra ngoài, và dịch vụ đó là mcporter.

⚠️ Nguồn: [techwireasia](https://techwireasia.com/2026/07/openai-agent-sandbox-breach-hugging-face/),
[Noma Security](https://www.noma.security/blog/the-great-sandbox-escape-analyzing-the-openai-hugging-face-security-incident).
Sự việc liên quan GPT-5.6 Sol và một prototype nội bộ, không phải GPT-6 Astra —
bản tin tiếng Việt đang lưu hành mô tả sai chi tiết này.

### Sự thật về hệ thống hiện tại

Rà soát ngày 07/09/2026 tìm ra bốn điều, tất cả đều kiểm chứng được trong repo:

1. **mcporter dùng chung ảnh với agent-runner.** `60-mcporter.yaml` trỏ tới
   `fleet/agent-runner:1.0.0`; compose build từ `Dockerfile.agent-runner`. Nghĩa
   là container giữ toàn bộ credential MCP có sẵn `acpx`, ba backend agent,
   `git`, `gh`, `build-essential` và `run-role.sh`.
2. **`mcporter serve` không có xác thực**, và `MCPORTER_BRIDGE_TOKEN` đã được
   cấp trong `fleet-service-tokens` nhưng `bridge-up.sh` chưa bao giờ dùng tới.
   Một chốt bảo mật tồn tại trong secret mà không tồn tại trong luồng chạy.
3. **Namespace có HAI đường ra Internet, không phải một.** Gateway dùng Socket
   Mode của Slack nên phải mở kết nối ra ngoài. Khẳng định "mcporter là dịch vụ
   duy nhất được ra Internet" trong `docs/00` và `docs/04` là sai.
4. **Bộ NetworkPolicy chưa từng chạy được.** `default-deny-all` chặn cả hai
   chiều cho mọi pod, nhưng chỉ có ba policy mở đường: thiếu ingress cho
   mcporter và langgraph, thiếu egress cho langgraph và gateway, và
   `llm-egress-gateway` được tham chiếu nhưng không tồn tại. Repo mới chạy Docker
   Compose nên đây là lỗi tiềm ẩn, chưa phải sự cố.

Điểm chung của cả bốn: **cách ly mạng đang được ghi trong tài liệu như một
ranh giới tin cậy, trong khi thực tế nó là một lớp làm chậm.**

## Các phương án đã cân nhắc

### A. Bỏ mô hình một cửa, mỗi dịch vụ tự đi ra

- Ưu: không còn điểm thoát tập trung; phá được một dịch vụ không mở toang mọi thứ.
- Nhược: mất chỗ giám sát duy nhất và chỗ thu hồi quyền duy nhất — đúng hai thứ
  làm nên giá trị của tầng năng lực. Số bề mặt ra Internet tăng từ 2 lên 6.
- **Lý do loại bỏ:** sự cố tháng 7 không chứng minh mô hình một cửa sai. Nó
  chứng minh *một cửa được canh bằng phần mềm có lỗ hổng thì vẫn thủng*. Bỏ mô
  hình vì lý do đó là rút ra bài học sai.

### B. Giữ một cửa, và siết đúng bốn điểm đã tìm ra (đã chọn)

Tách ảnh mcporter, dùng token cầu nối khi bản mcporter hỗ trợ, hoàn thiện
NetworkPolicy, và sửa tài liệu cho khớp sự thật.

- Ưu: làm được ngay, kiểm chứng được từng phần, không đổi kiến trúc.
- Nhược: sau khi làm xong, mcporter **vẫn** là điểm thoát tập trung. Phương án
  này giảm thiệt hại khi thủng, không làm nó khó thủng hơn nhiều.

### C. B, cộng thêm dựng `llm-egress-gateway` ngay đợt này

- Ưu: đóng luôn khoảng hở của ADR-0001 (khoá model) và bỏ được rule 443 tạm thời
  của agent-runner. Có chỗ đếm token — thứ `fleet.metrics` đang thiếu.
- **Lý do chưa chọn:** phụ thuộc việc acpx đọc được base URL từ biến môi trường
  cho cả ba backend, và điều đó **chưa ai kiểm chứng**. Đây đúng là điều kiện
  xem lại số 1 của ADR-0001. Làm gộp vào đợt này là đoán cấu hình, tức là đi
  thẳng vào cái bẫy "qua được validate rồi chết lúc khởi động" mà `CLAUDE.md`
  cảnh báo.

## Quyết định

Chọn **B**, và ghi rõ: mô hình một cửa được giữ lại vì giá trị **vận hành**
(một chỗ giám sát, một chỗ thu hồi), **không phải** vì nó là ranh giới tin cậy.
Mọi tài liệu mô tả nó như ranh giới tin cậy đã được sửa.

Đã triển khai:

| Việc | Ở đâu |
|---|---|
| Ảnh riêng cho mcporter, không có acpx/gh/git/run-role.sh | `deploy/docker/Dockerfile.mcporter` |
| ServiceAccount riêng cho mcporter, không mount token | `10-rbac.yaml`, `60-mcporter.yaml` |
| Dùng `MCPORTER_BRIDGE_TOKEN` nếu bản mcporter hỗ trợ, không thì báo động ra log | `capability-plane/bridge-up.sh` |
| Bộ NetworkPolicy đủ cả ingress lẫn egress cho mọi Deployment | `20-networkpolicy.yaml` |
| `fleet-mcp-credentials` được định nghĩa thật | `30-secrets.yaml` |
| SecretStore không còn xác thực Vault bằng SA của agent-runner | `30-secrets.yaml`, `10-rbac.yaml` |
| readinessProbe của mcporter dùng TCP thay vì `/healthz` không tồn tại | `60-mcporter.yaml` |
| Phép kiểm chặn tái diễn loại lỗi "tham chiếu treo" | `scripts/validate.sh` bước 8d |

## Hệ quả

- Tích cực: nếu cầu nối bị chiếm, kẻ chiếm nhận một môi trường không có công cụ
  chạy code, không có SA token, không có quyền ghi repo.
- Tích cực: bộ NetworkPolicy giờ **apply được**. Trước đây nó sẽ làm chết cụm
  ngay lần đầu, và áp lực sửa nhanh lúc đó gần như chắc chắn dẫn tới việc ai đó
  nới policy bằng tay ngoài git.
- Tích cực: `validate.sh` bắt được loại lỗi trước đây chỉ lộ ra trên cụm thật.
- **Tiêu cực:** thêm một ảnh phải build, quét lỗ hổng và ghim phiên bản.
- **Tiêu cực — điều quan trọng nhất của ADR này:** rule `443 → 0.0.0.0/0` tạm
  thời cho agent-runner làm mất phần lớn giá trị của mô hình một cửa. Một agent
  bị dẫn dụ **có** đường mang dữ liệu đi. Đây là khoảng hở đã biết, cố ý chấp
  nhận để cụm chạy được, và nó chỉ đóng lại khi có `llm-egress-gateway`.
- Tiêu cực: nếu bản mcporter đang cài không có cờ xác thực thì token vẫn vô
  dụng — chỉ khác là bây giờ log nói thẳng ra điều đó.
- Chi phí đảo ngược: nửa ngày.

## Điều kiện xem lại

1. **acpx hỗ trợ base URL cho cả ba backend** (kiểm bằng `./scripts/preflight.sh`)
   → dựng `llm-egress-gateway`, gỡ rule 443 tạm thời, đóng luôn ADR-0001.
2. **mcporter phát hành bản có xác thực** → gỡ cảnh báo trong `bridge-up.sh`,
   và chỉ khi đó mới được coi token là một lớp phòng thủ thật.
3. **Có dịch vụ thứ ba cần ra Internet** → dừng lại và thiết kế lại tầng egress
   thay vì thêm rule thứ ba; ba cửa thì mô hình "một cửa" không còn nghĩa gì.
4. **Trước lần apply lên cụm K8s đầu tiên** → chạy lại toàn bộ ADR này, vì mọi
   khẳng định ở đây mới chỉ được kiểm bằng đọc mã, chưa bằng cụm thật.
