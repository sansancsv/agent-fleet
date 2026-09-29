# CLAUDE.md

Hướng dẫn cho Claude Code khi làm việc trong repo này.

## Repo này là gì

Bộ khung triển khai một **đội agent nhiều vai trò** (9 vai trò) trên nền OpenClaw + acpx + mcporter + ClawHub, điều phối bằng n8n và LangGraph, đóng gói cho Docker Compose và Kubernetes. Gần như toàn bộ repo là **cấu hình** (JSON5/JSON/YAML/Rego) cộng một dịch vụ Python nhỏ (`orchestration/langgraph`). Cấu hình ở đây được coi là mã nguồn: có test, có CI, có kiểm tra nhất quán giữa các tầng.

Quy ước ngôn ngữ (theo `control-plane/workspaces/_shared/AGENTS.md`): tài liệu, chú thích, thông báo lỗi bằng **tiếng Việt**; code, tên biến, tên nhánh, commit message bằng **tiếng Anh**.

## Lệnh thường dùng

Mọi lệnh chạy từ gốc repo. `make` (không tham số) liệt kê đầy đủ.

```bash
./bootstrap.sh              # cài acpx/mcporter/clawhub/openclaw, sinh .env, chmod, rồi chạy validate
./scripts/preflight.sh      # đối chiếu cờ/lệnh con của CLI thật đã cài với những gì repo giả định

make validate               # scripts/validate.sh — cú pháp + nhất quán giữa các tầng (chạy trước mọi commit)
make oc-validate             # kiểm cấu hình OpenClaw bằng chính binary trong image
make up / down / nuke        # up = validate + oc-validate + compose up + health; nuke xoá volume
make health                  # chờ và retry tới 180s/dịch vụ; in log dịch vụ hỏng
make logs S=<service>         # openclaw-gateway | mcporter | agent-runner | langgraph | n8n | n8n-worker
make restart-gateway          # sau khi sửa control-plane/ (chạy oc-validate trước)

make test                    # pytest cho orchestration/langgraph
make metrics D=7              # bốn chỉ số vận hành từ vết chạy
make memory                   # mục lục bộ nhớ mà agent đọc ở mỗi lượt
make audit                    # openclaw security audit (trong container) + opa test policy/opa/ -v
opa test policy/opa/ -v       # chỉ test chính sách OPA

make capability                # sinh lại CLI từ MCP server sau khi sửa capability-plane/mcporter.json
make tools S=<server>          # xem tên tool chính xác của một MCP server (cần trước khi điền allowedTools)
make agents                    # openclaw agents list --tree / --bindings
make import-workflows / export-workflows   # n8n <-> orchestration/n8n/workflows/
make demo-flow / demo-review
```

Python (thư mục `orchestration/langgraph`, cần Python 3.12+):

```bash
cd orchestration/langgraph
pip install -e ".[dev]"
python -m pytest tests/ -q
ruff check src tests        # line-length 100
```

Không có venv trên host (ví dụ máy có `uv`):

```bash
cd orchestration/langgraph && PYTHONPATH=src uv run --no-project --python 3.12 \
  --with "pytest>=8" --with "pytest-asyncio>=0.24" --with "langgraph>=1.0" \
  --with "langgraph-checkpoint-postgres>=2.0" --with "psycopg[binary,pool]>=3.2" \
  --with "fastapi>=0.115" --with httpx --with "pyyaml>=6.0" python -m pytest tests/ -q -p no:cacheprovider
```

Runner API (Node thuần, không có package.json): `node --check execution-plane/runner/server.mjs`. `validate.sh` bước 5b làm việc này khi có `node`; bước 5c từ chối mọi workflow n8n chứa `n8n-nodes-base.executeCommand`.

Từ Windows, chạy script kiểm chứng trong WSL: `wsl -d Ubuntu -- bash -lc 'cd ~/agent-fleet && ./scripts/validate.sh'` (shell không tương tác của WSL không có `node`/`pytest` trên PATH; validate.sh tự bỏ qua các bước đó và báo rõ).

CI (`.github/workflows/fleet-ci.yml`): `scripts/validate.sh`, `opa test`, `ruff` + `pytest`, build image agent-runner + trivy, gitleaks.

## Kiến trúc: bốn tầng, hai bộ điều phối

| Tầng | Thư mục | Công cụ | Trả lời câu hỏi |
|---|---|---|---|
| Điều khiển | `control-plane/` | OpenClaw Gateway | Ai được nói chuyện với fleet, tin nhắn đi tới vai trò nào |
| Thực thi | `execution-plane/` | acpx | Agent chạy ở đâu, quyền gì, backend model nào |
| Năng lực | `capability-plane/` | mcporter | Agent chạm được hệ thống ngoài nào, qua tool nào |
| Phân phối | `distribution-plane/` | ClawHub | Skill/quy trình nội bộ đóng gói và phát hành ra sao |

Trên đó: **n8n** (`orchestration/n8n/`) cho quy trình nghiệp vụ liên phòng ban; **LangGraph** (`orchestration/langgraph/`) cho quy trình dài, checkpoint PostgreSQL, `interrupt()` chờ người duyệt; **acpx flow** (`execution-plane/flows/*.flow.ts`) cho quy trình sống trong repo. Ba cái xếp chồng, không thay thế nhau: n8n tiếp nhận → LangGraph chạy quy trình dài → acpx thực thi từng lượt agent.

Luồng một yêu cầu: Slack → gateway tra `bindings.json` → agent `orchestrator` → LangGraph `graph.py` (`prepare` tạo worktree → `triage` → [`design` nếu risky] → `implement` → `cross_review` song song → `gate` → `approval` interrupt → `open_pr`) → mỗi lượt agent đi qua `acpx_client.run_role` → dịch vụ agent-runner (`execution-plane/runner/server.mjs`, `POST /run`, Bearer `AGENT_RUNNER_TOKEN`) spawn `run-role.sh` → `acpx <backend> exec` → mọi truy cập ra ngoài đi qua **một** cầu nối mcporter (`http://mcporter:7420/mcp`).

Tầng thực thi là dịch vụ HTTP, không phải container để `docker exec`. n8n gọi `POST /run`, `POST /pr/checkout`, `POST /pr/cleanup` bằng node httpRequest; `validate.sh` cấm node executeCommand trong `orchestration/n8n/workflows/`. Không đặt `AGENT_RUNNER_URL` thì `run_role` spawn acpx tại chỗ (dev/test). Prompt luôn đi qua argv của spawn hoặc JSON body, không bao giờ qua chuỗi shell.

### Nguyên tắc thiết kế cần giữ khi sửa

- **Xác định bọc ngoài, phi xác định bên trong.** Model *nêu phát hiện*; code *quyết định*. `gate()` trong `graph.py`, `parse_findings`/`risk_from_text` trong `policies.py` là hàm thuần tuý, có test. Không rẽ nhánh bằng cách đoán nội dung phản hồi; ép đầu ra model về tập nhãn hữu hạn, và khi không nhận dạng được thì nghiêng về mức chặt hơn (`risky`).
- **BLOCKER/CRITICAL không có `file:dòng` thì không phải phát hiện** (bị `parse_findings` loại). Mọi agent phải kết thúc bằng khối ```` ```fleet-status ```` (xem `_shared/AGENTS.md`); `run-role.sh` và `acpx_client._extract_status` phân tích khối này.
- **Reviewer phải khác nhà cung cấp với implementer** (Claude viết, Codex/Gemini chấm) — tránh mô hình tự chấm điểm chính mình. `validate.sh` bước 8 cưỡng chế cho mọi profile.
- **Mọi vòng lặp có giới hạn** (`max_revisions`, `limits.maxStepRuns`); hết lượt thì leo thang cho người, không thử tiếp.
- **Bộ nhớ và vết chạy fail-soft.** `fleet/memory.py` và `fleet/trajectory.py` nuốt mọi lỗi I/O có chủ đích: volume hỏng thì mất bộ nhớ/số liệu, không được làm hỏng một lượt giao hàng tính năng. Đừng thêm `raise` vào hai module này.
- **Mọi thứ trong bộ nhớ đều có trần** (`MAX_LESSONS`, `MAX_PROGRESS_LINES`, `MAX_INJECT_CHARS`) để không lặng lẽ ăn hết cửa sổ ngữ cảnh của mọi lượt gọi.
- **Agent chỉ *nêu* bài học, code *quyết định* ghi.** Trường `lesson:` trong khối `fleet-status`; `graph._after_turn` gọi `memory.record_lesson`. Không cho agent tự ghi file bộ nhớ, để tránh nó thành nơi agent tự cấp chỉ dẫn cho chính mình ở lượt sau.
- **Khoá model được thu hẹp theo backend** ở `run-role.sh` và `acpx_client.provider_env()`; hai nơi phải khớp, `validate.sh` bước 5d kiểm — mỗi backend chỉ thấy đúng khoá API của mình, giảm bán kính rò rỉ khoá.
- **Dữ liệu ngoài bọc trong `<untrusted source="...">`** khi đưa vào prompt.
- **Một quyền bị chặn ở ít nhất hai tầng**: OpenClaw `tools.deny`, cờ acpx (`--deny-all`/`--approve-reads`/`--approve-all`), mcporter `allowedTools`, OPA rego, K8s RBAC.

### Vai trò được khai báo ở nhiều nơi, phải sửa đồng bộ

Khi thêm/bớt vai trò hoặc đổi backend, cập nhật tất cả:

1. `control-plane/config.d/agents.json` — `agents.entries.<id>` (+ workspace `control-plane/workspaces/<id>/SOUL.md`)
2. `policy/tool-policy.yaml` — `roles.<id>` (`validate.sh` bước 6 kiểm tra khớp tập vai trò với agents.json)
3. `policy/opa/fleet.rego` — `role_capabilities` (+ `fleet_test.rego`)
4. `execution-plane/scripts/run-role.sh` — bảng `case "$ROLE"`
5. `orchestration/langgraph/src/fleet/acpx_client.py` — `ROLE_BACKENDS`

Chỉ mục 1↔2 được script kiểm tự động; 3–5 phải tự soát.

### Cơ chế mở rộng phòng ban

Thêm phòng ban = thêm `profiles/<tên>.yaml` (schema ở `profiles/_schema.yaml`) + `capability-plane/packs/<capabilityPack>.json`. Không sửa code: `dept-request.flow.ts` và `server.py` (`GET /profiles/<tên>/authorize`) đọc profile lúc chạy. `validate.sh` kiểm profile trỏ tới pack có thật và drafter ≠ reviewer (trừ `dataClass: restricted`). `dataClass` quyết định backend được phép (`policies.MODEL_POLICY`, `model-routing.yaml`, `fleet.rego` — ba nơi phải khớp).

### Bộ nhớ, vết chạy, chỉ số

Ba module nhỏ trong `orchestration/langgraph/src/fleet/`, tất cả chỉ do container `langgraph` ghi (agent-runner không mount) nên không có tranh chấp quyền volume giữa hai image:

| Module | Ghi ở đâu | Trả lời câu hỏi |
|---|---|---|
| `memory.py` | `FLEET_MEMORY_DIR` (volume `fleet-memory`) | "lần trước đụng repo này đã học được gì" — `MEMORY.md` mục lục, `repos/<slug>.md` bài học, `tasks/<id>.md` tiến độ |
| `trajectory.py` | `FLEET_TRAJECTORY_DIR`, NDJSON một file một ngày | "quy trình hỏng ở nút nào, lỗi nào lặp lại" |
| `metrics.py` | không ghi — đọc vết chạy | bốn chỉ số vận hành; `GET /metrics`, `python -m fleet.metrics` |

Phân biệt phải giữ: **checkpointer là state của một luồng; memory là tri thức giữa các luồng.** Đừng nhét bài học vào `FleetState` và đừng dùng checkpointer làm bộ nhớ.

**Không có UI duyệt người thật cho `POST /runs/<id>/resume`.** `server.py` ghi thẳng vào checkpointer bằng `thread_id` dạng chuỗi tuỳ ý (ví dụ `REQ-XXXX`), không dùng "Threads API" chuẩn của LangGraph Platform. Hệ quả: **LangGraph Studio/`langgraph dev` không dùng để duyệt các task này được** — nó chạy trên `langgraph_runtime_inmem`, một tầng sổ sách Threads/Runs/State tách biệt hoàn toàn, không đọc/ghi bảng `checkpoints` thật trong `FLEET_CHECKPOINT_DSN`. Người duyệt gọi thẳng `POST /runs/<id>/resume` (qua n8n có xác thực người bấm thật, hoặc gọi tay).

`langgraph.json` phải khai `graphs.fleet` bằng đường dẫn MODULE đã cài (`"fleet.graph:graph"`), không phải đường dẫn FILE — đường dẫn file làm `langgraph dev` nạp module không có package context, vỡ `from . import memory, trajectory` trong `graph.py`.

Chi phí token trong `metrics.py` cố ý trả `None` kèm lý do, không quy đổi từ số ký tự. Khi acpx phơi số token thì sửa `trajectory.step()` để ghi thêm.

### API LangGraph mà n8n gọi

`server.py` là FastAPI tự viết (không dùng `langgraph up`). Endpoint n8n phụ thuộc: `POST /runs/wait`, `POST /runs/{thread_id}/resume`, `GET /runs/{thread_id}`, `GET /profiles/{name}/authorize`, `GET /ok`. Đổi tên/hình dạng các endpoint này phải sửa cả `orchestration/n8n/workflows/*.json` và `tests/test_server.py`.

Hai chốt fail-closed trong `server.py`: mọi endpoint trừ `/ok` đòi `Authorization: Bearer $LANGGRAPH_TOKEN` (thiếu biến → 503 cho tất cả); `/runs/{id}/resume` chỉ chấp nhận `by` nằm trong `approvers` của hồ sơ gắn với thread (`profile` trong state, mặc định `engineering`), nếu không → 403 và ghi `permission.decision` ra stdout.

Khi thêm endpoint mới: gắn `dependencies=[Protected]` (trừ healthcheck), và trong `tests/test_server.py` gửi header `AUTH` (fixture `client` đã đặt `LANGGRAPH_TOKEN`). Khi thêm điểm cuối cho runner (`server.mjs`): thêm vào bảng `ROUTES`, kiểm đầu vào bằng regex/đường dẫn tuyệt đối trong `FLEET_REPO_ROOT` như các handler hiện có, không bao giờ dựng chuỗi shell. Runner cố ý không có bảng vai trò riêng (chỉ kiểm regex rồi giao cho `run-role.sh`) để không thành nơi khai vai trò thứ sáu.

## Bẫy cấu hình cần biết (OpenClaw 2026.8.1, mcporter 0.13.8)

Phần lớn được `scripts/validate.sh` và `scripts/check-oc-placeholders.py` bắt.

**OpenClaw (`control-plane/`)** — định dạng JSON5, schema nghiêm ngặt (khoá lạ = gateway từ chối khởi động):
- `${BIẾN}` chỉ được thay thế ở trường credential (token, apiKey, secret…) và trong khối `mcp`. Mọi chỗ khác đọc **nguyên văn**. Cú pháp `${BIẾN:-mặc-định}` không được hỗ trợ ở đâu cả.
- Không dùng SecretRef object `{source, provider, id}` — qua được `config validate` rồi chết lúc khởi động nếu provider chưa đăng ký. Dùng chuỗi `"${TÊN_BIẾN}"`.
- Không khai `env.vars` (ghi đè khoá API do Docker tiêm vào).
- `gateway.bind` là enum (`lan` cho Docker), không phải IP; không đọc từ biến môi trường.
- `agents.ownership: "explicit"` bắt buộc; không dùng `default: true` (đã khai tử); agent mặc định = luật bắt-tất-cả cuối trong `bindings.json`. Trong cùng tầng, luật đứng trước thắng — xếp từ hẹp tới rộng.
- `openclaw plugins install`/`enable` từ chối ghi cấu hình khi `control-plane/openclaw.json` dùng `$include` ở root — giới hạn của CLI, chưa có cách hợp lệ cài plugin (kể cả `@openclaw/slack`) mà vẫn giữ kiến trúc `$include`. Dùng n8n làm kênh vào chính; hoãn Slack cho tới khi cần.
- Tra schema thật: `openclaw config schema | jq '.properties.<khối>.properties | keys'`. **Không chạy `openclaw doctor --fix`** trên cấu hình trong git.
- Image ghim `OPENCLAW_TAG` trong `.env`; CLI trên host khác bản sẽ cho kết quả validate không đại diện — vì vậy luôn dùng `make oc-validate`.

**mcporter (`capability-plane/mcporter.json`)**:
- Mọi `${VAR}` trong `mcpServers` phải có dạng `${VAR:-mặc-định}`; một biến thiếu làm hỏng toàn bộ việc nạp cấu hình.
- `allowedTools`/`blockedTools` là tên tool chính xác (lấy bằng `make tools S=<server>`), không phải glob; không khai cả hai trên cùng server.
- `lifecycle` phải có `mode`; `mcporter serve` chỉ phơi server `keep-alive`.
- Không đặt khoá chú thích `"//..."` bên trong `mcpServers` (cấp gốc thì được).
- `mcporter serve` không có auth; cách ly ở tầng mạng (không map port ra host, NetworkPolicy ở K8s).

**acpx + ACP adapter (`execution-plane/config/acpx.global.json`; acpx 0.19.3, claude-agent-acp 0.84.0, codex-acp 2.0.0)**:
- acpx đẩy mọi `ACPX_AUTH_<X>` thành biến `<X>` cho tiến trình agent (`ACPX_AUTH_OPENAI_API_KEY` → `OPENAI_API_KEY`); khoá model đi đường này. Bước `authenticate` chỉ chạy khi tên biến khớp đúng method id agent quảng bá.
- codex-acp 2.x quảng bá method `api-key`, nhưng fleet không đặt `ACPX_AUTH_API_KEY` (tên chung đó lọt khỏi việc thu hẹp khoá). Env của agent-runner (compose, K8s, `.env.example` của langgraph) đặt `DEFAULT_AUTH_REQUEST={"methodId":"api-key"}` để adapter tự đăng nhập; thiếu nó mọi lượt codex chết ở `session/new` ("Authentication required"). Vì vậy `authPolicy` phải là `skip`. Không đặt biến này bằng `ENV` trong Dockerfile: BuildKit cảnh báo `SecretsUsedInArgOrEnv` với mọi tên chứa AUTH.
- codex-acp 2.x không phân tích cờ: cờ lạ bị bỏ qua lặng lẽ, `codex-acp --help` khởi động server rồi treo — đừng gọi trong preflight/healthcheck.
- Mỗi adapter tự mang runtime (Claude Code native trong SDK; `@openai/codex` trong cây phụ thuộc). Không cài `claude`/`codex` toàn cục vào ảnh.

**Docker (`deploy/docker/`)**: named volume gắn vào thư mục con của image ngoài phải có init container chown trước (`check-volume-perms.py`); image tự build thì tạo sẵn thư mục trong Dockerfile. State của OpenClaw nằm ở `/home/node/.openclaw/state`, không phải `~/.config/openclaw`.

**Kubernetes (`deploy/k8s/`)**:
- **NetworkPolicy là cộng dồn và hai chiều.** A gọi được B chỉ khi A có egress rule tới B *và* B có ingress rule từ A. `default-deny-all` chặn cả hai chiều cho mọi pod, nên mỗi Deployment cần **hai** policy nhắm đích danh. Quên vế ingress khiến cụm im lặng không hoạt động.
- NetworkPolicy **không hiểu tên miền**, chỉ podSelector/namespaceSelector/CIDR. Mọi thứ kiểu "chỉ cho gọi api.anthropic.com" phải làm ở tầng khác.
- Luôn `except: 169.254.169.254/32` trong mọi rule ra Internet — endpoint metadata của cloud.
- `mcporter serve` **không có endpoint HTTP nào**; probe phải dùng `tcpSocket`. `httpGet /healthz` làm Deployment không bao giờ Ready mà log vẫn sạch.
- Ảnh `mcporter` tách riêng khỏi `agent-runner` (`Dockerfile.mcporter`): pod giữ credential MCP không được chứa sẵn acpx/gh/git/run-role.sh — lộ credential MCP không đồng nghĩa lộ quyền chạy code.
- Namespace có hai đường ra Internet (mcporter + gateway cho Slack Socket Mode), cộng một rule 443 tạm thời cho agent-runner cho tới khi có `llm-egress-gateway`.

## Lưu ý môi trường

- Trên WSL, đặt repo trên filesystem Linux (`~/agent-fleet`), không phải `/mnt/c`: mất bit `+x`, `.env` không giữ được 600, I/O chậm. Compose gọi script qua `bash <path>` để chịu được mất `+x`.
- Các file `*:Zone.Identifier` là rác do Windows sinh khi tải file; không tạo thêm, không tham chiếu.
- Git trên Windows đang cảnh báo "LF will be replaced by CRLF": mọi file trong repo phải giữ **LF**. Script `.sh`, `.mjs`, cấu hình được mount thẳng vào container Linux; CRLF làm hỏng shebang và JSON5.
- `.env` không commit; `bootstrap.sh` sinh khoá nội bộ (gồm `LANGGRAPH_TOKEN`, `AGENT_RUNNER_TOKEN`, cả hai bắt buộc), người dùng tự điền `ANTHROPIC_API_KEY`/`OPENAI_API_KEY`/`GEMINI_API_KEY`. Thêm biến bắt buộc mới thì phải sửa đủ ba nơi: `.env.example`, danh sách `for KEY in` của `bootstrap.sh`, và `${VAR:?...}` trong compose.

## Roadmap

- **K8s**: manifest ở `deploy/k8s/` chưa apply lên cụm thật — cần kiểm chứng NetworkPolicy hai chiều (mcporter, langgraph) trước khi coi là production-ready.
- **Duyệt người thật**: chưa có kênh duyệt cho `POST /runs/<id>/resume` ngoài gọi API trực tiếp — cần Slack qua n8n hoặc một trang duyệt tối giản.
- **Slack qua OpenClaw**: `openclaw plugins install` chưa cài được plugin Slack với kiến trúc `$include` hiện tại — hướng khả thi: tự tải gói, trỏ qua `plugins.load.paths`, bỏ qua bước "install" của CLI.
- **Chi phí token**: `metrics.py` chưa đo được token thật — chờ acpx phơi số token rồi bổ sung vào `trajectory.step()`.
- **`llm-egress-gateway`**: thay rule 443 tạm thời cho agent-runner bằng một cổng ra Internet có kiểm soát tên miền.
