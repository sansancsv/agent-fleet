# Agent Fleet — đội agent lập trình chuẩn doanh nghiệp

Bộ khung triển khai một **đội agent nhiều vai trò** (multi-agent team) trên nền
OpenClaw + acpx + mcporter + ClawHub, có điều phối bằng n8n và LangGraph, đóng
gói cho Docker và Kubernetes.

Thiết kế để **mở rộng ra ngoài phòng kỹ thuật**: thêm một phòng ban là thêm một
file YAML trong `profiles/`, không sửa code, không deploy lại.

---

## Bốn tầng, bốn công cụ

| Tầng | Công cụ | Trả lời câu hỏi |
|---|---|---|
| **Điều khiển** (control plane) | OpenClaw Gateway | Ai được nói chuyện với đội agent, và tin nhắn đi tới vai trò nào? |
| **Thực thi** (execution plane) | acpx | Agent thật chạy ở đâu, với quyền gì, backend model nào? |
| **Năng lực** (capability plane) | mcporter | Agent chạm được vào hệ thống nào, qua tool nào? |
| **Phân phối** (distribution plane) | ClawHub | Quy trình nội bộ được đóng gói và phát hành cho các nhóm ra sao? |

Trên bốn tầng đó là **hai bộ điều phối**: n8n cho quy trình nghiệp vụ liên phòng
ban, LangGraph cho quy trình dài cần lưu trạng thái và chờ người duyệt.

```
     Slack / Telegram / Webhook / Lịch
                  │
        ┌─────────▼──────────┐
        │  OpenClaw Gateway  │  định tuyến theo binding, phiên riêng từng người
        └─────────┬──────────┘
                  │
   ┌──────────────┼───────────────┐
   ▼              ▼               ▼
 n8n          LangGraph      acpx flow          ← tầng XÁC ĐỊNH
 (nghiệp vụ)  (bền vững)     (trong repo)
   └──────────────┼───────────────┘
                  ▼
          ┌───────────────┐
          │     acpx      │  9 vai trò × nhiều backend model
          └───────┬───────┘        ← tầng PHI XÁC ĐỊNH
                  ▼
          ┌───────────────┐
          │   mcporter    │  MỘT cầu nối tới mọi MCP server
          └───────┬───────┘
                  ▼
     GitHub · Linear · Grafana · Notion · Kho dữ liệu · …
```

---

## Chín vai trò

| Vai trò | Quyền | Backend mặc định | Vì sao tách riêng |
|---|---|---|---|
| `orchestrator` | đọc, chạy, gọi agent | Claude Opus | Điều phối thì không nên tự sửa code |
| `architect` | đọc, ghi tài liệu | Claude Opus | Quyết định kiến trúc cần được ghi lại, không chỉ được nói |
| `implementer` | **toàn quyền trong repo** | Claude Sonnet | Vai trò duy nhất được ghi — mọi thay đổi truy được về một chỗ |
| `tester` | ghi + chạy, **không mạng** | Claude Sonnet | Test phụ thuộc mạng là test không đáng tin |
| `reviewer` | **chỉ đọc** | GPT (khác nhà cung cấp) | Không sửa được thứ mình đang chấm |
| `security` | chỉ đọc + chạy, không mạng | Claude Opus | Kết quả quét không được rò ra ngoài |
| `docs-writer` | đọc, ghi | Gemini | Ngữ cảnh dài, chi phí thấp |
| `sre` | đọc, chạy, **không ghi repo** | Claude Sonnet | Chạm được cụm nhưng không lặng lẽ sửa code |
| `analyst` | chỉ đọc | Gemini | Dùng chung cho mọi phòng ban |

**Quy tắc quan trọng nhất trong bảng này:** `reviewer` chạy trên model của một
nhà cung cấp **khác** `implementer`. Cùng một model vừa viết vừa chấm sẽ bỏ sót
cùng một loại lỗi. `scripts/validate.sh` cưỡng chế quy tắc này.

---

## Bắt đầu

```bash
git clone <repo> agent-fleet && cd agent-fleet

./bootstrap.sh          # kiểm tra tiên quyết, cài công cụ, sinh khoá nội bộ
./scripts/preflight.sh  # đối chiếu CLI thật đã cài với những gì repo giả định
$EDITOR .env            # điền ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY

make up                 # khởi động 8 dịch vụ
make health             # kiểm tra sức khoẻ
make agents             # xem đội hình và luật định tuyến
make audit              # rà soát bảo mật + test chính sách
make demo-flow          # chạy thử một vòng đầy đủ
```

Xem `make help` để có danh sách đầy đủ.

---

## Cây thư mục

```
control-plane/          OpenClaw — cổng vào, định tuyến, phiên, kênh chat
  openclaw.json         cấu hình gốc, tách nhỏ bằng $include
  config.d/             agents · bindings · models · channels · security · mcp · cron
  workspaces/           AGENTS.md dùng chung + SOUL.md của từng vai trò

execution-plane/        acpx — nơi agent thật chạy
  config/               cấu hình toàn cục và cấu hình theo repo
  flows/                quy trình xác định viết bằng TypeScript
  scripts/              run-role.sh · fanout-review.sh · session-pool.sh
  runner/               server.mjs — API HTTP của tầng thực thi (POST /run), n8n và LangGraph gọi vào đây

capability-plane/       mcporter — một nguồn sự thật cho mọi MCP server
  mcporter.json         khai báo server + lọc tool
  packs/                gói năng lực theo phòng ban
  generate-clis.sh      sinh CLI để agent không phải nạp hết tool vào ngữ cảnh

distribution-plane/     ClawHub — đóng gói và phát hành quy trình nội bộ
  skills/               5 skill: code-review · adr · release-gate · intake · tooling

orchestration/
  langgraph/            đồ thị bền vững, checkpoint PostgreSQL, chờ người duyệt
  n8n/workflows/        quy trình nghiệp vụ: tiếp nhận · cổng thẩm định PR

profiles/               MỘT FILE = MỘT PHÒNG BAN  ← cơ chế mở rộng
policy/                 tool-policy · model-routing · OPA rego (có test)
deploy/docker/          compose 8 dịch vụ (+1 init) + 2 Dockerfile
deploy/k8s/             namespace · RBAC · NetworkPolicy · ExternalSecrets · 4 Deployment
docs/                   tài liệu tiếng Việt
```

---

## Thêm một phòng ban mới

```bash
cp profiles/marketing.yaml profiles/nhan-su.yaml
$EDITOR profiles/nhan-su.yaml       # sửa: dataClass, requesters, approvers,
                                    # categories, reviewCriteria, output
cp capability-plane/packs/support.json capability-plane/packs/nhan-su.json
$EDITOR capability-plane/packs/nhan-su.json

./scripts/validate.sh               # kiểm tra nhất quán
```

Xong. Không sửa code, không deploy lại. Quy trình chung
`execution-plane/flows/dept-request.flow.ts` đọc hồ sơ này lúc chạy.

Chi tiết: `docs/03-mo-rong-phong-ban.md`.

---

## Tài liệu

| File | Nội dung |
|---|---|
| `docs/00-kien-truc.md` | Vì sao bốn tầng, ranh giới trách nhiệm, luồng dữ liệu |
| `docs/01-cai-dat.md` | Cài đặt từng bước cho Docker và Kubernetes |
| `docs/02-workflow.md` | Quy trình xác định và phi xác định — chọn công cụ nào |
| `docs/03-mo-rong-phong-ban.md` | Mở rộng ra ngoài phòng kỹ thuật |
| `docs/04-bao-mat.md` | Mô hình mối đe doạ, phân quyền, secret, kiểm toán |
| `docs/05-runbook.md` | Vận hành hằng ngày, sự cố thường gặp |
| `docs/06-doi-chieu-harness.md` | Bảng chấm bảy lớp harness — chỗ nào theo kịp xu thế, chỗ nào còn trống |
| `docs/adr/` | Biên bản quyết định kiến trúc (khuôn mẫu ở skill `fleet-adr`) |
| `docs/99-thuat-ngu.md` | Đối chiếu thuật ngữ Anh–Việt |

---

## Yêu cầu

Node 24+ · Python 3.12+ · Docker Engine + Compose v2 · git · jq · yq
(tuỳ chọn: `gh`, `opa`, `kubectl` cho triển khai Kubernetes)

### Dùng WSL trên Windows

Đặt repo trên **filesystem Linux** (`~/agent-fleet`), không phải trên ổ Windows
(`/mnt/c/...`). Hai lý do thực tế, không phải lý thuyết:

1. `chmod` không bám trên `/mnt/c` nếu chưa bật `metadata` — script mất bit thực
   thi, và `.env` không giữ được quyền `600`.
2. I/O qua `/mnt/c` chậm hơn nhiều lần; `docker build` và `npm install` sẽ rất ì.

```bash
cp -r /mnt/c/Users/<bạn>/agent-fleet ~/agent-fleet
cd ~/agent-fleet && find . -name '*.sh' -exec chmod +x {} +
```

Compose trong repo đã gọi script qua `bash <đường-dẫn>` thay vì chạy trực tiếp,
nên vẫn hoạt động cả khi bit `+x` bị mất — nhưng hai vấn đề trên vẫn còn.
