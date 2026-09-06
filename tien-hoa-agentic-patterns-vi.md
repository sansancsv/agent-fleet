# Sự tiến hoá của các Agentic Pattern trong AI

> **Bản tiếng Việt** (diễn đạt lại, cô đọng) từ bài *"The Evolution of AI Agentic Patterns"* — tieukhoimai.me, 07/05/2026.
> **Đã mở rộng** với các diễn biến từ tháng 05/2026 đến 09/2026.
> Thẻ: Agentic-AI · Prompt-Engineering · Context-Engineering · Harness-Engineering · Loop-Engineering
> Nguồn gốc: https://tieukhoimai.me/blog/evolution-of-agentic-patterns

| | |
|---|---|
| **Phiên bản tài liệu** | v2.0 |
| **Cập nhật lần cuối** | 05/09/2026 |
| **Phạm vi bao phủ** | 2022 → 09/2026 |
| **Lần rà soát kế tiếp** | *(để trống — điền khi rà soát)* |

---

## Cách đọc tài liệu này

Tài liệu dùng ba loại dấu hiệu:

| Dấu hiệu | Ý nghĩa |
|---|---|
| *(không dấu)* | Nội dung từ bài gốc, đã được xác nhận qua nhiều nguồn |
| 🆕 | Nội dung bổ sung sau ngày bài gốc xuất bản (05/2026 → nay) |
| ⚠️ | Ghi nhận từ **một nguồn duy nhất** hoặc chưa được kiểm chứng độc lập — dùng với sự dè dặt |
| 🔲 | **Chỗ trống có chủ đích** — khung sẵn để điền khi có dữ liệu quan sát mới |

---

## Quy ước dịch thuật

Để tránh mỗi chỗ dịch một kiểu, tài liệu thống nhất như sau. Thuật ngữ tiếng Anh được **giữ nguyên** trong thân bài; tiếng Việt chỉ đóng vai trò giải nghĩa lần đầu.

| Thuật ngữ gốc | Cách gọi tiếng Việt thống nhất | Ghi chú |
|---|---|---|
| prompt engineering | **kỹ thuật soạn chỉ dẫn** | không dịch là "viết lệnh" — dễ nhầm với lập trình |
| context engineering | **kỹ thuật tổ chức ngữ cảnh** | trọng tâm là *chọn và sắp xếp*, không phải "quản lý" chung chung |
| harness engineering | **kỹ thuật dựng bộ khung vận hành** | *harness* = toàn bộ hạ tầng bao quanh model |
| loop engineering 🆕 | **kỹ thuật thiết kế vòng lặp** | ai/cái gì điều khiển bộ khung đó |
| context window | **cửa sổ ngữ cảnh** | |
| to hit a ceiling | **chạm trần** | nghĩa: hết dư địa cải tiến bằng cách cũ |
| dynamic assembly | **bản dựng động** | không dịch "lắp ráp" — nghe cơ khí |
| lossy | **mất thông tin không hồi phục** | |
| grounded / verification | **kiểm chứng** | phân biệt với *validation* = kiểm tra hợp lệ |
| durable execution 🆕 | **thực thi bền** | chạy tiếp được sau khi tiến trình chết |
| observability 🆕 | **khả năng quan sát** | đo được chuyện gì đang xảy ra bên trong hệ thống |

---

## Luận điểm chính

Trong bốn năm, câu hỏi trung tâm của ngành đã đổi **ba lần** — và tính đến giữa 2026, **lần thứ tư đang hình thành**:

| Mốc | Câu hỏi trung tâm | Câu trả lời |
|---|---|---|
| 2022 | "Mình nên **nói gì**?" | Prompt engineering — kỹ thuật soạn chỉ dẫn |
| 2023 | "Model cần **nhìn thấy gì**?" | Context engineering — kỹ thuật tổ chức ngữ cảnh |
| 2025–2026 | "Mình cần **xây hệ thống gì**?" | Harness engineering — kỹ thuật dựng bộ khung vận hành |
| 🆕 giữa 2026 → | "**Ai/cái gì điều khiển** hệ thống đó?" | Loop engineering — kỹ thuật thiết kế vòng lặp |

Mỗi lần chuyển dịch xảy ra vì thế hệ trước **chạm trần** — tức là không thể đi xa hơn chỉ bằng cách làm tinh vi hơn cùng một việc:

- Prompt engineering không giải được **knowledge cutoff** (mốc cắt tri thức của model).
- Context engineering không giải được **reliability** (độ tin cậy).
- Harness engineering là lớp hạ tầng xử lý phần mà cả hai thế hệ trước đều bó tay: làm cho agent chạy **ổn định trong môi trường production** — qua nhiều phiên làm việc, qua các lần thất bại, và với nhiều người dùng khác nhau.
- 🆕 Harness engineering, đến lượt nó, cũng lộ ra trần riêng: **một bộ khung tốt vẫn cần có người bấm nút và kiểm tra kết quả**. Đó là chỗ loop engineering bước vào.

> Bài viết gốc được truyền cảm hứng từ talk *"Build an Agent Harness with Microsoft Agent Framework and GitHub Copilot SDK"* của **Thang Chung** tại Global Azure 2026 (DevCafe Vietnam, 18/04/2026).

---

## 🖼️ Sơ đồ 1 — Các lớp lồng nhau *(đã mở rộng 🆕)*

```
┌────────────────────────────────────────────────────────────┐   ▲
│ 🆕 LOOP / ORGANIZATION ENGINEERING                         │   │
│    Ai giao việc, ai kiểm tra, khi nào dừng.                │   │
│    Vòng lặp tự chạy · đồ thị nhiều agent · human gate      │   │
│                                                            │   │
│  ┌──────────────────────────────────────────────────────┐  │   │
│  │  HARNESS ENGINEERING                                 │  │   │
│  │  Toàn bộ hạ tầng — tools, memory, sandbox,           │  │  Phạm
│  │  orchestration, serving, xử lý lỗi, kiểm chứng       │  │  vi
│  │                                                      │  │  mở
│  │   ┌────────────────────────────────────────────┐     │  │  rộng
│  │   │  CONTEXT ENGINEERING                       │     │  │  dần
│  │   │  Cái gì được đưa vào cửa sổ ngữ cảnh và    │     │  │   │
│  │   │  đưa vào lúc nào — retrieval, nén, dựng    │     │  │   │
│  │   │                                            │     │  │   │
│  │   │   ┌──────────────────────────────────┐     │     │  │   │
│  │   │   │  PROMPT ENGINEERING              │     │     │  │   │
│  │   │   │  Soạn chỉ dẫn — bạn nói gì với   │     │     │  │   │
│  │   │   │  model                           │     │     │  │   │
│  │   │   └──────────────────────────────────┘     │     │  │   │
│  │   └────────────────────────────────────────────┘     │  │   │
│  └──────────────────────────────────────────────────────┘  │   │
└────────────────────────────────────────────────────────────┘   │
```

**Ý chính:** *Mỗi lớp bao trùm lớp trước. Lớp mới không thay thế lớp cũ — nó quyết định lớp cũ được dùng như thế nào.*

---

## 🖼️ Sơ đồ 2 — Dòng thời gian tiến hoá *(đã cập nhật 🆕)*

```
2022 ─────── 2023 ─────── 2024 ─── đầu 2025 ─ giữa 2025 ─── đầu 2026 ─ giữa 2026 ─ 09/2026
│                                │             │              │           │
├────────────────────────────────┤             │              │           │
│      PROMPT ENGINEERING        │             │              │           │
│      "Mình nên nói gì?"        │             │              │           │
                                 ├─────────────┤              │           │
                                 │ CONTEXT ENG.│              │           │
                                 │ "Model cần  │              │           │
                                 │  thấy gì?"  │              │           │
                                               ├──────────────────────────┤
                                               │   HARNESS ENGINEERING    │
                                               │   "Xây hệ thống gì?"     │
                                                                ├─────────┤
                                                                │ LOOP /  │
                                                                │ GRAPH   │
                                                                │ ENG. 🆕 │

Trọng tâm kỹ thuật dịch chuyển:
  Prompt text ──→ Cách dựng cửa sổ ngữ cảnh ──→ Kiến trúc hệ thống ──→ Kiến trúc điều khiển
  ←──────────  "chỗ đặt sự chặt chẽ kỹ thuật"  ──────────→
```

> 🔲 **CHỖ TRỐNG — Thế hệ kế tiếp.** Khi xuất hiện một tên gọi thứ năm được dùng rộng rãi, thêm cột vào đây kèm: (a) câu hỏi trung tâm, (b) trần mà thế hệ thứ tư không vượt được, (c) 2–3 nguồn độc lập chứng minh thuật ngữ đã được chấp nhận chứ không phải một bài blog lẻ.

---

## 1. Prompt Engineering

**Giai đoạn:** 2022 → hết phần lớn 2024.

**Giả định nền tảng:** LLM được huấn luyện trên kho tri thức nhân loại khổng lồ — sách, code, bài báo, hội thoại — và tri thức đó bị **nén vào hàng tỷ tham số**. Nếu tri thức đã nằm sẵn trong model, thì biến số duy nhất còn lại là **cách bạn diễn đạt yêu cầu**. Viết đúng chữ, đúng cấu trúc → mở khoá đúng câu trả lời.

Toàn bộ nghề nghiệp nằm gọn trong **prompt text**: chính xác từ ngữ, cấu trúc, và chỉ dẫn bạn đưa cho model. Đúng thì model làm rất đẹp; sai thì nhận về câu trả lời chung chung hoặc **hallucination** (model bịa ra thông tin nghe hợp lý nhưng sai).

**Các kỹ thuật đã thực sự hiệu quả:**

- **Chain-of-Thought** — "hãy suy nghĩ từng bước một"
- **Few-shot examples** — cho vài ví dụ mẫu
- **Role prompting** — gán vai trò cho model

Prompt engineering đi từ một *kỹ năng* → một *chức danh công việc* → gần như một *huyền thoại*.

> *"Ngôn ngữ lập trình mới nóng nhất chính là tiếng Anh."* — Andrej Karpathy, 2023

### Code minh hoạ (nguyên văn từ bài gốc)

```python
system_prompt = """
You are a coding assistant.
Rules:
- Return JSON only
- Never skip edge cases
- Use snake_case
"""

response = openai.chat(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": query}
    ]
)
# Không có bộ nhớ. Mỗi lần gọi đều bắt đầu lại từ đầu.
```

### 🖼️ Sơ đồ 3 — Hai giới hạn của Prompting

```
┌─────────────────────────────────┐  ┌─────────────────────────────────┐
│ 01  HALLUCINATION               │  │ 02  KNOWLEDGE CUTOFF            │
│                                 │  │                                 │
│ Soạn chỉ dẫn khéo chỉ là bản vá │  │ Model không truy cập được dữ    │
│ bề mặt — nó không loại bỏ được  │  │ liệu mới: phiên bản thư viện    │
│ xu hướng bịa đặt vốn nằm ngay   │  │ vừa cập nhật, thay đổi API gần  │
│ trong bản thân model, nhất là   │  │ đây, bất cứ thứ gì xuất hiện    │
│ với các tác vụ mơ hồ.           │  │ sau mốc cắt huấn luyện.         │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

**Vì sao chạm trần:** Giới hạn nằm ở **cấu trúc**, không phải ở văn phong. LLM bị đóng băng trong thời gian — tri thức dừng ở mốc huấn luyện. Nó không biết công ty bạn vừa ship gì tuần trước, chính sách nội bộ nói gì, hay hệ thống vừa ném ra lỗi gì năm phút trước. Dù bạn diễn đạt khéo tới đâu, model cũng không thể trả lời chính xác từ tri thức mà nó **không có**.

Nút thắt đã dịch chuyển: vấn đề không còn là **bạn nói gì**, mà là **model nhìn thấy được gì**.

---

## 2. Context Engineering

**Giai đoạn:** xuất hiện cuối 2023.

Câu hỏi thật sự trở thành: **nạp cái gì vào cửa sổ ngữ cảnh** — tức toàn bộ những gì model nhìn thấy trước khi sinh ra câu trả lời.

Trong một **agentic loop** (vòng lặp agent), ngữ cảnh không bao giờ đứng yên. Mỗi lượt lại có thêm thông tin được ghép vào:

- **Conversation history** — các lượt hội thoại trước
- **Knowledge retrieval** — tài liệu liên quan được kéo về từ nguồn ngoài qua **RAG** (Retrieval-Augmented Generation)
- **Tool results** — kết quả từ các công cụ MCP mà agent đã gọi, *bao gồm cả những lần thất bại* mà agent có thể học từ đó

Prompt không còn là thứ bạn viết một lần. Nó trở thành một **bản dựng động** được dựng lại ở **mỗi lượt** — phình ra, đổi hình, tích luỹ trạng thái. Mà cửa sổ ngữ cảnh thì có **giới hạn cứng**.

### Hai kỹ thuật chống trần — đánh đổi khác nhau về bản chất

**Compaction (nén — còn phục hồi được)**
Bỏ đi những thông tin vốn đã tồn tại sẵn ở nơi khác trong môi trường. Nếu agent vừa viết một file 500 dòng, chỉ lưu **đường dẫn** — khi cần agent tự đọc lại. Tín hiệu được giữ nguyên vẹn.
→ *Claude Code* triển khai bằng cách nén ngữ cảnh nhưng luôn giữ sẵn **năm file được truy cập gần nhất**.

**Summarization (tóm tắt — mất thông tin không hồi phục)**
Dùng LLM viết lại lịch sử thành ngôn ngữ tự nhiên. Nén rất mạnh, người đọc được — nhưng **không đảo ngược được**. Một chi tiết đã bị tóm tắt bỏ đi là mất luôn.

> **Thứ tự ưu tiên:** ngữ cảnh thô > compaction > summarization.
> Chỉ dùng cách nén mất thông tin như **phương án cuối cùng**.

### Vấn đề còn sót lại

Ngay cả với các kỹ thuật trên, vẫn còn một vấn đề sâu hơn: khi model tự tóm tắt lịch sử hội thoại của chính nó, nó trở nên **thiên lệch về phía những gì nó đã chọn để nhớ**. Các chi tiết quan trọng bị lặng lẽ đánh rơi.

- **RAG** giúp được bằng cách chỉ kéo về thứ liên quan, theo yêu cầu.
- **Dynamic tool selection** (chọn công cụ theo tình huống) giữ cho danh sách MCP tool gọn nhẹ.

Tất cả đều quy về cùng một ràng buộc gốc: **cửa sổ ngữ cảnh là hữu hạn, và mỗi token đều là một lựa chọn.**

**Vì sao chạm trần:** Context engineering làm agent **thông minh hơn**. Nó không làm agent **đáng tin cậy hơn**. Muốn có độ tin cậy, bạn cần nhiều hơn một prompt viết khéo hay một cửa sổ ngữ cảnh được tổ chức tốt — bạn cần **một hệ thống**.

### 🆕 Bổ sung 2026: hai kết quả đáng chú ý

**① Bằng chứng thực nghiệm rằng "context là hệ thống, không phải kỹ năng".**
Microsoft báo cáo đã chuyển SRE Agent của họ từ **hơn 100 công cụ viết riêng** sang một kiến trúc **ngữ cảnh dựa trên filesystem**, và điểm *"Intent Met"* trên các sự cố chưa từng gặp tăng từ **45% lên 75%**. ⚠️ Con số này đến từ báo cáo của chính nhà cung cấp, chưa có bên thứ ba tái lập.

**② Agentic Context Engineering (ACE).**
Zhang và cộng sự, công bố tại **ICLR 2026**, thử nghiệm một vòng lặp ba pha: *sinh chiến lược từ các lần thử → soi lại xem cái gì hiệu quả → biên tập lại ngữ cảnh*, giữ chiến lược thành công và loại bỏ chiến lược thất bại. Điểm mới là ngữ cảnh trở thành **thứ được học và tích luỹ**, chứ không phải thứ được lắp lại từ đầu mỗi phiên.

> 🔲 **CHỖ TRỐNG — Kiểm chứng độc lập.** Ghi lại ở đây khi có bên thứ ba tái lập được (a) con số 45%→75% của Microsoft, hoặc (b) kết quả ACE trên bộ tác vụ khác. Nếu tái lập thất bại, giữ nguyên phần ghi này và đổi dấu ⚠️ thành ghi chú phản bác.

---

## 3. Harness Engineering

**Giai đoạn:** cuối 2025 bước sang 2026.

**Mitchell Hashimoto** — đồng sáng lập HashiCorp — viết bài *"My AI Adoption Journey"* và đặt tên cho thứ đang hình thành: **harness engineering**.

### 🖼️ Sơ đồ 4 — Ý tưởng của Hashimoto

```
┌────────────────────────────────┐   ┌──────────────────────────────────┐
│ "Tôi dần gọi cái này là        │   │ ▍01 CHỈ DẪN NGẦM TỐT HƠN         │
│  'HARNESS ENGINEERING.'        │   │                                  │
│  Đó là ý niệm rằng bất cứ khi  │   │ AGENTS.md — mỗi dòng dựa trên    │
│  nào bạn thấy AN AGENT MAKES   │   │ một hành vi xấu có thật đã quan  │
│  A MISTAKE, bạn bỏ thời gian   │   │ sát được. Gần như dập tắt hẳn    │
│  ra ENGINEER A SOLUTION SUCH   │   │ các lỗi lặp lại.                 │
│  THAT THE AGENT NEVER MAKES    │   ├──────────────────────────────────┤
│  THIS MISTAKE AGAIN."          │   │ ▍02 CÔNG CỤ ĐƯỢC LẬP TRÌNH THẬT  │
│                                │   │                                  │
│              Mitchell Hashimoto│   │ Script, type checker, bộ khung   │
│                                │   │ kiểm chứng — biến phán đoán của  │
│                                │   │ con người thành ràng buộc hệ     │
│                                │   │ thống mà agent không lách được.  │
└────────────────────────────────┘   └──────────────────────────────────┘
```

Điều Hashimoto mô tả **không phải** là tinh chỉnh prompt. Đó là một **quan hệ khác về chất với sai lầm**: lỗi không bị bỏ qua âm thầm — chúng được **viết thành ràng buộc vĩnh viễn** lên hệ thống. Hai hình thức cụ thể:

1. **Chỉ dẫn ngầm tốt hơn qua `AGENTS.md`** — một file ràng buộc, mỗi dòng đại diện cho một hành vi xấu **có thật** đã được quan sát và chặn lại. Đơn giản, bền, bồi đắp độ đúng theo thời gian.

2. **Công cụ được lập trình thật sự** — script, type checker, bộ khung kiểm chứng. Nếu agent cứ gọi sai một API, hãy viết code buộc mọi lời gọi API phải qua type checking. Biến phán đoán của con người thành ràng buộc hệ thống mà agent **không thể bỏ qua**.

```markdown
# AGENTS.md — các ràng buộc tích luỹ từ những lần thất bại thật
## Rules
- Never modify migration files
- All DB writes must go through the service layer
- Run tests before marking any task complete
- Never delete files without confirmation
```

*(Tạm dịch: Không sửa file migration · Mọi thao tác ghi DB phải đi qua service layer · Chạy test trước khi đánh dấu hoàn thành task · Không xoá file khi chưa được xác nhận.)*

**Không phải prompt. Không phải ngữ cảnh. Mà là hệ thống.**

Harness engineering = thiết kế **toàn bộ hạ tầng bao quanh model**: tools, memory, sandbox, orchestration, phục hồi lỗi, vòng đánh giá, rào an toàn. Sau bài của Hashimoto, thuật ngữ này xuất hiện khắp nơi — các đội xây sản phẩm AI nghiêm túc, LangChain ship *Open Deep Research* trên LangGraph, nhiều công ty tư duy lại toàn bộ hạ tầng.

Sự chặt chẽ kỹ thuật đã lặng lẽ dịch từ **prompt text** sang **kiến trúc hệ thống**. Câu hỏi không còn là "làm sao viết prompt hay?" — mà là "**mình thực sự muốn xây cái gì?**"

> LangChain đúc kết gọn (03/2026):
> ### **Agent = Model + Harness**

Model chứa **trí tuệ**; harness làm cho trí tuệ đó **dùng được**. Harness là mọi mẩu code, cấu hình và logic thực thi **không phải là model**. Model cung cấp dự đoán token **phi trạng thái** (không nhớ gì giữa các lần gọi). Harness cung cấp mọi thứ khiến điều đó có ích: **memory, tools, ràng buộc, sandbox, orchestration, phản hồi**.

🆕 Đến giữa 2026, cách nói này đã thành mặc định trong giới học thuật lẫn công nghiệp, và được diễn đạt gọn hơn nữa: *nếu bạn không phải là model, thì bạn là harness*. Kèm theo đó là một hệ quả đo lường quan trọng: **hiệu năng của agent phải được hiểu là thuộc tính của một model đặt trong một hệ thống thực thi cụ thể, chứ không phải thuộc tính của riêng model** — xem mục 5.2 về Harness-Bench.

### 🖼️ Sơ đồ 5 — Giải phẫu một Agent Harness

```
        NGƯỜI DÙNG
             │
             ▼
┌────────────────────────────────────────┐
│ 3.1  SERVING LAYER                     │  Nhận input / trả output
│      Gateway · trừu tượng hoá Channel  │  (WhatsApp, Slack, IDE, Web…)
├────────────────────────────────────────┤
│ 3.2  ORCHESTRATION                     │  Định tuyến & chia nhỏ tác vụ
│      Sinh subagent · Multi-agent       │
├────────────────────────────────────────┤
│ 3.3  SANDBOX                           │  Cô lập thực thi & mở rộng ngang
│      Subprocess → Docker → Cloud       │
├────────────────────────────────────────┤
│ 3.4  CONTEXT ENGINEERING               │  Quyết định cái gì vào ngữ cảnh
│      Compaction · Progressive          │  và vào lúc nào
│      Disclosure · Tool Offloading      │
├────────────────────────────────────────┤
│ 3.5  MEMORY                            │  Cửa sổ ngữ cảnh / RAM / Filesystem
├────────────────────────────────────────┤
│ 3.6  TOOLS                             │  MCP, có cổng phân quyền
├────────────────────────────────────────┤
│ 3.7  AGENT LOOP                        │  ReAct · Orchestrator-Worker
├────────────────────────────────────────┤
│ 🆕 3.8  DURABILITY & OBSERVABILITY     │  Checkpoint · hibernate/wake ·
│      Thực thi bền · vết chạy · eval    │  truy vết để cải tiến bộ khung
└────────────────────────────────────────┘
             │
             ▼
          MODEL  (dự đoán token, phi trạng thái)
```

---

### 3.1 Serving Layer (lớp tiếp nhận)

Serving layer là cách agent **nhận input và trả output**.

Bài học kiến trúc từ **OpenClaw** là trừu tượng hoá **Channel**: thay vì deploy một bot riêng cho từng nền tảng, **một tiến trình Gateway duy nhất** nhận tin nhắn từ nhiều nền tảng khác nhau và định tuyến chúng vào **cùng một kho phiên (session store)**.

Một instance OpenClaw, kết nối nhiều nền tảng chat. **Cùng một bộ não, cùng một bộ nhớ, cùng một agent.** Bắt đầu hội thoại trên WhatsApp rồi tiếp tục trên Telegram — OpenClaw vẫn giữ được mạch vì ngữ cảnh dùng chung.

Các bề mặt được hỗ trợ: WhatsApp, Telegram, Slack, Discord, Signal, iMessage, Google Chat, Microsoft Teams, Matrix, Zalo và **50+** nền tảng khác. Mỗi channel plugin lo phần xác thực, nhận tin và gửi phản hồi — nhưng **agent phía sau là y hệt nhau**.

**Khác biệt then chốt giữa các channel là lượng ngữ cảnh mà chúng cung cấp được:**

| Loại channel | Ngữ cảnh thu được | Đặc điểm |
|---|---|---|
| **TUI / IDE plugin** (VS Code, JetBrains) | Nhiều nhất | Agent thấy file đang mở, vị trí con trỏ, lỗi đang hiện |
| **Web app** | Trung bình | Không cần cài đặt, dễ tiếp cận |
| **Messaging** (WhatsApp, Telegram, Slack) | Ít nhất | Chỉ có text — nhưng gặp người dùng ngay nơi họ đã ở sẵn |

Gateway **chuẩn hoá** tất cả về một định dạng phiên thống nhất **trước khi** agent nhìn thấy chúng.

> 🔲 **CHỖ TRỐNG — Channel mới.** Khi có bề mặt tiếp nhận mới đáng kể (thiết bị đeo, xe hơi, agent-to-agent qua giao thức máy–máy, v.v.), thêm dòng vào bảng trên kèm cột "ngữ cảnh thu được" và một câu về việc nó đổi thiết kế harness ra sao.

---

### 3.2 Orchestration (điều phối)

Orchestration **không phải** là điểm vào của request — đó là việc của serving layer. Orchestration là **logic định tuyến và chia nhỏ**: cho một tác vụ, quyết định chia nó thế nào và ai xử lý phần nào. Hình dung như **OpenRouter** — không phải cổng vào, mà là **định tuyến thông minh**.

#### 🖼️ Sơ đồ 6 — Hai pattern chủ đạo

```
A. SUBAGENT SPAWNING (sinh agent con)      B. MULTI-AGENT COORDINATION
   — SAO CHÉP ngữ cảnh                        — CHIA ngữ cảnh

        ┌──────────┐                           ┌──────────────┐
        │  PARENT  │                           │ ORCHESTRATOR │
        │  ctx: ▓▓▓│                           │  ctx: ▓▓▓    │
        └────┬─────┘                           └──┬───┬───┬───┘
             │ spawn                           chia│   │   │
      ┌──────┴──────┐                       ┌──────┘   │   └──────┐
      ▼             ▼                       ▼          ▼          ▼
 ┌──────────┐ ┌──────────┐            ┌─────────┐┌─────────┐┌─────────┐
 │ CHILD 1  │ │ CHILD 2  │            │ AGENT A ││ AGENT B ││ AGENT C │
 │ ctx: ▓▓▓ │ │ ctx: ▓▓▓ │            │ ctx: ▓  ││ ctx: ▓  ││ ctx: ▓  │
 │ (bản sao)│ │ (bản sao)│            │(lát cắt)││(lát cắt)││(lát cắt)│
 └──────────┘ └──────────┘            └────┬────┘└────┬────┘└────┬────┘
                                           └──────────┼──────────┘
                                                      ▼
                                              tổng hợp kết quả
```

**Subagent Spawning:** Agent cha tạo agent con. Khi sinh con, nó viết một prompt mới, gán một bộ công cụ cụ thể, và **nhân bản cửa sổ ngữ cảnh của mình sang con** — đứa con có đủ ngữ cảnh để làm việc độc lập.
→ Trong tính năng **"Agent Teams"** của Claude Code (lộ ra từ vụ rò rỉ mã nguồn tháng 03/2026): một phiên đóng vai **trưởng nhóm**, sinh ra các sub-agent độc lập chạy song song, mỗi con có ngữ cảnh riêng, giao tiếp qua một **danh sách việc dùng chung có theo dõi phụ thuộc**.

**Multi-agent Coordination:** Tác vụ được chia nhỏ và cửa sổ ngữ cảnh được **chia** cho các agent chuyên biệt. Mỗi agent chỉ thấy lát cắt liên quan tới nó. Orchestrator thu thập và tổng hợp kết quả. Khác với spawning, ngữ cảnh **không được nhân bản — nó bị chia nhỏ**.

> **Khác biệt cốt lõi:** spawning **sao chép** ngữ cảnh và giao **một** tác vụ; multi-agent coordination **chia nhỏ** bài toán và đưa cho mỗi agent **đúng phần của nó**.

🆕 **Điều gì thực sự sống sót trong production (tổng kết giữa 2026).** Các báo cáo vận hành thực tế hội tụ vào một kết luận không mấy hào nhoáng: **quản lý trạng thái, chứ không phải chất lượng model, mới là khó khăn số một**. Nếu một quy trình năm bước mất ngữ cảnh ở bước bốn, nó phải chạy tiếp được từ bước bốn — chứ không phải làm lại từ đầu. Xem mục 3.8.

---

### 3.3 Sandbox

Agent chạy code. Code đó có thể **xoá file, làm sập hệ thống, hoặc rò rỉ credential**. Sandbox đảm bảo thất bại được **khoanh vùng**, đồng thời cho phép **mở rộng ngang** qua nhiều môi trường song song.

**Ba mức cô lập, theo thứ tự an toàn tăng dần:**

1. **Local subprocess / dev-test** — tiến trình cô lập trên máy local; nhanh, hợp cho thử nghiệm.
2. **Local Docker** — container trên host; cô lập hơn, gần điều kiện production hơn.
3. **Remote cloud container** — tạo theo yêu cầu, huỷ khi xong; an toàn nhất, mở rộng ngang được, có GPU cho tải nặng.

🆕 Từ giữa 2026, mức 3 tách thành hai nhánh rõ rệt theo cơ chế cô lập: **microVM** (Firecracker và tương đương — cô lập ở tầng ảo hoá) và **sandbox nhân người dùng** kiểu gVisor (cô lập ở tầng syscall). Đánh đổi quen thuộc: microVM an toàn hơn nhưng khởi động chậm hơn; gVisor khởi động nhanh, phù hợp khi cần tạo/huỷ liên tục.

**Bài học đắt giá về cô lập credential:** đã từng có thiết kế ghép chung (*coupled*) chạy **code do agent sinh ra, không đáng tin, trong cùng container với credential** — chỉ cần **một** lần prompt injection là đọc được toàn bộ biến môi trường.

> **Cách sửa mang tính cấu trúc, không thương lượng:** credential **không bao giờ** được nằm trong tầm với của sandbox nơi code do agent sinh ra được chạy.

🆕 **Chuẩn thực hành đã cụ thể hơn (2026):** khởi động sandbox với **bộ credential rỗng**, rồi **tiêm từng secret theo đúng tác vụ** qua một cơ chế mà bản thân agent không chạm tới được — thay vì để sandbox kế thừa toàn bộ biến môi trường của host.

🆕 **Về mặt chính sách:** tháng 05/2026, nhóm **Five Eyes** (CISA, NSA và các cơ quan tương ứng) ra hướng dẫn chung về agentic AI, gọi tên **prompt injection** là con đường tấn công cốt lõi và nhấn mạnh rằng **không một biện pháp đơn lẻ nào là đủ** — phải xếp chồng nhiều lớp phòng thủ.

> 🔲 **CHỖ TRỐNG — Sự cố thực tế.** Mỗi khi có một vụ rò rỉ/lạm dụng agent được công bố công khai, thêm một dòng vào bảng dưới. Mục tiêu là biến sự cố thành ràng buộc thiết kế, đúng tinh thần Hashimoto.
>
> | Ngày | Sự cố | Lớp harness bị thủng | Ràng buộc rút ra |
> |---|---|---|---|
> | *(trống)* | | | |

---

### 3.4 Context Engineering (ở tầng harness)

Ở tầng harness, context engineering **không còn là một kỹ năng thủ công** — nó là một **thành phần được kỹ thuật hoá**, chạy ở **mọi lần gọi**, quyết định cái gì vào cửa sổ ngữ cảnh và vào lúc nào.

Ba kỹ thuật xử lý ba bề mặt vấn đề khác nhau:

**① Compaction — xử lý lịch sử hội thoại.**
Khi số token tiến sát trần (ví dụ còn dưới 200k), harness nén các lượt cũ lại.
Claude Code triển khai **năm chiến lược compaction** khác nhau:
- **"Snip"** — cắt tỉa các message cũ, nhanh nhưng mất thông tin;
- **"Microcompact"** — nhắm riêng vào tool output;
- **hai chiến lược còn lại vẫn nằm sau feature flag** — dấu hiệu cho thấy bài toán này chưa được giải ở quy mô lớn.

**② Progressive Disclosure — xử lý tool input.**
Giống một hệ thống skill: agent đọc **tên và mô tả** của tất cả công cụ khả dụng trước, phát hiện khi nào cần một công cụ cụ thể, rồi mới **nạp đầy schema** vào ngữ cảnh theo yêu cầu. Không có gì được nạp sẵn hàng loạt. Đây chính là pattern dùng trong các framework agent skill — **nạp mô tả trước, nạp chi tiết khi cần**.

🆕 Đến giữa 2026 pattern này đã được **chuẩn hoá thành một định dạng đóng gói**: một skill là một **thư mục** gồm file `SKILL.md` (mô tả + chỉ dẫn) và các tài nguyên đi kèm. Chỉ có *tên và mô tả* thường trực trong ngữ cảnh; phần thân và file đính kèm chỉ được đọc khi mô tả khớp với tác vụ. Hệ quả thực tế: **cài bao nhiêu skill cũng gần như không tốn ngữ cảnh** cho tới khi skill đó được kích hoạt. Cách đóng gói này hiện có mặt trong Claude Agent Skills và Microsoft Agent Framework.

⚠️ Có phản biện đáng ghi nhận: một số nghiên cứu 2026 đặt câu hỏi liệu progressive disclosure **một mình** có đủ cho tác vụ ngữ cảnh dài hay không, khi agent phải quyết định "cần gì" trước lúc nó thực sự biết mình cần gì. Đây là câu hỏi mở, chưa ngã ngũ.

**③ Tool Offloading — xử lý tool output.**
Thay vì nạp hàng trăm tool schema vào cửa sổ ngữ cảnh, lưu chúng trong một **từ điển nằm ngoài** cửa sổ. LLM chỉ dùng **ba công cụ cố định**:

| Tool | Chức năng |
|---|---|
| **Search** | Tìm theo ngữ nghĩa hoặc gần đúng để xác định đúng công cụ cần |
| **Load** | Nạp schema của công cụ đó vào ngữ cảnh |
| **Execute** | Gọi công cụ |

Đây là **meta-programming** — API sống trong một từ điển; LLM lúc nào cũng chỉ nhìn thấy ba công cụ.

**Pattern này đã lan rộng:** OpenAI Agents SDK thêm `deferLoading: true`. ZeroClaw triển khai gần như y hệt. CrewAI thêm dynamic tool injection ở v1.10.2.

> Nếu bạn có **hơn ~20 công cụ** mà không làm điều này, bạn đang **đốt token ở mọi lần gọi**.

🆕 **Hỗ trợ từ phía giao thức:** bản đặc tả **MCP 2026-07-28** bổ sung **kết quả `tools/list` có thể cache** kèm `ttlMs`, cho phép client giữ lại danh mục công cụ thay vì hỏi lại mỗi phiên — biến tool offloading từ mẹo phía ứng dụng thành thứ được giao thức đỡ lưng. Xem mục 5.1.

---

### 3.5 Memory (bộ nhớ)

Bộ nhớ agent trong production vận hành trên **ba tầng**:

| Tầng | Là cái gì | Vòng đời |
|---|---|---|
| **Cửa sổ ngữ cảnh** | Thứ LLM đang thực sự đọc ngay lúc này | Mất sau mỗi request |
| **RAM** | Lịch sử hội thoại và tool result của phiên hiện tại | Mất khi tiến trình thoát |
| **Filesystem** | Các file Markdown ghi xuống đĩa | **Sống sót qua mọi phiên** |

Phản xạ đầu tiên của phần lớn người mới là nghĩ ngay tới **vector database**. Thực tế đơn giản hơn nhiều: Claude Code dùng kiến trúc memory ba lớp xoay quanh **`MEMORY.md`** — lưu **tham chiếu ngắn** thay vì thông tin đầy đủ. **Không vector database. Không RAG pipeline.**

Thứ giữ tất cả lại với nhau chính là **Markdown thuần**: người đọc được, người sửa được, và bền.

- Một `MEMORY.md` làm mục lục trỏ tới các file theo chủ đề
- Một `AGENTS.md` được chèn vào lúc bắt đầu phiên
- Một `claude-progress.txt` cập nhật sau mỗi phiên làm việc

→ Bộ nhớ **sống sót được, kiểm tra được, và chính agent tự cập nhật được**.

**Pattern long-running agent của Anthropic** làm điều này cụ thể hơn: một **initializer agent** chạy ở phiên đầu tiên, ghi ra file tiến độ, tạo commit git khởi đầu. **Mọi phiên sau đó đọc file đó trước tiên** — chuyển giao tri thức bền vững từ phiên này sang phiên khác, **không cần hạ tầng gì thêm**.

> 🔲 **CHỖ TRỐNG — Khi nào Markdown không còn đủ.** Ghi lại ở đây ngưỡng quan sát được (số phiên, dung lượng, số agent dùng chung) mà tại đó bộ nhớ dạng file phẳng bắt đầu hỏng, và cái gì thay thế nó. Đây là chỗ vector DB *có thể* quay lại một cách chính đáng — nhưng cần dữ liệu, không phải cảm tính.

---

### 3.6 Tools (công cụ)

Trước vụ **rò rỉ mã nguồn Claude Code ngày 31/03/2026**, nhiều người tưởng chỉ cần đưa cho agent một bash shell là đủ. **512.000 dòng TypeScript** bị lộ cho thấy kiến trúc thật: Claude Code **không phải** một lớp bọc chat. Nó là một **kiến trúc kiểu plugin**, trong đó **mọi năng lực đều là một công cụ riêng biệt, có cổng phân quyền** — BashTool, FileRead, FileWrite, WebFetch, tích hợp LSP, và **~40 công cụ khác**.

**Vì sao bọc công cụ trong MCP thay vì phơi bash trần:** vì **permission gating** (cổng phân quyền).
> Bash cho agent **mọi thứ**. MCP chỉ cho agent **đúng những gì nó được phép có**.

**Hệ thống phân quyền của Claude Code xây trên nguyên tắc `default-deny` (mặc định từ chối).** Mỗi công cụ khai báo:
- `isReadOnly` — **mặc định là `false`** (tức là mặc định giả định công cụ có ghi)
- một **mức rủi ro** (risk level)

Hệ thống xếp chồng thêm: kiểm tra theo luật (`alwaysAllow` / `alwaysDeny`), **pre-tool-use hook**, và một **bộ phân loại an toàn cho chế độ tự động**.

Đây chính là thứ người dùng nhìn thấy dưới dạng **luồng phê duyệt** — lựa chọn giữa *tự động chấp thuận* và *có người duyệt* thật ra là **logic if-else nằm ngay bên trong lớp bọc MCP tool**.

**Bộ công cụ tiêu chuẩn:**

| Tool | Mục đích |
|---|---|
| **Bash** | Đa dụng; agent có thể viết và chạy script tại chỗ |
| **Read / Write** | Thao tác file kèm kiểm tra an toàn (kiểm tra đường dẫn, giới hạn số dòng) |
| **Edit** | Sửa tại chỗ có mục tiêu; thay chuỗi cụ thể, không ghi đè cả file |
| **Glob** | Tìm file theo mẫu tên (`*.py`, `src/**/*.ts`) |
| **Grep** | Tìm bên trong file theo mẫu nội dung |
| **Task** | Sinh một subagent mới — **cầu nối giữa Tools và Orchestration** |

---

### 3.7 Agent Loop (vòng lặp agent)

#### Pattern 1 — ReAct Loop (Reasoning + Acting)

```
Observe → Reason → Act → Observe → ...
(Quan sát → Suy luận → Hành động → Quan sát → ...)
```

Mỗi lần **Act** đều làm thay đổi ngữ cảnh, nên **không có vòng lặp thật sự** — mỗi vòng là một **bước chuyển sang trạng thái mới**.

**Generator pattern** trong Claude Code làm điều này trở nên rõ ràng: mỗi bước là một `yield`, giữ được trạng thái mà **không cần vòng `while` truyền thống**. Nhờ vậy bạn có thể:
- test từng giai đoạn riêng lẻ,
- thêm compaction hoặc kiểm tra quyền như **các chặng trong pipeline**, thay vì callback chắp vá bên ngoài.

#### Pattern 2 — Orchestrator-Worker

Một orchestrator chia nhỏ tác vụ và giao cho các worker chuyên biệt. Điểm mấu chốt: một **bộ kiểm chứng riêng biệt** rà soát output của worker **trước khi** nó được chấp nhận — **kiểm chứng tách rời khỏi thực thi**.

Trong các **"swarm"** đa agent của Claude Code: một phiên làm **điều phối viên**, sinh các sub-agent với quyền công cụ riêng cho những tác vụ song song hoá được, và một **danh sách việc dùng chung có theo dõi phụ thuộc** điều phối công việc.

> **Khác biệt cốt lõi:**
> **ReAct** phù hợp nhất cho tác vụ **tuần tự, đơn luồng, nhiều bước**.
> **Orchestrator-Worker** phù hợp nhất cho tác vụ **song song hoá được và cần kiểm chứng độc lập**.

---

### 🆕 3.8 Durability & Observability (tính bền và khả năng quan sát)

Đây là lớp mà bài gốc chưa có, và là thứ nổi lên rõ nhất trong nửa cuối 2026 khi agent bắt đầu chạy **hàng giờ đến hàng ngày** thay vì hàng phút.

**Vấn đề:** một phiên agent dài không thể giả định rằng tiến trình sẽ sống sót. Máy restart, mạng đứt, quota hết, model timeout. Nếu mất trạng thái là phải làm lại từ đầu, thì mọi tác vụ dài đều không khả thi về mặt kinh tế.

**Ba cơ chế đã thành chuẩn:**

| Cơ chế | Làm gì | Ví dụ triển khai |
|---|---|---|
| **Checkpointing** | Lưu ảnh chụp trạng thái sau **mỗi bước**, gắn theo luồng (thread) | LangGraph — cho phép chạy tiếp từ bước cuối cùng thành công, đồng thời mở ra debug "tua ngược" và điểm dừng chờ người duyệt |
| **Hibernate & wake** | Cho workflow **ngủ đông** giữa các chặng dài rồi đánh thức lại, thay vì giữ tiến trình sống | Meta dùng cơ chế này cho agent chạy pipeline ML nhiều ngày ⚠️ (nguồn: báo cáo nội bộ được thuật lại) |
| **Ngân sách có phê duyệt** | Đặt trần chi phí/số bước do người quyết định, agent chạy trong trần đó | Cùng hệ thống của Meta |

**Khả năng quan sát** là mặt còn lại của cùng đồng xu: nếu không ghi lại được **vết chạy (trajectory)** của agent, bạn không thể biết nó hỏng ở đâu, và cũng không thể cải tiến bộ khung một cách có căn cứ. 🆕 Đã bắt đầu có sản phẩm thương mại cho riêng việc này — ví dụ **Amazon CloudWatch Coding Agent Insights** (giám sát hiệu năng agent lập trình ở quy mô tổ chức).

> 🔲 **CHỖ TRỐNG — Chỉ số vận hành của riêng bạn.** Bảng dưới để điền số đo thật từ hệ thống của mình, thay vì đi mượn số của người khác.
>
> | Chỉ số | Định nghĩa | Giá trị hiện tại | Ngày đo |
> |---|---|---|---|
> | Tỉ lệ hoàn thành phiên dài | % phiên >1h kết thúc thành công | *(trống)* | |
> | Chi phí trung bình / tác vụ | token + hạ tầng | *(trống)* | |
> | Tỉ lệ can thiệp của người | % bước cần người duyệt | *(trống)* | |
> | Lỗi lặp lại sau khi thêm ràng buộc | kiểm chứng cách làm của Hashimoto | *(trống)* | |

---

## 🆕 4. Loop Engineering — thế hệ thứ tư đang hình thành

**Giai đoạn:** thuật ngữ được đặt tên khoảng **tháng 06/2026**.

Nếu harness engineering trả lời câu hỏi *"môi trường agent chạy trong đó trông như thế nào?"*, thì loop engineering trả lời câu hỏi tiếp theo: **"ai quyết định bước kế tiếp?"**

Định nghĩa gọn: **loop engineering là việc thiết kế hệ thống điều khiển tự ra chỉ dẫn, tự kiểm chứng, tự thử lại và tự biết khi nào dừng — thay vì bạn ngồi gõ lệnh tiếp theo từng lượt một.**

Công thức được nhắc nhiều nhất:

> **Một vòng lặp = một tác vụ + một phép kiểm.**
> **Tác vụ không có phép kiểm thì chỉ là hy vọng.**

⚠️ Về nguồn gốc thuật ngữ: các bài tổng hợp quy về các bài viết của **Addy Osmani** và một phát biểu ngắn của **Peter Steinberger** (người đứng sau dự án OpenClaw) ngày **07/06/2026**, cho rằng kỹ năng đáng giá không còn là *ra lệnh cho agent lập trình* mà là *thiết kế cái vòng lặp ra lệnh cho nó*. Đây là thuật ngữ mới, độ ổn định chưa bằng "harness engineering".

### Lớp kế tiếp nữa: tổ chức theo đồ thị

Song song với loop engineering, một hướng thứ hai đang định hình: nếu **vòng lặp lập trình hành vi của một agent**, thì **đồ thị lập trình cách tổ chức của nhiều agent** — có những nút nào (agent, hàm tất định, bộ định tuyến, điểm chờ người duyệt), và những đường chuyển giao nào được phép xảy ra.

Kèm theo đó là một dịch chuyển về quyền sở hữu: quan sát và quản trị **toàn đội agent** (fleet) — ai có quyền gọi công cụ gì, phiên bản nào đang chạy ở đâu — trở nên quan trọng hơn việc từng nhóm tự dựng stack giám sát riêng.

### Vì sao đây là một thế hệ chứ không phải một tính năng

Cùng một logic đã lặp lại ba lần trước đó: thế hệ mới sinh ra ở đúng chỗ mà thế hệ cũ chạm trần.

| Harness engineering giải được | Cái nó không giải được |
|---|---|
| Agent chạy trong môi trường an toàn, có công cụ, có bộ nhớ | Vẫn cần người khởi động, người đánh giá kết quả, người quyết định thử lại |
| Lỗi lặp lại bị chặn bằng ràng buộc | Không tự biết khi nào "đủ tốt để dừng" |

> 🔲 **CHỖ TRỐNG — Xác nhận hay bác bỏ.** Đến quý 1/2027, kiểm lại ba dấu hiệu để biết "loop engineering" là một thế hệ thật hay chỉ là nhãn marketing:
> 1. Có xuất hiện **framework/công cụ chuyên dụng** cho vòng lặp (không phải chỉ là blog)?
> 2. Có **benchmark** đo riêng chất lượng vòng lặp, tách khỏi chất lượng model và harness?
> 3. Có **vị trí tuyển dụng** hoặc phần mô tả công việc dùng thuật ngữ này?
>
> Kết luận: *(để trống)*

---

## 🆕 5. Cập nhật 05/2026 → 09/2026

Phần này gom các diễn biến sau ngày bài gốc xuất bản. Sắp theo mức độ ảnh hưởng tới thiết kế harness.

### 5.1 MCP đổi nền: đặc tả 2026-07-28 chuyển sang phi trạng thái

Đây là thay đổi hạ tầng lớn nhất của nửa cuối 2026. MCP chuyển từ một **giao thức hai chiều có trạng thái** sang một **giao thức request/response phi trạng thái**.

**Những gì thay đổi:**

| Thay đổi | Ý nghĩa thực tế |
|---|---|
| **Lõi phi trạng thái** — bỏ phiên ở tầng giao thức và header `Mcp-Session-Id` | Cùng một request có thể do **bất kỳ instance server nào** trả lời |
| **Định tuyến theo header** (`Mcp-Method`) | Chạy được sau một load balancer round-robin thường, không cần sticky session |
| **`tools/list` cache được** kèm `ttlMs` | Client giữ lại danh mục công cụ — bớt round-trip, đỡ token |
| **Multi Round-Trip Requests** | Hỗ trợ các tương tác cần nhiều lượt mà vẫn không cần trạng thái ở tầng giao thức |
| **Siết chặt authorization** + khung **extensions** chính thức | Phân quyền chuẩn hoá hơn; mở rộng riêng không còn phá vỡ tương thích |

**Vì sao quan trọng với harness:** trước đây một MCP server từ xa cần sticky session, kho phiên dùng chung và kiểm tra sâu ở gateway. Sau bản này, nó vận hành như **một service HTTP bình thường**. Rào cản triển khai MCP ở quy mô lớn hạ xuống đáng kể.

### 5.2 Harness trở thành đối tượng đo lường, không chỉ là ý tưởng

Một chuyển biến quan trọng: giới nghiên cứu bắt đầu **đo tác động của harness** một cách tách bạch khỏi model.

- **Harness-Bench** (05/2026) đo hiệu ứng của harness xuyên qua nhiều model trong các luồng công việc thực tế. Kết luận trung tâm: **hiệu năng agent là thuộc tính của cặp (model, hệ thống thực thi)** — công bố điểm số của riêng model là thiếu thông tin.
- Các khảo sát hệ thống (tổng hợp 110+ bài báo) đã **hình thức hoá "agent harness" thành một đối tượng kiến trúc** có thể phân loại và so sánh.
- ⚠️ **BenchGuard** và các công trình cùng hướng chỉ ra vấn đề ngược lại: chính **bộ khung chấm điểm** cũng sai — test suite từ chối cả lời giải đúng về mặt chức năng, và nhiễm dữ liệu (contamination) ngày càng chi phối điểm số công bố.

**Hệ quả cho người đọc bảng xếp hạng:** một con số benchmark không nói lên nhiều nếu không kèm mô tả harness đã dùng.

### 5.3 Harness tự tiến hoá (AHE)

⚠️ Hướng nghiên cứu nổi bật nhất, nhưng còn mới — nên đọc như một hướng đi hứa hẹn, không phải kết luận đã ổn định.

**Ý tưởng:** thay vì con người sửa harness sau mỗi lần agent mắc lỗi (cách của Hashimoto), để **một agent khác** đọc vết chạy và tự sửa harness.

**Điểm mấu chốt không nằm ở sự thông minh của agent đi sửa, mà ở khả năng quan sát.** Công trình *Agentic Harness Engineering* (04/2026) đặt ra ba trụ:

| Trụ | Nội dung |
|---|---|
| **Quan sát thành phần** | Tách harness thành **7 thành phần trực giao ở mức file**, đặt trong một workspace theo dõi bằng git → mỗi sửa đổi khoanh vùng được, kiểm tra được, hoàn tác được |
| **Quan sát kinh nghiệm** | Chưng cất vết chạy thô thành một **kho bằng chứng phân tầng** — biến hàng triệu token thành thứ agent-đi-sửa đọc nổi |
| **Quan sát quyết định** | Mỗi đề xuất sửa đi kèm **một dự đoán**; vòng lặp kế tiếp kiểm chứng dự đoán đó và **hoàn tác ở mức từng file** nếu sai |

**Kết quả báo cáo:** ⚠️ 10 vòng lặp AHE nâng pass@1 trên Terminal-Bench 2 từ **69,7% lên 77,0%**, vượt cả harness do người thiết kế (Codex-CLI, 71,9%). Harness sau khi "đóng băng" chuyển giao được sang bộ khác: trên SWE-bench-Verified đạt tổng tỉ lệ thành công cao nhất với **ít hơn 12% token** so với cấu hình khởi đầu.

**Câu quan trọng nhất của công trình này:**

> Nút thắt không phải là agent đi sửa có thông minh hay không, mà là **nó có nhìn thấy đủ rõ để sửa hay không**. Cho nó một không gian hành động rõ ràng và bằng chứng có cấu trúc, nó tự hội tụ về thiết kế tốt hơn.

⚠️ Đã có công trình phản biện (07/2026) đặt lại câu hỏi **cách đánh giá** sự tiến hoá của harness — cụ thể là làm sao phân biệt "harness tốt lên thật" với "harness khớp quá mức vào chính bộ benchmark đang dùng để đánh giá nó". Vấn đề này chưa được giải.

> 🔲 **CHỖ TRỐNG — Theo dõi AHE.** Cập nhật khi có: (a) kết quả tái lập độc lập, (b) triển khai trong sản phẩm thương mại thật, (c) kết luận về nguy cơ khớp quá mức vào benchmark.

### 5.4 Khoảng cách giữa benchmark và công việc thật

Một dữ liệu đáng để dán lên tường: ⚠️ theo **APEX-Agents** (Mercor, 01/2026), các model đạt **trên 90%** ở benchmark truyền thống chỉ đạt khoảng **24%** trên các tác vụ nghề nghiệp thực tế.

Nguyên nhân được nêu ra khá nhất quán trong các phân tích 2026:

- Benchmark hiếm khi kiểm tra hành vi của agent **sau lời gọi công cụ thứ 50 hay thứ 100** — tức là chính vùng mà độ tin cậy sụp đổ.
- Điểm số nhạy cảm với **sáu biến cùng lúc**: model, code vòng lặp, bộ công cụ, bộ khung benchmark, phương pháp chấm, và nhiễu ngẫu nhiên.
- Vì thế xuất hiện hướng nghiên cứu **"vượt qua pass@1"** — đo độ tin cậy của agent chạy dài như một đại lượng thống kê, thay vì một con số đơn lẻ.

### 5.5 Bảng tổng hợp nhanh các mốc 05→09/2026

| Thời điểm | Sự kiện | Ảnh hưởng tới harness |
|---|---|---|
| 05/2026 | Five Eyes ra hướng dẫn chung về agentic AI | Prompt injection thành rủi ro được công nhận ở cấp chính sách; buộc phòng thủ nhiều lớp |
| 05/2026 | Harness-Bench công bố | Hiệu năng agent = thuộc tính của (model + harness), không phải của model |
| 06/2026 | Thuật ngữ "loop engineering" hình thành | Mở lớp thứ tư phía trên harness |
| 07/2026 | MCP spec 2026-07-28 | Lõi phi trạng thái; MCP triển khai được như service HTTP thường |
| 07/2026 | Phản biện về cách đánh giá harness tự tiến hoá | Cảnh báo nguy cơ khớp quá mức vào benchmark |
| Suốt kỳ | Agent Skills / progressive disclosure chuẩn hoá | Skill thành thư mục `SKILL.md`; cài nhiều skill gần như không tốn ngữ cảnh |
| Suốt kỳ | Thực thi bền thành yêu cầu mặc định | Checkpoint, hibernate/wake, ngân sách có phê duyệt |

> 🔲 **CHỖ TRỐNG — Mốc mới.** Thêm dòng vào bảng trên theo định dạng: *thời điểm · sự kiện · ảnh hưởng tới harness*. Chỉ thêm khi sự kiện **đổi cách thiết kế**, không thêm mọi thông báo sản phẩm.

---

## Tổng kết một câu cho mỗi thế hệ

| Thế hệ | Giải được gì | Vì sao chưa đủ |
|---|---|---|
| **Prompt Engineering** | Khai thác tri thức đã nén sẵn trong model qua cách diễn đạt | Không vượt được knowledge cutoff và xu hướng bịa đặt nội tại |
| **Context Engineering** | Cho model **nhìn thấy** đúng thông tin, đúng lúc | Làm agent thông minh hơn nhưng **không đáng tin cậy hơn** |
| **Harness Engineering** | Biến trí tuệ thành thứ **vận hành ổn định trong production** | Vẫn cần người khởi động, đánh giá và quyết định dừng |
| 🆕 **Loop / Graph Engineering** | Thiết kế **hệ điều khiển** tự giao việc, tự kiểm, tự dừng | ⚠️ *(đang là biên giới hiện tại — chưa đủ dữ liệu để biết trần của nó ở đâu)* |

---

## 🔲 Nhật ký quan sát — khung để điền về sau

Phần này cố tình để trống. Mục đích: mỗi lần có quan sát mới, thay vì viết lại cả tài liệu thì thêm một mục vào đây; định kỳ mới gộp ngược lên các mục chính.

### Mẫu một mục ghi

```markdown
### [YYYY-MM-DD] Tiêu đề ngắn

**Loại:** đặc tả kỹ thuật / kết quả nghiên cứu / báo cáo vận hành / sự cố / thuật ngữ mới
**Nguồn:** (URL, tên tác giả, ngày)
**Số nguồn độc lập:** 1 / 2 / ≥3
**Mức tin cậy:** ⚠️ một nguồn · ✓ đã đối chiếu

**Quan sát được gì:**
—

**Đổi kết luận nào trong tài liệu này:**
—

**Mục cần sửa:** §x.y

**Việc cần làm tiếp:**
- [ ] Tìm nguồn đối chiếu thứ hai
- [ ] Kiểm bằng dữ liệu của chính mình
```

### Các mục đã ghi

*(chưa có — thêm mục mới lên đầu danh sách)*

---

### 🔲 Câu hỏi mở đang theo dõi

Danh sách này là "hàng chờ" — mỗi câu hỏi có chỗ để điền câu trả lời khi đủ dữ liệu.

| # | Câu hỏi | Điều gì sẽ trả lời được nó | Trạng thái |
|---|---|---|---|
| 1 | Bộ nhớ dạng Markdown phẳng hỏng ở ngưỡng nào? | Một hệ thống chạy >100 phiên với cùng một `MEMORY.md` | 🔲 chưa có dữ liệu |
| 2 | Harness tự tiến hoá có khớp quá mức vào benchmark không? | Kết quả chuyển giao sang bộ tác vụ hoàn toàn mới, do bên thứ ba chạy | 🔲 chưa có dữ liệu |
| 3 | Progressive disclosure một mình có đủ cho ngữ cảnh dài? | Nghiên cứu so sánh với retrieval chủ động | 🔲 đang tranh luận |
| 4 | MCP phi trạng thái có làm mất tính năng nào không? | Trải nghiệm di trú của các server có trạng thái sau 6–12 tháng | 🔲 quá sớm |
| 5 | "Loop engineering" là thế hệ thật hay nhãn marketing? | Ba dấu hiệu ở §4 | 🔲 kiểm lại Q1/2027 |
| 6 | Chi phí thực của harness so với chi phí model? | Bóc tách hoá đơn: token vs hạ tầng vs người duyệt | 🔲 chưa ai công bố |
| 7 | *(để trống — thêm câu hỏi của bạn)* | | |

---

## Tài liệu tham khảo

### Nguồn của bài gốc (giữ nguyên)

1. Thang Chung (2026, April 18). *Build an Agent Harness with Microsoft Agent Framework and GitHub Copilot SDK.* Global Azure 2026, DevCafe Vietnam.
2. Bits Bytes NN. (2026, April 5). *Evolution of AI Agentic Patterns.* https://bits-bytes-nn.github.io/insights/agentic-ai/2026/04/05/evolution-of-ai-agentic-patterns-en.html
3. Anthropic. (2025, October 22). *Effective Context Engineering for AI Agents.* https://www.anthropic.com/engineering/effective-context-engineering
4. LumaDock. (2026, January 23). *How to set up OpenClaw across WhatsApp, Telegram, Discord, Slack.* https://lumadock.com/tutorials/openclaw-multi-channel-setup
5. OpenClaw. (2026). *openclaw npm package.* https://www.npmjs.com/package/openclaw
6. The AI Journal. (2026, April 6). *A simplistic understanding of OpenClaw Arch.* https://aijourn.com/a-simplistic-understanding-of-openclaw-arch-to-help-you-build-your-own/
7. Palma.ai. (2026, April 1). *Claude Code's Source Leak: What 512K Lines of Code Reveal About MCP.* https://palma.ai/blog/claude-code-source-leak-what-it-means-for-mcp
8. Iusztin, P. (2026, March 31). *Agentic Harness Engineering.* Decoding AI. https://www.decodingai.com/p/agentic-harness-engineering
9. Nebius. (2026, March 5). *OpenClaw security: architecture and hardening guide.* https://nebius.com/blog/posts/openclaw-security
10. Kubesimplify Blog. (2026, April 1). *What Claude Code's Leaked Source Teaches About AI Agents.* https://blog.kubesimplify.com/claude-code-leak-what-the-source-actually-teaches
11. Bara, M. (2026, April 1). *What Claude Code's Source Leak Actually Reveals.* https://medium.com/@marc.bara.iniesta/what-claude-codes-source-leak-actually-reveals-e571188ecb81
12. Anthropic. (2026, March 25). *Effective Harnesses for Long-Running Agents.* https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents
13. Hegde, V. (2026, April 1). *The Great Claude Code Leak of 2026.* DEV Community.
14. Yao, S., et al. (2022, October). *ReAct: Synergizing Reasoning and Acting in Language Models.* Princeton University / Google. https://arxiv.org/abs/2210.03629

### 🆕 Nguồn bổ sung (05/2026 → 09/2026)

**Giao thức**

15. Model Context Protocol. (2026, July 28). *The 2026-07-28 Specification.* https://blog.modelcontextprotocol.io/posts/2026-07-28/
16. Model Context Protocol. (2026). *Key Changes — 2026-07-28 changelog.* https://modelcontextprotocol.io/specification/2026-07-28/changelog
17. Model Context Protocol. (2026). *The New MCP Roadmap.* https://blog.modelcontextprotocol.io/posts/mcp-roadmap/

**Harness: đo lường và tự tiến hoá**

18. *Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses.* (2026, April). arXiv:2604.25850. https://arxiv.org/abs/2604.25850 — kèm mã nguồn: https://github.com/china-qijizhifeng/agentic-harness-engineering
19. *Harness-Bench: Measuring Harness Effects across Models in Realistic Agent Workflows.* (2026, May). arXiv:2605.27922. https://arxiv.org/html/2605.27922v1
20. *Rethinking the Evaluation of Harness Evolution for Agents.* (2026, July). arXiv:2607.12227. https://arxiv.org/html/2607.12227v2
21. *BenchGuard: Who Guards the Benchmarks? Automated Auditing of LLM Agent Benchmarks.* (2026, April). arXiv:2604.24955.
22. *Towards a Science of AI Agent Reliability.* (2026, February). arXiv:2602.16666.
23. *Beyond pass@1: A Reliability Science Framework for Long-Horizon LLM Agents.* (2026, March). arXiv:2603.29231.
24. Schmid, P. (2026). *The importance of Agent Harness in 2026.* https://www.philschmid.de/agent-harness-2026
25. ai-boost. (2026). *awesome-harness-engineering.* https://github.com/ai-boost/awesome-harness-engineering

**Agent Skills & progressive disclosure**

26. Anthropic. (2026). *Agent Skills — Overview.* Claude Platform Docs. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
27. Microsoft. (2026). *Agent Skills.* Microsoft Learn. https://learn.microsoft.com/en-us/agent-framework/agents/skills
28. *Is Progressive Disclosure All You Need for Long-Context Agents?* (2026, July). arXiv:2607.17598. https://arxiv.org/html/2607.17598v1
29. *Agent Skills for Large Language Models: Architecture, Acquisition, Security, and the Path Forward.* (2026). arXiv:2602.12430.
30. SwirlAI Newsletter. *Agent Skills: Progressive Disclosure as a System Design Pattern.* https://www.newsletter.swirlai.com/p/agent-skills-progressive-disclosure

**An ninh & sandbox**

31. NVIDIA. (2026). *Practical Security Guidance for Sandboxing Agentic Workflows and Managing Execution Risk.* https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk/
32. Northflank. (2026). *How to sandbox AI agents in 2026: MicroVMs, gVisor & isolation strategies.* https://northflank.com/blog/how-to-sandbox-ai-agents
33. Sysdig. (2026). *The Comprehensive Guide to Prompt Injection Attacks in 2026.* https://www.sysdig.com/learn-cloud-native/prompt-injection
34. *Towards Secure Agent Skills: Architecture, Threat Taxonomy, and Security Analysis.* (2026, April). arXiv:2604.02837.

**Vận hành & orchestration**

35. Lanham, M. (2026). *Multi-Agent in Production in 2026: What Actually Survived.* https://medium.com/@Micheal-Lanham/multi-agent-in-production-in-2026-what-actually-survived-f86de8bb1cd1
36. Google Developers Blog. (2026). *Architecting efficient context-aware multi-agent framework for production.* https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production/
37. Redis. (2026). *AI agent orchestration for production systems.* https://redis.io/blog/ai-agent-orchestration/

**Loop engineering**

38. IBM. (2026). *What Is Loop Engineering?* https://www.ibm.com/think/topics/loop-engineering
39. Masood, A. (2026). *Loop Engineering: A Guide for Engineers and Practitioners.* https://medium.com/@adnanmasood/loop-engineering-a-guide-for-engineers-and-practitioners-893bb65ea943
40. Tosea.ai. (2026). *What Is Loop Engineering? A Complete Guide from Prompt to Harness Engineering.* https://tosea.ai/blog/loop-engineering-ai-agents-complete-guide-2026

**Benchmark & khoảng cách thực tế**

41. Simmering, P. (2026). *The Reliability Gap: Agent Benchmarks for Enterprise.* https://simmering.dev/blog/agent-benchmarks/
42. Sourcegraph. (2026). *Context Engineering: A Practical Guide for AI Agents.* https://sourcegraph.com/blog/context-engineering

> 🔲 **CHỖ TRỐNG — Nguồn mới.** Thêm vào đúng nhóm ở trên. Với mỗi nguồn mới, ghi kèm: nguồn này **xác nhận** hay **phản bác** điều gì trong tài liệu — nếu không trả lời được câu đó thì chưa cần thêm.

---

## Bảng thuật ngữ

### Thuật ngữ cốt lõi

| Thuật ngữ | Nghĩa |
|---|---|
| **harness** | Bộ khung vận hành bao quanh model — toàn bộ phần *không phải là model* (nghĩa gốc: bộ yên cương) |
| **context window** | Cửa sổ ngữ cảnh — lượng token model đọc được trong một lần gọi |
| **knowledge cutoff** | Mốc cắt tri thức — thời điểm dữ liệu huấn luyện dừng lại |
| **hallucination** | Model bịa ra thông tin nghe hợp lý nhưng sai |
| **compaction** | Nén ngữ cảnh theo cách còn phục hồi được (giữ tham chiếu thay vì nội dung) |
| **summarization** | Tóm tắt bằng LLM — nén mạnh nhưng mất thông tin không hồi phục |
| **lossy** | Mất thông tin, không đảo ngược được |
| **spawn** | Sinh ra một tiến trình/agent con |
| **sandbox** | Môi trường cô lập để chạy code không đáng tin |
| **prompt injection** | Tấn công bằng cách chèn chỉ dẫn độc hại vào input mà model sẽ đọc |
| **indirect prompt injection** | Biến thể phổ biến hơn: chỉ dẫn độc hại nằm trong nội dung agent tự đi đọc (trang web, email, file), không do người dùng gõ vào |
| **permission gating** | Cổng phân quyền — chặn/cho phép từng hành động |
| **default-deny** | Mặc định từ chối, chỉ mở khi được cấp phép rõ ràng |
| **stateless** | Phi trạng thái — không nhớ gì giữa các lần gọi |
| **MCP** | Model Context Protocol — chuẩn kết nối công cụ cho agent |
| **RAG** | Retrieval-Augmented Generation — sinh văn bản có kèm truy hồi tài liệu |
| **LSP** | Language Server Protocol — giao thức máy chủ ngôn ngữ cho IDE |

### 🆕 Thuật ngữ bổ sung 2026

| Thuật ngữ | Nghĩa |
|---|---|
| **loop engineering** | Kỹ thuật thiết kế vòng lặp — xây hệ điều khiển tự ra chỉ dẫn, tự kiểm chứng, tự dừng, thay cho việc người gõ lệnh từng lượt |
| **durable execution** | Thực thi bền — workflow chắc chắn đi tới trạng thái cuối (thành công hoặc lỗi đã xử lý) bất kể tiến trình bị gián đoạn |
| **checkpointing** | Lưu ảnh chụp trạng thái sau mỗi bước để chạy tiếp từ đó, thay vì làm lại từ đầu |
| **hibernate & wake** | Cho workflow ngủ đông giữa các chặng dài rồi đánh thức, thay vì giữ tiến trình sống suốt |
| **trajectory** | Vết chạy — toàn bộ chuỗi bước, lời gọi công cụ và kết quả của một phiên agent; nguyên liệu chính để chẩn đoán và cải tiến harness |
| **observability** | Khả năng quan sát — mức độ bạn suy ra được chuyện gì đang xảy ra bên trong hệ thống chỉ từ những gì nó phát ra bên ngoài |
| **progressive disclosure** | Nạp dần theo nhu cầu — chỉ giữ tên + mô tả trong ngữ cảnh, đọc phần thân khi thật sự cần |
| **SKILL.md** | Quy ước đóng gói một skill thành thư mục: file mô tả + chỉ dẫn, kèm tài nguyên nạp theo yêu cầu |
| **tool offloading** | Đưa schema công cụ ra khỏi cửa sổ ngữ cảnh, chỉ để lại ba công cụ Search / Load / Execute |
| **pass@1** | Tỉ lệ giải đúng ngay lần thử đầu tiên; bị phê phán vì không phản ánh độ tin cậy của agent chạy dài |
| **contamination** | Nhiễm dữ liệu — lời giải của benchmark đã lọt vào dữ liệu huấn luyện, làm điểm số bị thổi phồng |
| **microVM** | Máy ảo siêu nhẹ (Firecracker và tương tự) — cô lập ở tầng ảo hoá, an toàn hơn container |
| **gVisor** | Nhân người dùng chặn syscall — cô lập nhẹ hơn microVM, khởi động nhanh hơn |
| **fleet** | Toàn đội agent đang chạy trong một tổ chức, nhìn như một đối tượng quản trị chung |
| **human-in-the-loop** | Có người ở trong vòng lặp — điểm dừng bắt buộc chờ người duyệt trước khi agent đi tiếp |

> 🔲 **CHỖ TRỐNG — Thuật ngữ mới.** Trước khi thêm, thử ba câu hỏi: (1) nó có tên tiếng Việt gọn và không gây hiểu nhầm không? (2) nó có thật sự khác các mục đã có, hay chỉ là cách gọi khác? (3) đã có ít nhất hai nguồn độc lập dùng nó chưa?

---

*Tài liệu này được thiết kế để bổ sung dần. Khi thêm nội dung, giữ ba nguyên tắc: đánh dấu 🆕 cho phần mới, ⚠️ cho phần một nguồn, và luôn ghi rõ nguồn mới **xác nhận** hay **phản bác** điều gì đã viết.*
