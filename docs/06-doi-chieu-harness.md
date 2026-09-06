# Đối chiếu với xu thế agentic pattern

Bảng chấm hệ thống này theo bảy lớp harness trong `tien-hoa-agentic-patterns-vi.md`
(Sơ đồ 5, mục 3.1–3.8), cộng thế hệ thứ tư ở mục 4.

Mục đích của tài liệu: trả lời được câu hỏi "chỗ nào của fleet đã theo kịp cách
làm đã được kiểm chứng, chỗ nào còn trống" mà không phải đọc lại toàn bộ repo.

- Ngày chấm: 2026-09-06
- Bản tài liệu tham chiếu: `tien-hoa-agentic-patterns-vi.md` (bản mở rộng, có §3.8, §4, §5)

---

## 1. Kết luận

Hệ thống **không đi sai hướng**. Đây là một bản triển khai harness engineering
đúng nghĩa: bốn tầng tách bạch, quy trình xác định bọc ngoài lượt agent phi xác
định, phân quyền cưỡng chế ở nhiều tầng, trạng thái bền vững ngoài tiến trình.

Hai lớp **đi trước** tài liệu tham chiếu:

- **Tools (§3.6)** — tài liệu khuyến nghị `default-deny`; repo này cưỡng chế
  "một quyền bị chặn ở ít nhất hai tầng" và có `scripts/validate.sh` kiểm tính
  nhất quán giữa các tầng.
- **Agent loop (§3.7)** — tài liệu khuyến nghị "kiểm chứng tách rời thực thi";
  repo này biến nó thành phép kiểm CI (`validate.sh` bước 8 bắt drafter và
  reviewer khác **nhà cung cấp**, cho mọi hồ sơ phòng ban).

Chỗ lệch không nằm ở hướng đi mà nằm ở ba lớp bị bỏ trống, đã xử lý trong đợt
này (xem §4).

---

## 2. Bảng chấm

| Lớp | Điểm | Bằng chứng trong repo | Khoảng lệch |
|---|---|---|---|
| **3.1 Serving** | 9/10 | OpenClaw Gateway; `control-plane/config.d/bindings.json` định tuyến kênh → vai trò; allowlist danh tính; phiên dùng chung giữa các kênh | Gateway là một bản sao có trạng thái (SQLite trên PVC) — điểm hỏng đơn. Tài liệu mô tả cùng thiết kế nên không tính là lệch xu thế |
| **3.2 Orchestration** | 9/10 | Ba tầng xếp chồng n8n → LangGraph → acpx (`docs/02-workflow.md` §3). `fanout()` chạy reviewer + security song song. Đúng pattern **Multi-agent Coordination**: ngữ cảnh được **chia** theo vai trò, không nhân bản | Không có subagent spawning. Đây là lựa chọn có chủ đích cho mô hình chín vai trò cố định, không phải thiếu sót |
| **3.3 Sandbox** | 6/10 → **7/10** | Worktree riêng cho mỗi task (`graph.prepare`); Pod Security `restricted`; `automountServiceAccountToken: false`; NetworkPolicy chỉ cho mcporter ra Internet | Khoá model nằm cùng container nơi code do agent sinh ra được chạy. Đã thu hẹp bán kính (xem `docs/adr/0001`), chưa tách hẳn. PVC `repos` mount RW cho mọi vai trò |
| **3.4 Context engineering** | 7/10 | **Progressive disclosure ✅** — `distribution-plane/skills/*/SKILL.md` + `fleet-* --help`. **Tool offloading ✅✅** — `capability-plane/generate-clis.sh` sinh CLI thay vì nạp tool schema, mạnh hơn pattern ba-tool trong tài liệu | **Compaction ❌** — chưa có cơ chế nào. Hiện chưa đau vì mỗi nút là một lượt ngắn; sẽ đau khi kéo dài phiên hoặc bật `session` có trạng thái |
| **3.5 Memory** | 4/10 → **7/10** | Trước đợt này: chỉ có checkpoint PostgreSQL (state của quy trình) và phiên gateway. Sau đợt này: `orchestration/langgraph/src/fleet/memory.py` — `MEMORY.md` làm mục lục, `repos/<slug>.md` tích luỹ bài học, `tasks/<id>.md` ghi tiến độ | Vẫn chưa có cơ chế loại bỏ bài học đã lỗi thời ngoài việc cắt theo số lượng. Ngưỡng "Markdown không còn đủ" chưa quan sát được |
| **3.6 Tools** | 10/10 | `default-deny`; MCP thay vì bash trần; quy tắc chặn ở ≥2 tầng (`policy/tool-policy.yaml`); `globalDeny`; OPA rego có test; `validate.sh` bước 6 kiểm khớp vai trò | — |
| **3.7 Agent loop** | 10/10 | Orchestrator-Worker với bộ kiểm chứng tách rời thực thi. `gate()` là hàm thuần tuý có test. Mọi vòng lặp có trần (`max_revisions`, `limits.maxStepRuns`) | — |
| **3.8 Durability & Observability** | 6/10 → **8/10** | **Durability ✅✅** — checkpoint từng bước + `interrupt()` + trần vòng lặp = 2/3 cơ chế chuẩn (thiếu hibernate/wake, chưa cần). **Observability** — trước đợt này chỉ có audit "ai làm gì"; nay có `trajectory.py` ghi vết chạy và `metrics.py` tính bốn chỉ số | Chưa có số đo token thật (acpx chưa trả về) → chi phí/tác vụ hiện đo bằng đại lượng thay thế, có ghi rõ |

### Thế hệ thứ tư (§4 — Loop / Graph engineering)

Về mặt **đồ thị** thì fleet đã ở đó: nút agent, nút tất định, bộ định tuyến,
điểm chờ người duyệt, quản trị quyền trên toàn đội. Về mặt **vòng lặp** thì công
thức *"một vòng lặp = một tác vụ + một phép kiểm"* mới đúng một nửa: có phép
kiểm cho **code** (`gate()` + thẩm định chéo), chưa có phép kiểm cho **chính
harness**. `make metrics` là bước đầu tiên để có nó — không đo thì không biết
sửa prompt hay `SOUL.md` làm hệ thống tốt lên hay tệ đi.

### Phép thử Hashimoto

Nguyên tắc "mỗi ràng buộc tương ứng một hành vi xấu có thật" được repo áp dụng
rất tốt — nhưng cho **người và Claude Code sửa repo**, không phải cho **agent
trong fleet**:

- Đã làm tốt: mục "Bẫy cấu hình đã trả giá" trong `CLAUDE.md`; chú thích chown
  worktree trong `graph.py` (ghi lại đúng tám đường dẫn đã hỏng thật).
- Còn trống: `control-plane/workspaces/_shared/AGENTS.md` vẫn là hiến chương
  soạn sẵn từ đầu. Vòng "agent làm sai → mã hoá thành ràng buộc" chưa khép.

Trường `lesson:` trong khối `fleet-status` (thêm ở đợt này) là chỗ để khép vòng
đó: agent *nêu* bài học, code *quyết định* có ghi lại hay không, và bài học được
nạp lại ở lượt sau.

---

## 3. Những gì cố ý KHÔNG làm theo tài liệu

Ghi lại để lần sau không phải tranh luận lại.

| Điều tài liệu nêu | Vì sao repo không làm |
|---|---|
| Subagent spawning (§3.2) | Fleet có chín vai trò tĩnh với quyền khác nhau; nhân bản ngữ cảnh sang agent con sẽ mang theo cả quyền, phá vỡ mô hình phân quyền. Chia ngữ cảnh theo vai trò an toàn hơn |
| Vector database cho memory (§3.5) | Tài liệu nói rõ Markdown phẳng là đủ và không có dữ liệu nào ở đây cho thấy đã tới ngưỡng. Ngưỡng để mở lại: xem `docs/adr` khi có |
| Harness tự tiến hoá — AHE (§5.3) | Còn là hướng nghiên cứu, có phản biện về nguy cơ khớp quá mức vào benchmark. Điều kiện xem lại: có kết quả tái lập độc lập |
| MCP phi trạng thái theo spec 2026-07-28 (§5.1) | Chờ mcporter hỗ trợ. Khi có: cầu nối chạy được sau load balancer thường, nhưng `mcporter serve` vẫn không có auth nên cách ly ở tầng mạng vẫn bắt buộc |

---

## 4. Việc đã làm sau lần chấm này

| Khoảng lệch | Đã xử lý bằng |
|---|---|
| §3.5 Memory — thiếu tầng filesystem | `src/fleet/memory.py`, trường `lesson:` trong `fleet-status`, volume `fleet-memory` |
| §3.8 Observability — không có vết chạy, không có chỉ số | `src/fleet/trajectory.py`, `src/fleet/metrics.py`, `GET /metrics`, `make metrics` |
| §3.3 Sandbox — khoá model cùng chỗ chạy code | `docs/adr/0001-tach-khoa-model-khoi-container-chay-code.md` + thu hẹp khoá theo backend trong `run-role.sh` và `acpx_client.py`, có phép kiểm ở `validate.sh` bước 5d |

## 5. Khi nào chấm lại

Chấm lại khi xảy ra **một** trong các điều sau, không theo lịch:

- Thêm một lớp mới vào harness (ví dụ: compaction, hibernate/wake).
- `make metrics` cho thấy một chỉ số xấu đi hai kỳ liên tiếp.
- Tài liệu tham chiếu có bản cập nhật đổi **cách thiết kế**, không phải chỉ thêm
  tin sản phẩm.
