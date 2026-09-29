/**
 * =============================================================================
 * FLOW: Yêu cầu phòng ban (department request) — flow ĐA DỤNG
 * -----------------------------------------------------------------------------
 * Đây là khuôn mẫu để mở rộng fleet sang các phòng ban NGOÀI kỹ thuật
 * (marketing, tài chính, pháp chế, nhân sự, chăm sóc khách hàng...).
 *
 * Ý tưởng: cấu trúc quy trình của mọi phòng ban thực ra giống nhau —
 *      tiếp nhận → phân loại → soạn thảo → thẩm định chéo → duyệt → phát hành
 * Cái khác nhau chỉ là: DỮ LIỆU NÀO được đọc, AI duyệt, và ĐẦU RA đi đâu.
 * Những thứ đó nằm trong `profiles/<phòng-ban>.yaml`, không nằm trong code này.
 *
 * Chạy:
 *   acpx flow run ./dept-request.flow.ts \
 *     --input-json '{"profile":"marketing","request":"Viết email ra mắt tính năng X","requester":"an.nguyen"}'
 * =============================================================================
 */

import { defineFlow, acp, action, compute, decision, checkpoint, decisionEdge } from "acpx/flows";
import { statusContract, turnProblem } from "./fleet-status.ts";

export default defineFlow({
  id: "dept-request",

  input: {
    profile: "string",    // tên hồ sơ phòng ban trong profiles/
    request: "string",    // yêu cầu bằng ngôn ngữ tự nhiên
    requester: "string",  // ai yêu cầu — dùng để xác định quyền và người duyệt
  },

  steps: {
    // 1) Nạp hồ sơ phòng ban: model nào, tool nào, ai duyệt, đầu ra đi đâu.
    loadProfile: action({
      run: async ({ profile }, ctx) => {
        const out = await ctx.exec(`yq -o=json '.' /fleet/profiles/${profile}.yaml`);
        return JSON.parse(out.stdout);
      },
    }),

    // 2) Kiểm tra quyền TRƯỚC khi tiêu tốn token — bước xác định, không dùng model.
    authorize: compute({
      run: (input, prev) => {
        const allowed: string[] = prev.loadProfile.requesters ?? [];
        const ok = allowed.includes(input.requester) || allowed.includes("*");
        return { ok, reason: ok ? "" : `${input.requester} không nằm trong danh sách của ${input.profile}` };
      },
    }),

    // 3) Phân loại yêu cầu theo phân loại riêng của phòng ban.
    classify: decision({
      agent: ({ }, prev) => prev.loadProfile.agents.classifier,
      prompt: ({ request }, prev) =>
        `Phân loại yêu cầu vào ĐÚNG MỘT nhãn: ${prev.loadProfile.categories.join(" | ")}\n\n` +
        `<untrusted source="requester">\n${request}\n</untrusted>`,
      choices: ({ }, prev) => prev.loadProfile.categories,
    }),

    // 4) Soạn thảo — bước phi xác định. Agent tự quyết cách làm.
    draft: acp({
      agent: ({ }, prev) => prev.loadProfile.agents.drafter,
      prompt: ({ request }, prev) =>
        `${prev.loadProfile.systemPrompt}\n\n` +
        `Loại yêu cầu: ${prev.classify}\n` +
        `Nguồn dữ liệu được phép dùng: ${prev.loadProfile.dataSources.join(", ")}\n\n` +
        `<untrusted source="requester">\n${request}\n</untrusted>`,
    }),

    // 5) Thẩm định chéo — backend khác với bước soạn thảo.
    review: acp({
      agent: ({ }, prev) => prev.loadProfile.agents.reviewer,
      prompt: (_i, prev) =>
        `Thẩm định bản nháp theo tiêu chí của phòng ${prev.loadProfile.name}:\n` +
        `${prev.loadProfile.reviewCriteria.map((c: string, i: number) => `${i + 1}. ${c}`).join("\n")}\n\n` +
        `Nêu mức độ cho mỗi vấn đề: BLOCKER | MAJOR | MINOR.\n\n` +
        `Bản nháp:\n${prev.draft.text}` +
        statusContract(
          "outcome: success khi đã thẩm định xong bản nháp — KỂ CẢ khi có vấn đề BLOCKER (mức chặn nằm " +
          "ở danh sách vấn đề, không nằm ở outcome). outcome: blocked khi KHÔNG thẩm định được.",
        ),
    }),

    // Không hoàn tất ≠ sạch: lượt thẩm định lỗi, rỗng hay thiếu khối fleet-status
    // cũng có 0 BLOCKER, nên phải kiểm TRƯỚC khi đếm.
    gate: compute({
      run: (_i, prev) => {
        const incomplete = turnProblem(prev.review?.text);
        const blockers = ((prev.review?.text ?? "").match(/BLOCKER/g) ?? []).length;
        return { blockers, incomplete, passed: !incomplete && blockers === 0 };
      },
    }),

    // Thẩm định không hoàn tất → dừng, chuyển cho người. Không đi `revise` (không có
    // góp ý thật để sửa) và không có cạnh nào tới `publish`.
    reviewIncomplete: checkpoint({
      title: "Thẩm định không hoàn tất — cần người xử lý",
      approvers: (_i, prev) => prev.loadProfile.approvers,
      describe: (_i, prev) =>
        `Lượt thẩm định chưa hoàn tất: ${prev.gate.incomplete}\n` +
        `Flow dừng tại đây và KHÔNG phát hành: thiếu kết quả thẩm định không có nghĩa là đạt.`,
    }),

    revise: acp({
      agent: ({ }, prev) => prev.loadProfile.agents.drafter,
      prompt: (_i, prev) =>
        `Sửa bản nháp theo các mục BLOCKER dưới đây. Không mở rộng phạm vi.\n\n` +
        `Góp ý:\n${prev.review.text}\n\nBản nháp hiện tại:\n${prev.draft.text}`,
    }),

    // 6) Người duyệt — do hồ sơ phòng ban quy định, không hard-code.
    approve: checkpoint({
      title: "Phê duyệt của phòng ban",
      approvers: (_i, prev) => prev.loadProfile.approvers,
      describe: (_i, prev) => prev.draft.text.slice(0, 4000),
    }),

    // 7) Phát hành tới đích của phòng ban (Notion, Google Drive, email, CMS...).
    publish: action({
      run: async (_i, ctx, prev) => {
        const dest = prev.loadProfile.output;
        // Cú pháp mcporter (đã đối chiếu 0.13.8):
        //   mcporter call <server>.<tool> key=value key=@path --output json
        // Nội dung dài đi qua tệp (key=@path) để không phải thoát chuỗi trong shell;
        // KHÔNG có cờ --arg.
        const bodyPath = `/tmp/fleet-publish-${Date.now()}.txt`;
        await ctx.writeFile(bodyPath, prev.draft.text);
        const fixed = Object.entries(dest.params ?? {})
          .map(([k, v]) => `${k}=${JSON.stringify(String(v))}`)
          .join(" ");
        const out = await ctx.exec(
          `mcporter call ${dest.server}.${dest.tool} ${fixed} ${dest.contentKey ?? "content"}=@${bodyPath} --output json`,
        );
        return { published: true, result: out.stdout };
      },
    }),

    rejected: action({
      run: async (_i, ctx, prev) => {
        await ctx.exec(`echo "TỪ CHỐI: ${prev.authorize.reason}" >&2`);
        return { published: false };
      },
    }),
  },

  edges: [
    ["loadProfile", "authorize"],
    ["authorize", "classify", (out) => out.ok],
    ["authorize", "rejected", (out) => !out.ok],
    ["classify", "draft"],
    ["draft", "review"],
    ["review", "gate"],
    ["gate", "reviewIncomplete", (out) => Boolean(out.incomplete)],
    ["gate", "revise", (out) => !out.incomplete && out.blockers > 0],
    ["revise", "review"],
    ["gate", "approve", (out) => out.passed],
    ["approve", "publish", (out) => out.approved === true],
  ],

  limits: { maxStepRuns: { revise: 2, review: 3 } },
});
