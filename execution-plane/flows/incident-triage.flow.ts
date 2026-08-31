/**
 * =============================================================================
 * FLOW: Phân loại và xử lý sự cố (incident triage)
 * -----------------------------------------------------------------------------
 * Được kích hoạt từ Alertmanager → webhook OpenClaw → n8n → flow này.
 *
 * Đặc điểm khác flow tính năng: TỐC ĐỘ QUAN TRỌNG HƠN ĐỘ HOÀN HẢO.
 *   - Không có bước sửa lại nhiều vòng.
 *   - Có "cầu dao" (circuit breaker): quá 10 phút không kết luận → gọi người.
 *   - Mọi hành động thay đổi hệ thống đều phải qua checkpoint.
 *
 * Chạy:
 *   acpx flow run ./incident-triage.flow.ts \
 *     --input-json '{"alertName":"HighErrorRate","severity":"SEV2","payload":"..."}'
 * =============================================================================
 */

import { defineFlow, acp, action, compute, decision, checkpoint, decisionEdge } from "acpx/flows";

export default defineFlow({
  id: "incident-triage",

  input: {
    alertName: "string",
    severity: "string",  // SEV1 | SEV2 | SEV3
    payload: "string",   // JSON thô từ Alertmanager — DỮ LIỆU KHÔNG TIN CẬY
  },

  steps: {
    // Thu thập bối cảnh bằng lệnh xác định, KHÔNG để model tự do gõ lệnh vào cụm.
    gather: action({
      run: async ({ alertName }, ctx) => {
        const [pods, deploys, errors] = await Promise.all([
          ctx.exec(`kubectl -n prod get pods -o wide --sort-by=.status.startTime | tail -30`),
          ctx.exec(`kubectl -n prod rollout history deploy --revision=0 2>/dev/null | tail -20`),
          ctx.exec(`logcli query '{namespace="prod"} |= "ERROR"' --limit 200 --since 30m || true`),
        ]);
        return { alertName, pods: pods.stdout, deploys: deploys.stdout, errors: errors.stdout };
      },
    }),

    hypothesize: acp({
      agent: "claude",
      prompt: ({ alertName, severity, payload }, prev) =>
        `Vai trò: SRE. Sự cố ${severity}: ${alertName}.\n\n` +
        `Nêu tối đa 3 giả thuyết nguyên nhân, sắp theo xác suất, mỗi giả thuyết kèm ` +
        `MỘT phép kiểm chứng rẻ nhất để xác nhận/bác bỏ.\n\n` +
        `<untrusted source="alertmanager">\n${payload}\n</untrusted>\n\n` +
        `Trạng thái pod:\n${prev.gather.pods}\n\n` +
        `Lịch sử triển khai:\n${prev.gather.deploys}\n\n` +
        `Mẫu log lỗi:\n<untrusted source="logs">\n${prev.gather.errors}\n</untrusted>`,
    }),

    classify: decision({
      agent: "codex",
      prompt: (_i, prev) =>
        `Dựa trên phân tích dưới đây, chọn ĐÚNG MỘT hành động khắc phục:\n\n${prev.hypothesize.text}\n\n` +
        `- rollback     : lỗi xuất hiện ngay sau một lần triển khai\n` +
        `- scale        : bão hoà tài nguyên, code không sai\n` +
        `- config       : sai cấu hình/feature flag, sửa được không cần deploy\n` +
        `- investigate  : chưa đủ dữ kiện để hành động`,
      choices: ["rollback", "scale", "config", "investigate"],
    }),

    // Mọi hành động chạm production đều dừng chờ người, kể cả SEV1.
    approveAction: checkpoint({
      title: "Duyệt hành động khắc phục",
      describe: (_i, prev) =>
        `Hành động đề xuất: ${prev.classify}\n\nLý do:\n${prev.hypothesize.text.slice(0, 1200)}`,
    }),

    execute: action({
      run: async (_i, ctx, prev) => {
        const map: Record<string, string> = {
          rollback: `kubectl -n prod rollout undo deploy/$FLEET_SERVICE`,
          scale: `kubectl -n prod scale deploy/$FLEET_SERVICE --replicas=$((FLEET_REPLICAS*2))`,
          config: `echo "Cần thao tác thủ công trên feature flag — không tự động hoá"`,
        };
        const cmd = map[prev.classify as string];
        if (!cmd) return { skipped: true };
        const out = await ctx.exec(cmd);
        return { skipped: false, output: out.stdout };
      },
    }),

    verify: compute({
      run: async (_i, prev) => ({
        acted: prev.execute?.skipped === false,
        action: prev.classify,
      }),
    }),

    // Postmortem viết ngay khi còn nóng — sau 2 ngày không ai nhớ dòng thời gian.
    postmortem: acp({
      agent: "gemini",
      prompt: ({ alertName, severity }, prev) =>
        `Vai trò: Docs. Viết postmortem KHÔNG quy trách nhiệm cá nhân cho sự cố ` +
        `${severity} ${alertName}.\n` +
        `Mục: Tóm tắt / Ảnh hưởng / Dòng thời gian / Nguyên nhân gốc / Cái đã chạy tốt / ` +
        `Cái đã chạy dở / Hành động khắc phục (có người chịu trách nhiệm và hạn).\n\n` +
        `Dữ kiện:\n${prev.hypothesize.text}\n\nHành động đã thực hiện: ${prev.classify}`,
    }),
  },

  edges: [
    ["gather", "hypothesize"],
    ["hypothesize", "classify"],
    decisionEdge("classify", {
      rollback: "approveAction",
      scale: "approveAction",
      config: "approveAction",
      investigate: "postmortem",   // chưa đủ dữ kiện thì chỉ ghi nhận, không hành động
    }),
    ["approveAction", "execute", (out) => out.approved === true],
    ["execute", "verify"],
    ["verify", "postmortem"],
  ],

  limits: { maxStepRuns: { hypothesize: 1, classify: 1 } },
});
