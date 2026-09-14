# Sổ tay vận hành (runbook)

## Nhịp vận hành

| Tần suất | Việc | Lệnh |
|---|---|---|
| Hằng ngày | Xem sức khoẻ dịch vụ | `make health` |
| Hằng ngày | Xem chi phí theo phòng ban | dashboard chi phí |
| Hằng tuần | Rà nhật ký kiểm toán tìm hành vi bất thường | truy vấn Loki |
| Hằng tuần | Xem tỉ lệ leo thang (agent bó tay) | `make metrics D=7` |
| Hằng tuần | Xem bài học fleet đã tích luỹ, xoá bài sai | `make memory` |
| Hằng tháng | Rà quyền: vai trò nào có quyền không dùng đến | `make audit` |
| Hằng tháng | Cập nhật ảnh, quét lỗ hổng | CI |
| Hằng quý | Diễn tập xoay vòng khoá | thủ công |

---

## Bốn chỉ số cần theo dõi

**1. Tỉ lệ leo thang** — bao nhiêu % công việc kết thúc bằng `outcome: blocked`.
Tăng đột ngột = model xuống cấp, hoặc quy trình gặp loại việc mới chưa xử lý được.

**2. Số vòng sửa lại trung bình.** Gần 0 = thẩm định quá dễ dãi. Gần giới hạn
(2) = model viết code chưa đủ tốt cho loại việc này.

**3. Tỉ lệ đồng thuận khi thẩm định chéo.** Mục 3/3 gần như chắc chắn là lỗi
thật. Nếu hầu hết mục chỉ 1/3, tiêu chí thẩm định đang quá mơ hồ.

**4. Chi phí trên mỗi công việc hoàn thành.** Chỉ số duy nhất nói được fleet có
đáng tiền không. Tính theo *công việc hoàn thành*, không theo *lượt gọi*.

### Lấy số ở đâu

`make metrics` (hoặc `GET /metrics` kèm token) đọc vết chạy trong
`FLEET_TRAJECTORY_DIR` và in bảng bốn chỉ số. Hai điều cần biết trước khi đọc bảng:

- **Chi phí token trả về `null`, không phải 0.** acpx chưa phơi số token nên
  chưa đo được; bảng báo các đại lượng thay thế (số lượt agent, thời gian, ký
  tự đầu ra) và nói rõ vì sao thiếu.
- **Chưa có dữ liệu khác 0%.** Mọi tỉ lệ trả `null` khi mẫu số bằng 0. Nếu thấy
  "chưa có dữ liệu" ngay sau khi fleet đã chạy, kiểm `FLEET_TRAJECTORY_DIR` có
  được mount không.

Mục "Phát hiện lặp lại nhiều nhất" ở cuối báo cáo là danh sách việc cần làm:
mỗi dòng là một ràng buộc còn thiếu trong `_shared/AGENTS.md`. Thêm ràng buộc
rồi tuần sau xem dòng đó có biến mất không.

---

## Bộ nhớ của fleet

Bộ nhớ nằm ở `FLEET_MEMORY_DIR` (volume `fleet-memory`), do **container
langgraph ghi**, agent-runner không mount. Markdown thuần, sửa tay được:

```bash
make memory                                    # mục lục
$(COMPOSE) exec -T langgraph cat /srv/fleet-memory/repos/<repo>.md
```

**Khi nào phải can thiệp tay:** một bài học sai được ghi vào sẽ được nạp vào
MỌI lượt agent của repo đó cho tới khi bị đẩy ra khỏi trần 50 bài. Thấy bài học
sai thì xoá dòng đó ngay, đừng chờ nó tự trôi.

Mọi thứ ở đây đều có trần (`MAX_LESSONS`, `MAX_PROGRESS_LINES`,
`MAX_INJECT_CHARS`). Nếu volume này đầy thì nghĩa là có trần bị gỡ ở đâu đó,
không phải cần thêm đĩa.

---

## Sự cố thường gặp

### `make health` báo "Connection reset by peer" ngay sau `make up`

Gần như luôn là **kiểm tra quá sớm**, không phải dịch vụ hỏng. `docker compose
up -d` trả về khi container đã *khởi động*, không phải khi dịch vụ đã *sẵn
sàng*: n8n mất 20–40 giây chạy migration lần đầu, LangGraph phải kết nối
PostgreSQL và tạo bảng checkpoint.

`make health` nay chờ và thử lại tới 180 giây mỗi dịch vụ, và in luôn bảng
trạng thái container. Nếu vẫn đỏ sau ngần ấy thời gian thì mới là hỏng thật —
xem `make logs S=<dịch-vụ>`.

### Gateway không khởi động
```bash
make logs S=openclaw-gateway
```
| Triệu chứng | Nguyên nhân thường gặp | Xử lý |
|---|---|---|
| `config validation failed` | JSON5 sai cú pháp | `python3 scripts/json5_to_json.py <file>` để biết dòng nào |
| `bind: address in use` | cổng 18789 đã bị chiếm | đổi `OPENCLAW_GATEWAY_PORT` |
| `auth token missing` | thiếu biến trong `.env` | `openssl rand -hex 32` rồi điền |

### `mcporter` không khởi động

Bốn nguyên nhân, xếp theo tần suất gặp. Cả bốn đều bị `./scripts/validate.sh`
bắt trước khi container chạy — nếu bạn gặp ở runtime nghĩa là đã bỏ qua bước đó.

**1. `Unknown daemon subcommand`** — lệnh phơi cầu nối là `mcporter serve --http <port>`.
`mcporter daemon` chỉ có `start` / `stop` / `restart` / `status`, và nó **không nhận
`--config`** (luôn đọc `~/.mcporter/mcporter.json`).

**2. `expected object, received string` tại `mcpServers.//--- ... ---`**
Mỗi khoá trong `mcpServers` phải trỏ tới một object. Khoá chú thích kiểu
`"//--- nhóm ---": ""` chỉ dùng được ở **cấp gốc**, không dùng được bên trong
`mcpServers`.

**3. `Invalid input` tại `<server>.lifecycle`**
`lifecycle` là `"keep-alive"` | `"ephemeral"` | `{ mode, idleTimeoutMs }`.
Viết `{ idleTimeoutMs: 600000 }` mà thiếu `mode` sẽ hỏng.

**4. `unresolved env placeholder`**
Một `${VAR}` chưa đặt làm **hỏng toàn bộ** việc nạp cấu hình, không chỉ server
thiếu biến đó — nghĩa là thiếu một token Grafana cũng đủ để cả cầu nối không lên.
Luôn viết `${VAR:-giá-trị-mặc-định}`. Khi làm đúng, server thiếu credential chỉ
hiện là `offline` hoặc `auth required`, phần còn lại vẫn chạy.

### Ba hành vi của mcporter dễ mất thời gian nếu không biết trước

**`serve` chỉ phơi server `keep-alive`.** Đặt `lifecycle: ephemeral` nghĩa là
server đó vô hình với cầu nối, dù `mcporter list` vẫn thấy. Kiểm tra bằng
`make mcp-status` và `mcporter daemon status`.

**`allowedTools` / `blockedTools` là tên tool CHÍNH XÁC, không phải glob.**
`"*_delete_*"` không khớp gì cả — nó im lặng vô hiệu, và bạn tưởng đã chặn.
Quy trình đúng là hai bước: khai báo server → `make tools S=<server>` để xem tên
thật → chép vào `allowedTools`. Không được khai báo cả hai danh sách trên cùng
một server.

**`mcporter call` dùng `key=value`, không có `--arg`.**
```bash
mcporter call github.search_code q="rate limit" --output json
mcporter call notion.notion-create-pages parentPageId=abc content=@/tmp/body.md
```
`key=@path` đọc giá trị từ tệp — dùng cho nội dung dài để khỏi thoát chuỗi trong shell.

### Gateway báo `SecretProviderResolutionError`

```
Startup failed: required secrets are unavailable.
SecretProviderResolutionError: Secret provider "local-llm" is not configured
```

Nguyên nhân: dùng **SecretRef object** `{ source, provider, id }`. Dạng này hợp
lệ theo schema, nhưng `provider` phải là một secret provider đã đăng ký — và khối
`secrets` trong cấu hình chỉ nói về egress proxy, không phải nơi đăng ký provider.

Điều làm nó khó chịu: cấu hình **qua được cả `config validate` lẫn `security
audit`**, rồi gateway chết lúc khởi động. Không phép kiểm tĩnh nào bắt được.

Quy ước của repo này: **luôn dùng chuỗi `"${TÊN_BIẾN}"` cho credential**, không
dùng SecretRef object. `./scripts/validate.sh` cưỡng chế điều đó.

Bài học rộng hơn: **một tính năng tuỳ chọn chưa dựng không được phép chặn cả
gateway.** Model tự host vì vậy mặc định tắt (xem `config.d/models.json`), giống
như Slack. Bật lại chỉ khi thật sự có vLLM/TGI, rồi `make oc-validate` và
`make up` để xác nhận.

### Gateway lặp lại `EPERM: chmod '/home/node/.openclaw/state'`

Đây là cái bẫy kinh điển của **named volume gắn vào thư mục con**.

Khi Docker gắn một named volume vào đường dẫn **chưa tồn tại trong image**, nó
tạo thư mục đó với chủ sở hữu `root:root`. Gateway chạy bằng user `node`
(uid 1000) nên không `chmod` được, và chết ngay — lặp lại mãi.

Hai cách xử lý, tuỳ image là của ai:

| Image | Cách làm |
|---|---|
| **Của ta** (`build:`) | Tạo sẵn thư mục trong Dockerfile rồi `chown node:node`. Volume sẽ kế thừa đúng chủ sở hữu. |
| **Của người khác** (`image:`) | Một init container chạy bằng `root`, `chown` rồi thoát; service chính `depends_on` nó với `condition: service_completed_successfully`. |

Repo dùng cả hai: `Dockerfile.agent-runner` tạo sẵn các thư mục volume, còn
`openclaw-init` dọn quyền cho `openclaw-state` và `openclaw-audit`.

`./scripts/validate.sh` nay bắt lớp lỗi này: mọi named volume gắn vào thư mục con
của image bên ngoài mà thiếu init container đều bị báo trước khi chạy.

Một chi tiết dễ bỏ qua: **đừng dùng chung một volume cho hai image khác nhau**.
Chủ sở hữu của volume phụ thuộc container nào khởi tạo nó trước — một nguồn lỗi
ngẫu nhiên rất khó lần. Vì vậy audit của gateway có volume riêng
(`openclaw-audit`) thay vì dùng chung `fleet-logs`.

### Gateway "Up vài giây" lặp lại — plugin chưa được chấp thuận quyền

```
OpenClaw plugin verification failed; refusing to report the gateway ready.
- Plugin "slack" requires capability consent.
```

Bật một kênh chat sẽ nạp plugin tương ứng, và plugin đòi **chấp thuận quyền một
lần**. Chưa chấp thuận thì gateway từ chối báo sẵn sàng — cả fleet đứng im chỉ vì
một kênh bạn còn chưa có token. Vì vậy repo này để `channels.slack.enabled: false`
mặc định.

Bật Slack theo ba bước:

```bash
# 1. điền SLACK_BOT_TOKEN_* và SLACK_APP_TOKEN_* vào .env
make enable-slack          # 2. chấp thuận quyền (lưu vào state, một lần)
# 3. đổi channels.slack.enabled thành true
make restart-gateway
```

Xem plugin nào đang lỗi: `make plugins`.

**Chấp thuận quyền lưu ở `~/.openclaw/state/openclaw.sqlite`** — cùng chỗ với
lịch sử phiên và ghép đôi kênh. Compose gắn volume `openclaw-state` đúng vào thư
mục đó; nếu gắn sai chỗ thì mỗi lần tạo lại container là phải chấp thuận lại và
ghép đôi kênh lại từ đầu.

Một mẹo đọc trạng thái: container hiện `Up 7 seconds` mỗi lần bạn nhìn không phải
đang khởi động — nó **đang khởi động lại liên tục**. `make health` nay tự in 25
dòng log cuối của dịch vụ hỏng để khỏi phải đoán.

### `openclaw config validate` báo `Invalid input` cụt lủn

Khi thông báo chỉ nói `logging: Invalid input` mà không nói khoá nào sai, gần
như luôn là **lệch phiên bản**: CLI trên host là một bản, image container là bản
khác, và schema cấu hình đã đổi giữa hai bản đó.

```bash
openclaw --version                                    # bản trên host
docker compose -f deploy/docker/docker-compose.yml \
  run --rm openclaw-gateway openclaw --version        # bản trong image
```

Vì sao dễ xảy ra: `bootstrap.sh` cố ý **không** nâng cấp công cụ đã có sẵn trên
máy bạn, trong khi image thì được kéo về theo tag.

Hai biện pháp đã đưa vào repo:

- `OPENCLAW_TAG` được **ghim** trong `.env` (không dùng `latest`). Cấu hình
  trong `control-plane/` được kiểm chứng với đúng bản đó. Nâng bản có chủ đích:
  đổi tag → `make oc-validate` → `make up`.
- `make oc-validate` **ưu tiên container** (đang chạy, hoặc một container tạm từ
  image), chỉ dùng CLI host khi không có Docker — và khi đó có cảnh báo. Nó cũng
  báo khi phiên bản host lệch với runtime.

Đồng bộ CLI host cho khỏi nhầm lẫn về sau:

```bash
npm install -g openclaw@$(grep OPENCLAW_TAG .env | cut -d= -f2) --allow-scripts=openclaw
```

### Gateway báo `Unrecognized keys` / `Invalid config`

Schema của OpenClaw **nghiêm ngặt**: một khoá lạ là gateway từ chối khởi động.
Đừng đoán tên khoá — hỏi chính binary:

```bash
make oc-validate                       # kiểm chứng bằng binary OpenClaw
openclaw config schema | jq '.properties.agents.properties.defaults.properties | keys'
```

**Đừng chạy `openclaw doctor --fix` trên cấu hình nằm trong git.** Nó sửa tại chỗ
và âm thầm bỏ những khoá bạn cố ý đặt; lần deploy sau bạn sẽ không biết vì sao
hành vi đổi. Sửa tay theo thông báo lỗi.

Khác biệt thường gặp giữa kỳ vọng và schema thật (OpenClaw 2026.8.1):

| Tôi tưởng | Thực tế |
|---|---|
| `agents.defaults.tools` | không tồn tại — chính sách tool ở khối `tools` cấp gốc, ghi đè ở `agents.entries.*.tools` |
| `sandbox.network`, `sandbox.limits` | không tồn tại — sandbox chỉ có backend/browser/docker/mode/prune/scope/ssh/workspaceAccess/workspaceRoot |
| `identity.displayName` | là `identity.name` |
| `tools.agentToAgent.allowFrom/allowTo` | là `{ enabled, allow }` |
| `cron.jobs` | **không tồn tại** — lịch là dữ liệu do gateway quản lý, không phải cấu hình. Việc định kỳ của fleet nằm ở `n8n/workflows/03-lich-dinh-ky.json` |
| `hooks.entries` | là `hooks.mappings` (mảng) |
| `channels.defaults.dmPolicy` | thuộc từng kênh/account, không phải defaults |
| `logging.audit.{format,path,include,redact}` | audit chỉ có `{enabled, executionIdentity, messages}`; che dữ liệu dùng `logging.redactPatterns` |
| model tự host khai trong `agents.defaults.models` | endpoint/khoá thuộc khối `models.providers` cấp gốc |
| `agents.entries.<id>.default: true` | đã khai tử — cần `agents.ownership: "explicit"` |
| root `limits`, `content`, `mcp.maxToolsInContext` | không tồn tại |

### Gateway báo `Invalid --bind`

Hai nguyên nhân, và nguyên nhân thứ hai là bẫy thật sự.

**a. Sai giá trị.** `gateway.bind` nhận **một trong năm nhãn**, không phải địa
chỉ IP: `loopback` | `lan` | `tailnet` | `auto` | `custom`. Trong Docker phải là
`lan` (`loopback` chỉ nghe 127.0.0.1 *bên trong* container nên n8n và LangGraph
không gọi tới được). Muốn một IP cụ thể: `bind: "custom"` +
`gateway.customBindHost`.

**b. Dùng `${BIẾN}` sai chỗ.** Đây mới là bẫy: **OpenClaw KHÔNG thay thế
biến môi trường trong `openclaw.json`.** Giá trị được đọc nguyên văn, nên
`bind: "${OPENCLAW_GATEWAY_BIND:-loopback}"` bị hiểu là chuỗi `${OPENCLAW_...}`
và báo đúng lỗi trên — không hề nhắc gì tới biến môi trường, nên rất dễ đi tìm
sai chỗ.

Ba quy tắc rút ra:

| Nơi | `${BIẾN}` | Ghi chú |
|---|---|---|
| Trường credential (`token`, `botToken`, `apiKey`…) | **có** | nhiều trường trong số này là "runtime-mutable" nên KHÔNG nhận SecretRef object — chỉ nhận chuỗi |
| Khối `mcp` | **có** | |
| Mọi nơi khác | **không** | viết thẳng giá trị |
| Cú pháp `${BIẾN:-mặc-định}` | **không, ở bất kỳ đâu** | |

Dạng SecretRef `{ source: "env", provider: "<tên>", id: "TÊN_BIẾN" }` cũng hợp lệ
nhưng cần đủ **ba** khoá, và `provider` phải là một provider đã khai trong khối
`secrets` — nếu không, `openclaw security audit` báo *Secret provider is not
configured*. Với fleet này, mẫu chuỗi `"${BIẾN}"` đơn giản hơn và đủ dùng.

**Cạm bẫy nguy hiểm nhất của quy tắc này:** khai báo
`env: { vars: { ANTHROPIC_API_KEY: "${ANTHROPIC_API_KEY}" } }` sẽ đặt khoá API
thành đúng chuỗi 22 ký tự đó, **ghi đè khoá thật** Docker đã tiêm vào — rồi mọi
lệnh gọi model hỏng với lỗi xác thực chẳng liên quan gì. Vì vậy repo này không
khai báo `env.vars`; khoá đến từ `environment:` của compose (hoặc Secret ở K8s).

`./scripts/validate.sh` kiểm cả ba: giá trị `bind`, `${BIẾN}` đặt sai chỗ, và sự
tồn tại của `env.vars`.

### LangGraph báo `executable file not found in $PATH`

Gói `langgraph` (thư viện) **không kèm** lệnh `langgraph` — CLI nằm ở gói riêng
`langgraph-cli`. Và kể cả cài đúng, `langgraph up` dựng Docker Compose nên chạy
nó bên trong một container là sai tầng.

Fleet này không dùng LangGraph Server. Nó phục vụ đồ thị bằng một FastAPI mỏng
(`src/fleet/server.py`) chạy qua `uvicorn`, phơi đúng những endpoint mà n8n gọi:

| Endpoint | Dùng để |
|---|---|
| `GET /ok` | healthcheck |
| `GET /profiles/<tên>/authorize?requester=` | n8n kiểm quyền **trước khi** tiêu token |
| `POST /runs/wait` | chạy tới khi xong hoặc tới điểm chờ người duyệt |
| `POST /runs/<thread_id>/resume` | người duyệt trả lời → chạy tiếp đúng chỗ đã dừng |
| `GET /runs/<thread_id>` | đọc trạng thái hiện tại |

Nếu thiếu `FLEET_CHECKPOINT_DSN`, server vẫn chạy nhưng dùng bộ nhớ trong và in
cảnh báo — quy trình sẽ mất khi container khởi động lại.

### Agent trả lời "không có tool đó"
```bash
make mcp-status               # server nào kết nối được, server nào offline
make tools S=github           # tên tool CHÍNH XÁC mà server đó phơi ra
make capability               # sinh lại CLI sau khi sửa cấu hình
```
Nguyên nhân hay gặp nhất: tool bị lọc bởi `allowedTools`, hoặc bị chặn bởi
`blockedTools` ở tầng gateway (`config.d/mcp.json`).

### Lượt agent bị treo
```bash
docker compose exec agent-runner acpx claude sessions list
docker compose exec agent-runner acpx claude sessions rm <tên-phiên>
```
Timeout mặc định 30 phút. Treo thường xuyên = bước quá lớn, cần tách nhỏ.

### n8n hoặc LangGraph báo `agent-runner trả 401` / `không gọi được agent-runner`

Tầng thực thi là một dịch vụ HTTP (`execution-plane/runner/server.mjs`, cổng
8787 trong mạng compose, không map ra host). Ba nguyên nhân theo thứ tự:

| Triệu chứng | Nguyên nhân | Xử lý |
|---|---|---|
| container `agent-runner` thoát mã 78 | thiếu `AGENT_RUNNER_TOKEN` trong `.env` — runner từ chối khởi động (fail closed) | `openssl rand -hex 32` rồi điền, `make up` |
| `401` | token phía gọi (n8n/LangGraph) khác token của runner | cả ba dịch vụ đọc cùng một biến `AGENT_RUNNER_TOKEN`; kiểm `.env` |
| `429 runner đang bận` | quá `RUNNER_MAX_CONCURRENT` lượt song song | tăng `AGENT_RUNNER_REPLICAS` hoặc biến đó |
| `400 cwd phải là thư mục có thật nằm trong /srv/repos` | gọi với thư mục ngoài kho repo | runner cố ý chỉ chạy trong `/srv/repos` |

Kiểm nhanh: `docker compose exec agent-runner curl -s localhost:8787/healthz`.

### `git push`/`git clone` từ agent-runner hoặc langgraph báo `Bad credentials` hoặc `Invalid username or token`

Xác thực GitHub qua PAT/HTTPS trong container có thể báo "Bad credentials" dù
token đúng, còn hạn, đủ quyền. **Đừng debug PAT lâu quá 10 phút** — chuyển
thẳng sang SSH deploy key, ổn định hơn trong thực tế:

```bash
ssh-keygen -t ed25519 -f deploy/docker/secrets/deploy_key_<repo> -N '' \
  -C 'agent-fleet-<repo>-deploy-key'
# thêm public key làm Deploy Key trên GitHub (repo → Settings → Deploy keys),
# PHẢI tick "Allow write access" nếu fleet cần mở PR — mặc định GitHub tạo
# key read-only, quên tick là open_pr sẽ chết ở bước `git push` với
# "The key you are authenticating with has been marked as read only."
make setup-github-ssh
```

`make setup-github-ssh` cài key + `known_hosts` + `git config
url."git@github.com:".insteadOf "https://github.com/"` vào **cả**
`agent-runner` và `langgraph` (agent nào cũng có thể phải `git push`/`clone`).
Nó ghi vào writable layer của container, không phải volume — **phải chạy lại
mỗi lần các container đó bị `recreate`** (kể cả chỉ rebuild lại image
`langgraph` để deploy một bản vá code), nếu không lần `git push` kế tiếp lại
"Bad credentials" y hệt và dễ tưởng nhầm là PAT hỏng lại.

### LangGraph Studio (`langgraph dev`) không thấy thread nào

Đừng dùng LangGraph Studio để duyệt task của fleet. `langgraph dev` chạy trên
`langgraph_runtime_inmem` — một tầng sổ sách Threads/Runs/State hoàn toàn
tách biệt, không đọc/ghi bảng `checkpoints` thật trong `FLEET_CHECKPOINT_DSN`,
bất kể `langgraph.json` trỏ `graphs.fleet` vào biến thể nào. Đổi `thread_id`
sang UUID không giải quyết được gì — đó không phải nguyên nhân.

**Dùng Studio để làm gì thì được:** thuần công cụ phát triển cục bộ, ngắt hẳn
khỏi state thật — xem cấu trúc đồ thị, hoặc dựng thủ công một trạng thái tổng
hợp bên trong Studio để kiểm logic thuần tuý như `gate()`/`policies.py` — vẫn
không thay thế được `make test`. Mọi node chạm git/GitHub/LLM thật (`prepare`,
`implement`, `open_pr`) vẫn gây side-effect thật nếu bấm chạy trong Studio.

**Kênh duyệt thật, không đổi:** form n8n
(`orchestration/n8n/workflows/04-duyet-task.json`) hoặc gọi thẳng
`/runs/<id>/resume`.

### Webhook GitHub gọi vào n8n luôn thất bại xác thực, dù đã đúng URL

GitHub repo Webhook (Settings → Webhooks) **không gửi được header tuỳ ý** —
nó chỉ ký HMAC-SHA256 payload bằng "Secret" rồi gửi qua header cố định
`X-Hub-Signature-256`. Nếu node webhook trong n8n dùng credential kiểu
**Header Auth** (khớp đúng tên+giá trị một header tự đặt, ví dụ workflow
`02-pr-review-gate.json`), một GitHub Webhook gốc **không bao giờ** qua được
bước xác thực đó — không phải lỗi cấu hình URL/secret, mà là hai cơ chế xác
thực không tương thích. Cách dùng được: thêm một GitHub Actions workflow
(`.github/workflows/...yml`) trong **repo mục tiêu** (không phải agent-fleet)
để forward sự kiện `pull_request` sang n8n kèm đúng header, đọc payload qua
`$GITHUB_EVENT_PATH` chứ không nội suy `${{ toJSON(github.event) }}` thẳng vào
lệnh shell (rủi ro injection nếu tiêu đề/mô tả PR chứa ký tự đặc biệt).

Nếu dùng Cloudflare Quick Tunnel (`cloudflared tunnel --url ...`, không tài
khoản, không named tunnel) để expose n8n cho bước trên: nó **có thể chết bất
cứ lúc nào** — log báo `Unauthorized: Tunnel not found` từ phía server dù
tiến trình `cloudflared` vẫn chạy. Đây không phải sự cố mạng cục bộ, không
sửa được bằng cách chờ; phải `pkill cloudflared` rồi khởi động lại để nhận
URL `*.trycloudflare.com` **mới**, và phải cập nhật lại secret
`FLEET_WEBHOOK_URL` phía GitHub Actions. Không phải giải pháp production —
dùng Named Tunnel (mục dưới) thay thế.

### Cloudflare Named Tunnel — ingress công khai ổn định (thay Quick Tunnel)

Service `cloudflared` trong `deploy/docker/docker-compose.yml` đứng sau
Compose profile `"tunnel"` nên `make up` mặc định KHÔNG khởi động nó — chỉ
chạy khi bật rõ ràng.

**Thiết lập một lần:**

1. Tạo tunnel trên Cloudflare Zero Trust dashboard: Networks → Tunnels →
   Create a tunnel → chọn "Cloudflared" → đặt tên → bước "Install connector"
   chọn hệ điều hành "Docker" — dashboard đưa ra một lệnh dạng
   `docker run cloudflare/cloudflared:latest tunnel run --token eyJ...`.
   Chỉ cần lấy phần TOKEN (chuỗi sau `--token`), không cần chạy lệnh đó —
   compose của repo đã có sẵn service tương đương.
2. Thêm vào `.env` (không commit):
   ```
   CLOUDFLARE_TUNNEL_TOKEN=<token vừa lấy>
   ```
3. Ở cùng bước tạo tunnel, tab **Public Hostname**: khai domain công khai trỏ
   vào dịch vụ nào trong compose. Đây là cấu hình phía Cloudflare, KHÔNG có
   file ingress cục bộ nào trong repo phải sửa — vì token chạy ở chế độ
   "remotely-managed". Ví dụ:
   | Public hostname | Service |
   |---|---|
   | `n8n.miền-của-bạn.com` | `http://n8n:5678` |
   | `fleet-hooks.miền-của-bạn.com` | `http://openclaw-gateway:18789` |

   `cloudflared` nằm chung mạng Docker mặc định của project `agent-fleet` nên
   phân giải được tên dịch vụ compose (`n8n`, `openclaw-gateway`, ...) mà
   không cần map cổng ra host — cổng `127.0.0.1:*` hiện có trong compose vẫn
   chỉ để debug từ máy host, không liên quan tới đường đi của tunnel.

   **Đừng** trỏ hostname công khai thẳng vào n8n nếu nó lộ luôn giao diện quản
   trị (`/`, `/rest/*`) — hoặc chỉ public đúng path webhook, hoặc đặt
   Cloudflare Access trước hostname đó. `openclaw-gateway` tự đòi
   `hooks.token` (xem `control-plane/config.d/channels.json`) nên path
   `/hooks/*` đã có một lớp xác thực riêng, nhưng thu hẹp thêm ở tầng
   Cloudflare Access vẫn nên làm — đúng nguyên tắc "một quyền bị chặn ở ít
   nhất hai tầng" của repo này.

**Vận hành hằng ngày:**

```bash
make tunnel-up     # bật (đọc CLOUDFLARE_TUNNEL_TOKEN từ .env)
make tunnel-logs   # xem đã kết nối chưa — tìm dòng "Registered tunnel connection"
make tunnel-down   # tắt
```

Image `cloudflared` là distroless (không có `sh`/`curl`/`wget` bên trong) nên
service này KHÔNG có `healthcheck` trong compose — `make health` không kiểm
tra nó. Xác nhận tunnel sống bằng `make tunnel-logs` hoặc bằng cách gọi thẳng
domain công khai.

Nếu `make tunnel-up` báo thiếu biến bắt buộc: `CLOUDFLARE_TUNNEL_TOKEN` chưa
có trong `.env`, làm lại bước 2. Nếu log lặp lại lỗi xác thực (`Unauthorized`),
token đã bị revoke trên dashboard (tunnel bị xoá, hoặc token được cấp lại) —
lấy token mới, không sửa được bằng cách khởi động lại container.

### LangGraph trả `403` khi duyệt (`/runs/<id>/resume`)

Trường `by` không nằm trong `approvers` của hồ sơ gắn với thread (`profiles/<tên>.yaml`).
Đây là chủ đích: token API chứng minh "n8n gọi", không chứng minh "người có
thẩm quyền đã duyệt". Sửa danh sách `approvers` trong hồ sơ, không nới API.
Mọi lần duyệt/từ chối (kể cả bị 403) đều ghi một dòng `permission.decision`
ra log của container `langgraph`, và lượt bị 403 còn ghi thêm một dòng bền
`permission.denied` vào vết chạy (`FLEET_TRAJECTORY_DIR`) — xem
`docs/04-bao-mat.md` §5. `503` ở mọi endpoint nghĩa là thiếu
`LANGGRAPH_TOKEN` — API đóng hoàn toàn cho tới khi có token.

Một `409 Thread '<id>' không ở điểm chờ duyệt` **không phải lỗi cấu hình** — nó
nghĩa là thread đó đã được duyệt/từ chối rồi (hoặc chưa từng tới điểm
`interrupt()`). Gọi `/resume` hai lần cho cùng một thread luôn là lỗi gọi, không
phải lỗi hệ thống. Nếu quy trình bị kẹt SAU khi đã duyệt (ví dụ `open_pr` lỗi
giữa chừng vì mất quyền `git push`), `/resume` không dùng lại được nữa —
phải chạy tiếp trực tiếp từ checkpoint bằng `graph.ainvoke(None, cfg)` (không
truyền `Command`), gọi từ trong container `langgraph`; không có endpoint HTTP
nào cho việc này hôm nay.

### LangGraph mất trạng thái sau khi khởi động lại
Kiểm tra `FLEET_CHECKPOINT_DSN` đã trỏ đúng PostgreSQL chưa. Nếu để trống,
LangGraph chạy checkpoint trong bộ nhớ và **mọi lần chờ người duyệt sẽ mất** khi
pod restart. Đây là lỗi cấu hình hay gặp nhất khi lên production.

### n8n mất toàn bộ credential
`N8N_ENCRYPTION_KEY` đã bị đổi. Không khôi phục được. Khôi phục từ backup của
`n8ndata` volume, hoặc nhập lại credential thủ công. **Không bao giờ đổi khoá này.**

### Chi phí tăng vọt
Chưa có bảng chi phí theo model (nằm trong lộ trình). Hai nguồn đếm được ngay:
```bash
# Số lượt agent theo vai trò trong 24h qua — từ log của agent-runner
docker compose -f deploy/docker/docker-compose.yml logs --since 24h --no-log-prefix agent-runner \
  | grep '"route":"POST /run"' | jq -r '.role' | sort | uniq -c | sort -rn

# Sự kiện của gateway (tool call, run) — volume openclaw-audit
docker compose -f deploy/docker/docker-compose.yml exec openclaw-gateway ls -la /home/node/.openclaw/audit
```
Ba nguyên nhân thường gặp, theo thứ tự: vòng lặp sửa lại không giới hạn; dùng
model suy luận sâu cho việc phân loại; ngữ cảnh phình vì phiên không xoay vòng.

---

## Vận hành theo mùa vụ

### Thêm một vai trò agent
1. Thêm mục vào `control-plane/config.d/agents.json`
2. Thêm vai trò tương ứng vào `policy/tool-policy.yaml` **và** `policy/opa/fleet.rego` (+ `fleet_test.rego`)
3. Thêm ánh xạ trong `execution-plane/scripts/run-role.sh` và `acpx_client.py::ROLE_BACKENDS`
   (API agent-runner không có bảng riêng — nó giao cho `run-role.sh`)
4. Tạo `workspaces/<vai-trò>/SOUL.md`
5. `./scripts/validate.sh` — script chỉ so `agents.json` với `tool-policy.yaml`;
   rego, `run-role.sh` và `ROLE_BACKENDS` phải tự soát bằng mắt

### Đổi model của một vai trò
Sửa `agents.entries.<vai-trò>.model` trong `agents.json`, rồi `make restart-gateway`.
**Kiểm tra lại quy tắc đa dạng hoá:** nếu đổi model của `implementer` sang cùng
nhà cung cấp với `reviewer`, `validate.sh` sẽ báo lỗi.

### Cập nhật phiên bản công cụ
```bash
npm view acpx version && npm view mcporter version && npm view openclaw version
```
Cập nhật ARG trong `Dockerfile.agent-runner` và tag ảnh trong compose/K8s.
Chạy `make validate && make audit` trên staging trước.

### Xoay vòng khoá
```bash
# 1. Sinh khoá mới trong Vault
# 2. ExternalSecret tự đồng bộ sau <= 1 giờ (refreshInterval)
# 3. Khởi động lại để tiến trình nhận biến mới
kubectl -n fleet rollout restart deploy/agent-runner deploy/mcporter deploy/openclaw-gateway
# 4. Thu hồi khoá cũ ở phía nhà cung cấp
```

---

## Sao lưu

| Dữ liệu | Nơi | Tần suất | Vì sao |
|---|---|---|---|
| PostgreSQL (`fleet_checkpoints`) | PVC | hằng ngày | mất = mất mọi quy trình đang chờ duyệt |
| PostgreSQL (`n8n`) | PVC | hằng ngày | mất = mất workflow và credential |
| `openclaw-state` | PVC | hằng ngày | mất = mất lịch sử phiên và ghép đôi kênh |
| `N8N_ENCRYPTION_KEY` | Vault | — | mất = credential n8n thành vô dụng |
| Workflow n8n | **git** | mỗi lần sửa | `make export-workflows` sau khi sửa trên UI |

Workflow n8n chỉ nằm trong database là một điểm hỏng đơn lẻ. Xuất ra git sau mỗi
lần sửa — đó là lý do `make export-workflows` tồn tại.

---

## Cầu dao khẩn cấp

```bash
# Dừng mọi hoạt động agent, giữ nguyên dữ liệu để điều tra
docker compose stop agent-runner langgraph n8n-worker

# Kubernetes
kubectl -n fleet scale deploy/agent-runner deploy/langgraph --replicas=0
```

Gateway vẫn chạy để người dùng nhận được thông báo, nhưng không lượt agent nào
mới được khởi tạo.
