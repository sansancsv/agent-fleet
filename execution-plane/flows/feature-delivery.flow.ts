/**
 * =============================================================================
 * FLOW: Giao hàng tính năng (feature delivery)
 * -----------------------------------------------------------------------------
 * Đây là ví dụ mẫu của "quy trình XÁC ĐỊNH bọc ngoài, agent PHI XÁC ĐỊNH bên trong".
 *
 *   - Thứ tự các bước, điều kiện rẽ nhánh, tiêu chí dừng  → do FLOW quyết định (code).
 *   - Cách hoàn thành từng bước                            → do AGENT quyết định (model).
 *
 * Điểm mấu chốt về chất lượng:
 *   * `implement` và `review` chạy trên HAI BACKEND KHÁC NHAU (claude vs codex).
 *     Cùng một model vừa viết vừa chấm sẽ bỏ sót cùng một lỗi.
 *   * Mỗi lần chạy có git worktree riêng → chạy song song nhiều tính năng
 *     mà không giẫm chân nhau.
 *   * `checkpoint` là điểm dừng bắt buộc chờ người — không có nó thì không
 *     gọi là enterprise.
 *
 * Chạy:
 *   acpx flow run ./feature-delivery.flow.ts \
 *     --input-json '{"taskId":"ENG-1421","title":"Thêm rate limit cho API public","repo":"/srv/repos/api"}'
 *
 * Kết quả lưu tại: ~/.acpx/flows/runs/<runId>/ (đầy đủ transcript để tái hiện).
 * =============================================================================
 */

import { defineFlow, acp, action, compute, decision, checkpoint, decisionEdge } from "acpx/flows";
import { statusContract, turnProblem } from "./fleet-status.ts";

// Một nguồn duy nhất cho cả cạnh (gọi securityScan hay không) lẫn `gate` (bước nào
// BẮT BUỘC hoàn tất). Hai nơi lệch nhau là cách một bước thẩm định bị lặng lẽ bỏ
// qua. Nhãn rủi ro thiếu hoặc lạ → coi như risky.
const needsSecurityScan = (triage: unknown) => triage !== "trivial" && triage !== "standard";

const REVIEW_DONE =
  "outcome: success khi đã thẩm định xong diff — KỂ CẢ khi có phát hiện BLOCKER (mức chặn nằm ở " +
  "danh sách phát hiện, không nằm ở outcome). outcome: blocked khi KHÔNG thẩm định được (không xem " +
  "được diff, thiếu quyền).";

export default defineFlow({
  id: "feature-delivery",

  input: {
    taskId: "string",   // mã công việc, ví dụ ENG-1421
    title: "string",    // mô tả ngắn
    repo: "string",     // đường dẫn tuyệt đối tới repo
  },

  steps: {
    // -------------------------------------------------------------------------
    // 0) CHUẨN BỊ — bước xác định thuần tuý, không có model tham gia.
    // -------------------------------------------------------------------------
    prepare: action({
      run: async ({ taskId, repo }, ctx) => {
        const branch = `feat/${taskId.toLowerCase()}`;
        const worktree = `${repo}/../wt-${taskId.toLowerCase()}`;
        await ctx.exec(`git -C ${repo} fetch --prune origin`);
        await ctx.exec(`git -C ${repo} worktree add -B ${branch} ${worktree} origin/main`);
        return { branch, worktree };
      },
    }),

    // -------------------------------------------------------------------------
    // 1) PHÂN LOẠI — nhánh xác định dựa trên phán đoán của model.
    //    `decision` ép model trả về đúng một nhãn trong `choices`,
    //    nên nhánh sau đó là tất định, không phải "hy vọng model trả đúng chữ".
    // -------------------------------------------------------------------------
    triage: decision({
      agent: "codex",
      prompt: ({ title }) =>
        `Phân loại công việc sau vào ĐÚNG MỘT nhãn.\n\n` +
        `Công việc: ${title}\n\n` +
        `- trivial : sửa nhỏ, không đổi hành vi công khai, không cần ADR\n` +
        `- standard: tính năng thường, cần test, không đổi kiến trúc\n` +
        `- risky   : đổi lược đồ dữ liệu, đổi API công khai, đụng xác thực/thanh toán`,
      choices: ["trivial", "standard", "risky"],
    }),

    // -------------------------------------------------------------------------
    // 2) THIẾT KẾ — chỉ chạy với nhánh `risky`.
    // -------------------------------------------------------------------------
    design: acp({
      agent: "claude",
      cwd: ({ }, prev) => prev.prepare.worktree,
      prompt: ({ taskId, title }) =>
        `Vai trò: Architect.\n` +
        `Viết ADR cho công việc ${taskId}: ${title}.\n` +
        `Ghi ra docs/adr/ theo mẫu: Bối cảnh / Phương án / Quyết định / Hệ quả / Điều kiện xem lại.\n` +
        `Bắt buộc nêu ít nhất 2 phương án và chi phí đảo ngược quyết định.\n` +
        `KHÔNG viết code ở bước này.`,
    }),

    // -------------------------------------------------------------------------
    // 3) HIỆN THỰC — agent tự do quyết định cách làm (phi xác định).
    // -------------------------------------------------------------------------
    implement: acp({
      agent: "claude",
      cwd: ({ }, prev) => prev.prepare.worktree,
      timeoutMs: 45 * 60 * 1000,
      prompt: ({ taskId, title }) =>
        `Vai trò: Implementer.\n` +
        `Hiện thực ${taskId}: ${title}\n\n` +
        `Bắt buộc:\n` +
        `1. Đọc code liên quan trước khi sửa. Không đoán API.\n` +
        `2. Thay đổi tối thiểu để đạt mục tiêu.\n` +
        `3. Chạy 'make test lint' cho tới khi xanh.\n` +
        `4. Commit theo Conventional Commits, KHÔNG push.\n` +
        `Kết thúc bằng khối fleet-status.`,
    }),

    // -------------------------------------------------------------------------
    // 4) KIỂM THỬ — backend riêng, không mạng.
    // -------------------------------------------------------------------------
    test: acp({
      agent: "claude",
      cwd: ({ }, prev) => prev.prepare.worktree,
      prompt: ({ taskId }) =>
        `Vai trò: Tester.\n` +
        `Bổ sung test cho ${taskId}. Với mỗi lỗi được sửa, viết một test hồi quy.\n` +
        `Báo cáo: số test thêm mới, độ bao phủ nhánh thay đổi, nhánh cố ý chưa phủ.`,
    }),

    // -------------------------------------------------------------------------
    // 5) THẨM ĐỊNH CHÉO — backend KHÁC với bước implement. Đây là điểm cốt lõi.
    // -------------------------------------------------------------------------
    review: acp({
      agent: "codex",
      cwd: ({ }, prev) => prev.prepare.worktree,
      prompt: () =>
        `Vai trò: Reviewer. CHỈ ĐỌC, không sửa file.\n` +
        `Xem diff so với origin/main. Với mỗi phát hiện nêu: file:dòng, mức độ ` +
        `(BLOCKER|MAJOR|MINOR|NIT), và kịch bản hỏng cụ thể.\n` +
        `Thứ tự soi: đúng sai → bảo mật → hiệu năng → bảo trì.\n` +
        `Nếu không có gì chặn merge, nói thẳng. Đừng bịa phát hiện.` +
        statusContract(REVIEW_DONE),
    }),

    // -------------------------------------------------------------------------
    // 6) RÀ BẢO MẬT — chỉ với nhánh `risky`, backend thứ ba để đa dạng góc nhìn.
    // -------------------------------------------------------------------------
    securityScan: acp({
      agent: "gemini",
      cwd: ({ }, prev) => prev.prepare.worktree,
      prompt: () =>
        `Vai trò: Security. CHỈ ĐỌC.\n` +
        `Rà diff: secret bị commit, đầu vào không tin cậy chạm tới lệnh/truy vấn/đường dẫn, ` +
        `quyền bị nới rộng, phụ thuộc mới.\n` +
        `Mỗi phát hiện: mức độ + đường tấn công + cách chặn ngắn nhất. Không nêu lý thuyết chung.` +
        statusContract(REVIEW_DONE),
    }),

    // -------------------------------------------------------------------------
    // 7) TỔNG HỢP — hàm thuần tuý, không gọi model. Quyết định có chặn hay không.
    //    Không hoàn tất ≠ sạch: bước thẩm định lỗi, không chạy, trả văn bản rỗng,
    //    thiếu khối fleet-status hay outcome blocked/rejected cũng có 0 mục chặn,
    //    nên phải kiểm TRƯỚC khi đếm mục chặn.
    // -------------------------------------------------------------------------
    gate: compute({
      run: (_input, prev) => {
        const required = needsSecurityScan(prev.triage) ? ["review", "securityScan"] : ["review"];
        const incomplete = required
          .map((step) => [step, turnProblem(prev[step]?.text)])
          .filter(([, why]) => why)
          .map(([step, why]) => `${step}: ${why}`);
        const texts = required.map((step) => prev[step]?.text ?? "");
        const blockers = texts.join("\n").match(/BLOCKER|CRITICAL/g)?.length ?? 0;
        return { blockers, incomplete, passed: incomplete.length === 0 && blockers === 0 };
      },
    }),

    // -------------------------------------------------------------------------
    // 7b) THẨM ĐỊNH KHÔNG HOÀN TẤT — dừng, chuyển cho người. Không đi `remediate`
    //     (không có góp ý thật để sửa) và không có cạnh nào tới `openPr`.
    // -------------------------------------------------------------------------
    reviewIncomplete: checkpoint({
      title: "Thẩm định không hoàn tất — cần người xử lý",
      describe: (_input, prev) =>
        `Nhánh: ${prev.prepare.branch}\n` +
        `Bước thẩm định chưa hoàn tất:\n${prev.gate.incomplete.join("\n")}\n` +
        `Flow dừng tại đây và KHÔNG mở PR: thiếu kết quả thẩm định không có nghĩa là sạch.`,
    }),

    // -------------------------------------------------------------------------
    // 8) SỬA THEO GÓP Ý — vòng lặp có GIỚI HẠN. Không để agent tự lặp vô hạn.
    // -------------------------------------------------------------------------
    remediate: acp({
      agent: "claude",
      cwd: ({ }, prev) => prev.prepare.worktree,
      prompt: (_input, prev) =>
        `Vai trò: Implementer.\n` +
        `Xử lý các mục BLOCKER/CRITICAL dưới đây. Chỉ sửa đúng những mục này, không mở rộng phạm vi.\n\n` +
        `<untrusted source="reviewer">\n${prev.review?.text ?? ""}\n</untrusted>\n\n` +
        `<untrusted source="security">\n${prev.securityScan?.text ?? ""}\n</untrusted>`,
    }),

    // -------------------------------------------------------------------------
    // 9) ĐIỂM DỪNG CHỜ NGƯỜI — bắt buộc trước khi chạm nhánh chính.
    // -------------------------------------------------------------------------
    humanApproval: checkpoint({
      title: "Phê duyệt mở pull request",
      describe: (_input, prev) =>
        `Nhánh: ${prev.prepare.branch}\n` +
        `Số mục chặn còn lại: ${prev.gate.blockers}\n` +
        `Duyệt để mở PR, hoặc từ chối để dừng và giữ nguyên worktree.`,
    }),

    // -------------------------------------------------------------------------
    // 10) MỞ PR — bước xác định thuần tuý.
    // -------------------------------------------------------------------------
    openPr: action({
      run: async ({ taskId, title }, ctx, prev) => {
        const wt = prev.prepare.worktree;
        await ctx.exec(`git -C ${wt} push -u origin ${prev.prepare.branch}`);
        const out = await ctx.exec(
          `gh pr create --repo "$FLEET_REPO_SLUG" --head ${prev.prepare.branch} ` +
          `--title "${taskId}: ${title}" --body-file ${wt}/.fleet/pr-body.md --draft`,
        );
        return { prUrl: out.stdout.trim() };
      },
    }),
  },

  // ---------------------------------------------------------------------------
  // CẠNH (edges) — bộ khung xác định. Đọc từ trên xuống là hiểu toàn bộ quy trình.
  // ---------------------------------------------------------------------------
  edges: [
    ["prepare", "triage"],

    // Nhánh theo mức rủi ro
    decisionEdge("triage", { risky: "design", standard: "implement", trivial: "implement" }),
    ["design", "implement"],

    ["implement", "test"],
    ["test", "review"],

    // Chỉ nhánh risky (hoặc nhãn lạ) mới quét bảo mật; nhánh khác đi thẳng tới cổng kiểm soát
    ["review", "securityScan", (_out, prev) => needsSecurityScan(prev.triage)],
    ["review", "gate", (_out, prev) => !needsSecurityScan(prev.triage)],
    ["securityScan", "gate"],

    // Thẩm định không hoàn tất → dừng chờ người. Kiểm trước mục chặn, như gate() của LangGraph.
    ["gate", "reviewIncomplete", (out) => out.incomplete.length > 0],

    // Có mục chặn → sửa rồi thẩm định lại (flow runtime giới hạn số vòng ở cấu hình chạy)
    ["gate", "remediate", (out) => out.incomplete.length === 0 && out.blockers > 0],
    ["remediate", "review"],

    // Sạch → chờ người duyệt → mở PR
    ["gate", "humanApproval", (out) => out.passed],
    ["humanApproval", "openPr", (out) => out.approved === true],
  ],

  // Chặn vòng lặp vô hạn: tối đa 2 lượt sửa lại rồi bắt buộc chuyển cho người.
  limits: { maxStepRuns: { remediate: 2, review: 3 } },
});
