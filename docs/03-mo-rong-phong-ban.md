# Mở rộng ra ngoài phòng kỹ thuật

## Nhận xét nền tảng

Quy trình của mọi phòng ban, khi bóc hết chi tiết nghiệp vụ, đều có cùng một hình:

```
tiếp nhận → kiểm quyền → phân loại → soạn thảo → thẩm định chéo → duyệt → phát hành
```

Marketing viết email ra mắt. Tài chính lập báo cáo tháng. Pháp chế rà hợp đồng.
Kỹ thuật viết code. Bốn việc rất khác nhau, nhưng **khung quy trình giống hệt**.

Cái khác nhau chỉ là bốn thứ:

| | Kỹ thuật | Marketing | Tài chính |
|---|---|---|---|
| Đọc dữ liệu nào | GitHub, Linear | Notion, HubSpot | Kho dữ liệu |
| Ai duyệt | tech lead | brand lead | CFO |
| Model nào được phép | mọi model | mọi model | **chỉ model tự host** |
| Kết quả đi đâu | pull request | trang nháp Notion | tài liệu Drive |

Vì vậy: **thêm một phòng ban = thêm một file YAML**, không sửa code.

---

## Quy trình thêm phòng ban (khoảng 20 phút)

### Bước 1 — Tạo hồ sơ
```bash
cp profiles/marketing.yaml profiles/nhan-su.yaml
```

Sửa bảy trường:

```yaml
name: Nhân sự
dataClass: restricted            # hồ sơ nhân sự → không rời hạ tầng công ty

requesters: ["hr@congty.vn"]     # ai được gửi yêu cầu
approvers:  ["hr-director@congty.vn"]   # PHẢI khác requester

capabilityPack: nhan-su          # trỏ tới capability-plane/packs/nhan-su.json

agents:
  classifier: local-llm          # dataClass=restricted ép dùng model nội bộ
  drafter:    local-llm
  reviewer:   local-llm

categories: [tuyen-dung, danh-gia, chinh-sach, dao-tao, khac]

reviewCriteria:
  - "Không nêu thông tin cá nhân của nhân viên cụ thể"
  - "Ngôn ngữ trung lập, không định kiến"
  - "Trích đúng điều khoản trong sổ tay nhân sự"

systemPrompt: |
  Bạn hỗ trợ phòng Nhân sự. Không bao giờ đưa ra kết luận về một cá nhân.
  Mọi chính sách trích dẫn phải truy được về sổ tay đã ban hành.

output:
  server: notion
  tool: notion-create-pages
  params:
    parentPageId: "${NOTION_HR_DRAFTS_PAGE}"

limits:
  maxCostUsdPerRequest: 2
  maxRevisions: 1
```

### Bước 2 — Tạo gói năng lực
```bash
cp capability-plane/packs/support.json capability-plane/packs/nhan-su.json
```
```json
{
  "servers": ["notion", "google-drive"],
  "clis": ["fleet-wiki", "fleet-drive"],
  "writeAllowed": ["notion"],
  "modelPolicy": { "requireSelfHosted": true }
}
```

### Bước 3 — Tạo bot Slack riêng cho phòng ban
Trong `control-plane/config.d/channels.json` thêm một `accountId`, và trong
`bindings.json` thêm một luật định tuyến. Bot riêng cho mỗi phòng ban là điều
kiện để phân quyền và tính chi phí tách bạch.

⚠️ Kênh Slack cho OpenClaw hiện chưa bật được trên bản CLI đang dùng (xem
`docs/00-kien-truc.md`). Thay thế tạm thời: một Form Trigger hoặc Webhook
Trigger riêng trong n8n cho mỗi phòng ban, gọi cùng `dept-request.flow.ts`.

### Bước 4 — Kiểm chứng
```bash
./scripts/validate.sh
```
Script sẽ báo lỗi nếu: gói năng lực không tồn tại, hoặc người soạn và người thẩm
định trùng backend (trừ trường hợp `dataClass: restricted`).

**Xong.** Không sửa code, không deploy lại. Flow chung
`execution-plane/flows/dept-request.flow.ts` đọc hồ sơ này lúc chạy.

Trên Kubernetes, `langgraph` đọc hồ sơ từ ConfigMap `fleet-profiles` sinh từ
`profiles/`: sau khi merge, chạy lại lệnh đồng bộ ở `docs/01-cai-dat.md` §B
("Hồ sơ phòng ban trên Kubernetes"). Không cần khởi động lại pod. Xoá hồ sơ để gỡ
một phòng ban cũng cần đúng bước này — không chạy thì phòng ban đó vẫn gửi và
duyệt được trên cụm.

---

## Bốn mức nhạy cảm dữ liệu

Đây là trục quyết định **quan trọng hơn** trục "công việc khó hay dễ".

| Mức | Ví dụ | Backend được phép | Ràng buộc thêm |
|---|---|---|---|
| `public` | tài liệu công khai, mã nguồn mở | mọi backend | — |
| `internal` | mã nguồn nội bộ, wiki | mọi backend | — |
| `confidential` | dữ liệu khách hàng đã ẩn danh | Claude, model tự host | yêu cầu zero-retention |
| `restricted` | lương, hồ sơ nhân sự, hợp đồng | **chỉ model tự host** | không ra Internet |

Ràng buộc này được khai báo ở ba nơi phải khớp nhau: `policies.py::MODEL_POLICY`,
`policy/opa/fleet.rego`, và `policy/model-routing.yaml`. Thứ thực sự cưỡng chế
lúc chạy hôm nay là hồ sơ phòng ban (trường `agents.*` chọn backend) cộng
NetworkPolicy của Kubernetes; `assert_backend_allowed` và OPA có test nhưng chưa
được gọi trong đường chạy — việc nối chúng nằm trong lộ trình cải tiến.

---

## Vai trò dùng chung và vai trò riêng

Chín vai trò trong `agents.json` là của phòng kỹ thuật. Phòng ban khác dùng lại:

- `analyst` — dùng chung, mọi phòng ban (chỉ đọc)
- `docs-writer` — dùng chung cho mọi việc soạn thảo
- `orchestrator` — dùng chung, tiếp nhận và định tuyến

Chỉ tạo vai trò mới khi **quyền của nó khác** những vai trò đã có. Tạo vai trò
mới chỉ vì "công việc khác nhau" là sai — công việc khác nhau thể hiện ở
`systemPrompt` trong hồ sơ, không phải ở vai trò mới.

---

## Ba tình huống mở rộng thường gặp

**Phòng ban muốn quy trình riêng, không dùng `dept-request.flow.ts`.**
Viết flow riêng trong `execution-plane/flows/`, vẫn đọc hồ sơ phòng ban để lấy
quyền và ràng buộc. Đừng hard-code phòng ban vào flow.

**Phòng ban muốn tự sửa quy trình mà không cần dev.**
Chuyển quy trình đó sang n8n. Đó chính là lý do n8n có mặt trong kiến trúc.

**Hai phòng ban dùng chung một quy trình nhưng khác người duyệt.**
Cùng một flow, hai hồ sơ khác nhau. Đây là trường hợp mà thiết kế theo hồ sơ trả
công rõ nhất.
