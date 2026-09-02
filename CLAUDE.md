# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repo này là gì

Bộ khung triển khai một **đội agent nhiều vai trò** (9 vai trò) trên nền OpenClaw + acpx + mcporter + ClawHub, điều phối bằng n8n và LangGraph, đóng gói cho Docker Compose và Kubernetes. Gần như toàn bộ repo là **cấu hình** (JSON5/JSON/YAML/Rego) cộng một dịch vụ Python nhỏ (`orchestration/langgraph`). Cấu hình ở đây được coi là mã nguồn: có test, có CI, có kiểm tra nhất quán giữa các tầng.

Quy ước ngôn ngữ (theo `control-plane/workspaces/_shared/AGENTS.md`): tài liệu, chú thích, thông báo lỗi bằng **tiếng Việt**; code, tên biến, tên nhánh, commit message bằng **tiếng Anh**.

## Lệnh thường dùng

Mọi lệnh chạy từ gốc repo. `make` (không tham số) liệt kê đầy đủ.

```bash
./bootstrap.sh              # cài acpx/mcporter/clawhub/openclaw, sinh .env, chmod, rồi chạy validate
./scripts/preflight.sh      # đối chiếu cờ/lệnh con của CLI thật đã cài với những gì repo giả định

make validate               # scripts/validate.sh — cú pháp + NHẤT QUÁN giữa các tầng (chạy trước mọi commit)
make oc-validate            # kiểm cấu hình OpenClaw bằng CHÍNH binary trong image (ưu tiên hơn CLI host)
make up / down / nuke       # up = validate + oc-validate + compose up + health; nuke XOÁ volume
make health                 # chờ và retry tới 180s/dịch vụ; in log dịch vụ hỏng
make logs S=<service>       # openclaw-gateway | mcporter | agent-runner | langgraph | n8n | n8n-worker
make restart-gateway        # sau khi sửa control-plane/ (chạy oc-validate trước)

make test                   # pytest cho orchestration/langgraph
make audit                  # openclaw security audit (trong container) + opa test policy/opa/ -v
opa test policy/opa/ -v     # chỉ test chính sách OPA

make capability             # sinh lại CLI từ MCP server sau khi sửa capability-plane/mcporter.json
make tools S=<server>       # xem TÊN TOOL CHÍNH XÁC của một MCP server (cần trước khi điền allowedTools)
make agents                 # openclaw agents list --tree / --bindings
make import-workflows / export-workflows   # n8n <-> orchestration/n8n/workflows/
make demo-flow / demo-review
```

Python (thư mục `orchestration/langgraph`, cần Python 3.12+):

```bash
cd orchestration/langgraph
pip install -e ".[dev]"
python -m pytest tests/ -q
python -m pytest tests/test_policies.py::TestFindingParsing::test_blocker_khong_co_vi_tri_thi_bi_loai -q   # một test
ruff check src tests        # CI chạy ruff; line-length 100
```

CI (`.github/workflows/fleet-ci.yml`) chạy đúng các bước: `scripts/validate.sh`, `opa test`, `ruff` + `pytest`, build image agent-runner + trivy, gitleaks.

## Kiến trúc: bốn tầng, hai bộ điều phối

| Tầng | Thư mục | Công cụ | Trả lời câu hỏi |
|---|---|---|---|
| Điều khiển | `control-plane/` | OpenClaw Gateway | Ai được nói chuyện với fleet, tin nhắn đi tới vai trò nào |
| Thực thi | `execution-plane/` | acpx | Agent chạy ở đâu, quyền gì, backend model nào |
| Năng lực | `capability-plane/` | mcporter | Agent chạm được hệ thống ngoài nào, qua tool nào |
| Phân phối | `distribution-plane/` | ClawHub | Skill/quy trình nội bộ đóng gói và phát hành ra sao |

Trên đó: **n8n** (`orchestration/n8n/`) cho quy trình nghiệp vụ liên phòng ban; **LangGraph** (`orchestration/langgraph/`) cho quy trình dài, checkpoint PostgreSQL, `interrupt()` chờ người duyệt; **acpx flow** (`execution-plane/flows/*.flow.ts`) cho quy trình sống trong repo. Ba cái xếp chồng, không thay thế nhau: n8n tiếp nhận → LangGraph chạy quy trình dài → acpx thực thi từng lượt agent.

Luồng một yêu cầu: Slack → gateway tra `bindings.json` → agent `orchestrator` → LangGraph `graph.py` (`prepare` tạo worktree → `triage` → [`design` nếu risky] → `implement` → `cross_review` song song → `gate` → `approval` interrupt → `open_pr`) → mỗi lượt agent đi qua `acpx_client.run_role` → **dịch vụ agent-runner** (`execution-plane/runner/server.mjs`, `POST /run`, Bearer `AGENT_RUNNER_TOKEN`) spawn `run-role.sh` → `acpx <backend> exec` → mọi truy cập ra ngoài đi qua **một** cầu nối mcporter (`http://mcporter:7420/mcp`).

Tầng thực thi là dịch vụ HTTP, không phải container để `docker exec`. n8n gọi `POST /run`, `POST /pr/checkout`, `POST /pr/cleanup` bằng node httpRequest; `validate.sh` cấm node executeCommand trong `orchestration/n8n/workflows/`. Không đặt `AGENT_RUNNER_URL` thì `run_role` spawn acpx tại chỗ (dev/test). Prompt luôn đi qua argv của spawn hoặc JSON body, không bao giờ qua chuỗi shell.

### Nguyên tắc thiết kế cần giữ khi sửa

- **Xác định bọc ngoài, phi xác định bên trong.** Model *nêu phát hiện*; code *quyết định*. `gate()` trong `graph.py`, `parse_findings`/`risk_from_text` trong `policies.py` là hàm thuần tuý, có test. Không rẽ nhánh bằng cách đoán nội dung phản hồi; ép đầu ra model về tập nhãn hữu hạn, và khi không nhận dạng được thì nghiêng về mức chặt hơn (`risky`).
- **BLOCKER/CRITICAL không có `file:dòng` thì không phải phát hiện** (bị `parse_findings` loại). Mọi agent phải kết thúc bằng khối ```` ```fleet-status ```` (xem `_shared/AGENTS.md`); `run-role.sh` và `acpx_client._extract_status` phân tích khối này.
- **Reviewer phải khác NHÀ CUNG CẤP với implementer** (Claude viết, Codex/Gemini chấm). `validate.sh` bước 8 cưỡng chế cho mọi profile.
- **Mọi vòng lặp có giới hạn** (`max_revisions`, `limits.maxStepRuns`); hết lượt thì leo thang cho người, không thử tiếp.
- **Dữ liệu ngoài bọc trong `<untrusted source="...">`** khi đưa vào prompt.
- **Một quyền bị chặn ở ít nhất hai tầng**: OpenClaw `tools.deny`, cờ acpx (`--deny-all`/`--approve-reads`/`--approve-all`), mcporter `allowedTools`, OPA rego, K8s RBAC.

### Vai trò được khai báo ở NHIỀU nơi, phải sửa đồng bộ

Khi thêm/bớt vai trò hoặc đổi backend, cập nhật tất cả:

1. `control-plane/config.d/agents.json` — `agents.entries.<id>` (+ workspace `control-plane/workspaces/<id>/SOUL.md`)
2. `policy/tool-policy.yaml` — `roles.<id>` (`validate.sh` bước 6 kiểm tra khớp tập vai trò với agents.json)
3. `policy/opa/fleet.rego` — `role_capabilities` (+ `fleet_test.rego`)
4. `execution-plane/scripts/run-role.sh` — bảng `case "$ROLE"`
5. `orchestration/langgraph/src/fleet/acpx_client.py` — `ROLE_BACKENDS`

Chỉ mục 1↔2 được script kiểm tự động; 3–5 phải tự soát.

### Cơ chế mở rộng phòng ban

Thêm phòng ban = thêm `profiles/<tên>.yaml` (schema ở `profiles/_schema.yaml`) + `capability-plane/packs/<capabilityPack>.json`. Không sửa code: `dept-request.flow.ts` và `server.py` (`GET /profiles/<tên>/authorize`) đọc profile lúc chạy. `validate.sh` kiểm profile trỏ tới pack có thật và drafter ≠ reviewer (trừ `dataClass: restricted`). `dataClass` quyết định backend được phép (`policies.MODEL_POLICY`, `model-routing.yaml`, `fleet.rego` — ba nơi phải khớp).

### API LangGraph mà n8n gọi

`server.py` là FastAPI tự viết (không dùng `langgraph up` — CLI không có trong gói `langgraph` và `langgraph up` dựng Compose). Endpoint n8n phụ thuộc: `POST /runs/wait`, `POST /runs/{thread_id}/resume`, `GET /runs/{thread_id}`, `GET /profiles/{name}/authorize`, `GET /ok`. Đổi tên/hình dạng các endpoint này phải sửa cả `orchestration/n8n/workflows/*.json` và `tests/test_server.py`.

Hai chốt fail-closed trong `server.py`: mọi endpoint trừ `/ok` đòi `Authorization: Bearer $LANGGRAPH_TOKEN` (thiếu biến → 503 cho tất cả); `/runs/{id}/resume` chỉ chấp nhận `by` nằm trong `approvers` của hồ sơ gắn với thread (`profile` trong state, mặc định `engineering`), nếu không → 403 và ghi `permission.decision` ra stdout.

## Bẫy cấu hình đã trả giá (đối chiếu OpenClaw 2026.8.1, mcporter 0.13.8)

Phần lớn được `scripts/validate.sh` và `scripts/check-oc-placeholders.py` bắt; đọc trước khi sửa để không phải đi vòng.

**OpenClaw (`control-plane/`)** — định dạng JSON5, schema NGHIÊM NGẶT (khoá lạ = gateway từ chối khởi động):
- `${BIẾN}` chỉ được thay thế ở trường credential (token, apiKey, secret…) và trong khối `mcp`. Mọi chỗ khác đọc **nguyên văn**. Cú pháp `${BIẾN:-mặc-định}` không được hỗ trợ ở đâu cả.
- Không dùng SecretRef object `{source, provider, id}` — qua được `config validate` rồi chết lúc khởi động nếu provider chưa đăng ký. Dùng chuỗi `"${TÊN_BIẾN}"`.
- Không khai `env.vars` (ghi đè khoá API do Docker tiêm vào).
- `gateway.bind` là enum (`lan` cho Docker), không phải IP; không đọc từ biến môi trường.
- `agents.ownership: "explicit"` bắt buộc; không dùng `default: true` (đã khai tử); agent mặc định = luật bắt-tất-cả cuối trong `bindings.json`. Trong cùng tầng, luật đứng trước thắng — xếp từ hẹp tới rộng.
- Tra schema thật: `openclaw config schema | jq '.properties.<khối>.properties | keys'`. **Không chạy `openclaw doctor --fix`** trên cấu hình trong git.
- Image ghim `OPENCLAW_TAG` trong `.env`; CLI trên host khác bản sẽ cho kết quả validate không đại diện — vì vậy luôn dùng `make oc-validate`.

**mcporter (`capability-plane/mcporter.json`)**:
- Mọi `${VAR}` trong `mcpServers` phải có dạng `${VAR:-mặc-định}`; một biến thiếu làm hỏng toàn bộ việc nạp cấu hình.
- `allowedTools`/`blockedTools` là tên tool CHÍNH XÁC (lấy bằng `make tools S=<server>`), không phải glob; không khai cả hai trên cùng server.
- `lifecycle` phải có `mode`; `mcporter serve` chỉ phơi server `keep-alive`.
- Không đặt khoá chú thích `"//..."` bên trong `mcpServers` (cấp gốc thì được).
- `mcporter serve` không có auth; cách ly ở tầng mạng (không map port ra host, NetworkPolicy ở K8s).

**Docker (`deploy/docker/`)**: named volume gắn vào thư mục con của image ngoài phải có init container chown trước (`check-volume-perms.py`); image tự build thì tạo sẵn thư mục trong Dockerfile. State của OpenClaw nằm ở `/home/node/.openclaw/state`, không phải `~/.config/openclaw`.

## Lưu ý môi trường

- Trên WSL, đặt repo trên filesystem Linux (`~/agent-fleet`), không phải `/mnt/c`: mất bit `+x`, `.env` không giữ được 600, I/O chậm. Compose gọi script qua `bash <path>` để chịu được mất `+x`.
- Các file `*:Zone.Identifier` là rác do Windows sinh khi tải file; không tạo thêm, không tham chiếu.
- `.env` không commit; `bootstrap.sh` sinh khoá nội bộ (gồm `LANGGRAPH_TOKEN`, `AGENT_RUNNER_TOKEN`, cả hai bắt buộc), người dùng tự điền `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GEMINI_API_KEY`.
