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
`docs/00-kien-truc.md`). Thay thế tạm thời: gửi vào webhook tiếp nhận của n8n
(`01-intake-router.json`, trường `profile: <tên>`), hoặc một Form/Webhook
Trigger riêng cho mỗi phòng ban gọi cùng đường đó. Lưu ý: đường n8n hiện chỉ
chạy MỘT lượt agent (vai trò `analyst`) qua chốt dataClass, CHƯA chạy
`dept-request.flow.ts` — xem mục "Bốn mức nhạy cảm dữ liệu" bên dưới.

### Bước 4 — Kiểm chứng
```bash
./scripts/validate.sh
```
Script sẽ báo lỗi nếu: gói năng lực không tồn tại; người soạn và người thẩm
định trùng backend (trừ trường hợp `dataClass: restricted`); hoặc một backend
trong `agents.*` không nằm trong `allowedBackends` của `dataClass` của hồ sơ
(bước 8a, đọc `policy/model-routing.yaml`).

**Xong.** Không sửa code, không deploy lại. Flow chung
`execution-plane/flows/dept-request.flow.ts` đọc hồ sơ này lúc chạy; đường n8n
dùng `requesters` và `dataClass` của hồ sơ qua `server.py`.

---

## Bốn mức nhạy cảm dữ liệu

Đây là trục quyết định **quan trọng hơn** trục "công việc khó hay dễ".

| Mức | Ví dụ | Backend được phép | Ràng buộc thêm |
|---|---|---|---|
| `public` | tài liệu công khai, mã nguồn mở | mọi backend | — |
| `internal` | mã nguồn nội bộ, wiki | mọi backend | — |
| `confidential` | dữ liệu khách hàng đã ẩn danh | Claude, model tự host | yêu cầu zero-retention |
| `restricted` | lương, hồ sơ nhân sự, hợp đồng | **chỉ model tự host** | không ra Internet |

Ràng buộc này khai ở ba bảng: `policy/model-routing.yaml` (nguồn sự thật),
`policies.py::MODEL_POLICY` và `policy/opa/fleet.rego`. Nó được cưỡng chế ở hai
tầng.

**Tĩnh — `scripts/validate.sh` bước 8a** (`scripts/check-model-policy.py`):

- mọi backend trong `agents.*` của mọi hồ sơ phải nằm trong `allowedBackends`
  của `dataClass` của chính hồ sơ đó; `dataClass` lạ hoặc thiếu `agents` là lỗi;
- `MODEL_POLICY` và `allowed_backends` của rego phải khớp `model-routing.yaml`;
- backend của từng vai trò trong `ROLE_BACKENDS` (`acpx_client.py`) phải trùng
  bảng `case "$ROLE"` trong `run-role.sh`: chốt lúc chạy tra bảng thứ nhất,
  agent-runner chạy theo bảng thứ hai;
- `01-intake-router.json` không được gọi thẳng agent-runner.

**Lúc chạy — `POST /profiles/<tên>/run` trong `server.py`.** Đây là đường n8n
dành cho phòng ban ngoài kỹ thuật. Trước khi có lượt agent nào, server.py kiểm
người gửi thuộc `requesters`, rồi gọi `assert_backend_allowed(<backend của vai
trò analyst>, dataClass)`. Không được phép — kể cả `dataClass` thiếu hoặc gõ
nhầm — thì trả 403 kèm lý do, ghi audit ra stdout và vào vết chạy
(`permission.denied`). Không có đường "chạy tạm" trên backend khác. Workflow n8n
chuyển nguyên mã và lý do đó cho bên gửi. Tuyến khẩn cấp của n8n (SRE qua
OpenClaw — Claude, dự phòng OpenAI) không qua chốt này, nên chỉ hồ sơ
`engineering` được đi tắt; phòng ban khác luôn đi qua chốt.

**Lúc chạy — `POST /runs/wait` trong `server.py`.** Đây là đường vào đồ thị kỹ
thuật (`graph.py`). TRƯỚC `graph.ainvoke`, tức trước khi có thread nào,
server.py nạp hồ sơ của `profile` trong input — bỏ trống thì `engineering`, như
`initial_state`; không có hồ sơ đó thì 404 — rồi gọi `assert_backend_allowed`
cho backend của MỌI vai trò mà đồ thị có thể gọi (`graph.GRAPH_ROLES`:
orchestrator, architect, implementer chạy Claude; reviewer, security chạy
Codex). Kiểm cả vai trò chỉ chạy trên nhánh `risky`, vì nhánh nào chạy do một
lượt model phân loại quyết định, khi dữ liệu đã tới model rồi. Một vai trò không
được phép là đủ để từ chối cả lượt: 403 kèm lý do, audit `policy.decision` ra
stdout, `permission.denied` vào vết chạy, không có thread nào — không chạy phần
được phép, không đổi sang backend khác. n8n luôn gửi `engineering` nên đường n8n
không đổi; chốt này đóng đường gọi thẳng API bằng `LANGGRAPH_TOKEN`.
`tests/test_graph_roles.py` quét `graph.py` và đỏ nếu một nút gọi vai trò chưa
khai trong `GRAPH_ROLES`.

Hôm nay `analyst` chạy Gemini, còn đồ thị kỹ thuật chạy Claude và Codex, nên
trạng thái thật của từng hồ sơ là:

| Hồ sơ | dataClass | Đường n8n (một lượt `analyst`) | `/runs/wait` (đồ thị kỹ thuật) | `dept-request.flow.ts` |
|---|---|---|---|---|
| engineering | internal | không dùng — đi `/runs/wait` hoặc tuyến SRE | chạy (Claude + Codex) | — |
| marketing | internal | chạy trên Gemini | được phép; n8n không gửi | Claude soạn, Gemini thẩm định |
| support | confidential | **403** — Gemini không được phép | **403** — reviewer, security chạy Codex | dừng ở bước phân loại (local-llm chưa có) |
| finance, legal | restricted | **403** — chỉ local-llm được phép | **403** — Claude và Codex đều không được phép | dừng ở bước phân loại (local-llm chưa có) |

**Đánh đổi: local-llm chưa dựng.** Backend `local-llm` trong
`execution-plane/config/acpx.global.json` trỏ tới `/fleet/bin/local-acp-bridge.mjs`,
file chưa có trong repo. Vì vậy `restricted` chưa có đường chạy hợp lệ nào, và
`support` không chạy được: với `confidential`, cặp duy nhất vừa đúng chính sách
vừa khác nhà cung cấp khi thẩm định chéo là Claude + local-llm. Fleet chọn TỪ
CHỐI có lý do rõ ràng thay vì âm thầm chạy trên backend không được phép. Hạ
`dataClass` để "cho chạy được" là quyết định của người sở hữu dữ liệu, không
phải của fleet. Để mở lại các hồ sơ này cần: (1) dựng bridge; (2) một vai trò
chỉ đọc chạy trên `local-llm` cho đường n8n — khai đủ năm nơi như mọi vai trò
mới (xem `CLAUDE.md`) — và cho `server.py` chọn vai trò theo `dataClass`. Đồ thị
kỹ thuật không phải đường thay thế: nó chạy Claude và Codex cho mọi hồ sơ, nên
chỉ hồ sơ `public`/`internal` qua được chốt của `/runs/wait`.

**Chưa được cưỡng chế lúc chạy:**

- Chốt của `/runs/wait` nằm ở `server.py`, không ở trong đồ thị. Chạy `graph.py`
  bằng đường khác — `langgraph dev`/Studio (`langgraph.json`),
  `python -m fleet.graph`, hay gọi `graph.ainvoke` từ trong container — không
  qua chốt. Các đường này cần quyền vào container hoặc một máy đã có khoá model,
  không chỉ `LANGGRAPH_TOKEN`.
- `dept-request.flow.ts` đọc `agents.*` của hồ sơ và chạy thẳng: nó chỉ được bảo
  vệ bởi bước 8a. Hồ sơ bị sửa trên máy chủ mà không qua `validate.sh` thì flow
  chạy theo hồ sơ đó.
- OPA (`fleet.rego`) vẫn chỉ có test, chưa được gọi trong đường chạy.
- Chat trực tiếp với agent OpenClaw không đi qua hồ sơ, nên không có
  `dataClass` nào để kiểm.
- NetworkPolicy của Kubernetes không hiểu tên miền, nên không phân biệt được
  "gọi Gemini" với "gọi Claude"; nó không phải lớp cưỡng chế ràng buộc này.

---

## Vai trò dùng chung và vai trò riêng

Chín vai trò trong `agents.json` là của phòng kỹ thuật. Phòng ban khác dùng lại:

- `analyst` — dùng chung (chỉ đọc); đường n8n cho phòng ban chạy vai trò này
- `docs-writer` — dùng chung cho mọi việc soạn thảo
- `orchestrator` — dùng chung, tiếp nhận và định tuyến

Vai trò dùng chung vẫn chịu `dataClass`: backend của vai trò phải nằm trong
`allowedBackends` của hồ sơ. `analyst` và `docs-writer` chạy Gemini nên chỉ phục
vụ được hồ sơ `public`/`internal`; `orchestrator` chạy Claude nên không phục vụ
được `restricted`.

Chỉ tạo vai trò mới khi **quyền của nó khác** những vai trò đã có. Tạo vai trò
mới chỉ vì "công việc khác nhau" là sai — công việc khác nhau thể hiện ở
`systemPrompt` trong hồ sơ, không phải ở vai trò mới. Backend cũng là một thứ
"quyền" theo nghĩa này: vai trò chỉ đọc chạy trên `local-llm` cho hồ sơ
`restricted` là vai trò mới hợp lệ.

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
