/**
 * =============================================================================
 * Khối fleet-status cho các bước mà flow RẼ NHÁNH theo — dùng chung cho mọi flow.
 * -----------------------------------------------------------------------------
 * Hiến chương (`control-plane/workspaces/_shared/AGENTS.md`) chỉ được nạp vào agent
 * của OpenClaw. Lượt agent chạy qua acpx KHÔNG thấy nó, nên prompt nào mà `gate`
 * đọc kết quả phải tự nêu hợp đồng (`statusContract`).
 *
 * "Lượt hoàn tất" ở đây cùng định nghĩa với `policies.turn_problem()` của LangGraph
 * và node "Hợp nhất phát hiện (luật)" của n8n: không hoàn tất ≠ sạch. Lượt thẩm
 * định lỗi, rỗng hay dừng giữa chừng cũng có "0 mục chặn".
 * =============================================================================
 */

const MARKER = "```fleet-status";
const OUTCOMES = ["success", "partial", "blocked", "rejected"];

/** Đuôi prompt đòi khối trạng thái; `done` nói rõ `success` nghĩa là gì với vai trò đó. */
export function statusContract(done: string): string {
  return (
    "\n\nKẾT THÚC phản hồi bằng khối trạng thái dưới đây, đặt ở CUỐI CÙNG — không viết gì sau nó:\n" +
    `${MARKER}\n` +
    "role: <vai trò của bạn>\n" +
    "outcome: <ĐÚNG MỘT từ: success | partial | blocked | rejected>\n" +
    "confidence: <0.0–1.0>\n" +
    "artifacts: <đường dẫn, phân tách bằng dấu phẩy, hoặc none>\n" +
    "next: <câu hỏi hoặc hành động đề xuất, hoặc none>\n" +
    "lesson: <một câu cho lượt sau, hoặc bỏ trống>\n" +
    "```\n" +
    `${done} Thiếu thông tin để làm đúng → outcome: blocked và nêu đúng MỘT câu hỏi ở dòng next:. ` +
    "Việc vượt quyền của vai trò → outcome: rejected."
  );
}

/**
 * Lý do một lượt KHÔNG được tính là hoàn tất; chuỗi rỗng = hoàn tất.
 *
 * Bước `acp` chỉ trả văn bản, nên đọc khối fleet-status CUỐI CÙNG trong đó. Khối
 * đứng trước có thể là khối agent trích lại từ diff/issue, tức dữ liệu không tin
 * cậy. Không có lượt, văn bản rỗng, thiếu khối, hoặc `outcome` không phải
 * success/partial (kể cả nhãn lạ) đều là CHƯA hoàn tất.
 */
export function turnProblem(text: string | undefined): string {
  const t = text ?? "";
  const at = t.lastIndexOf(MARKER);
  if (at < 0) return "thiếu khối fleet-status";
  const status = new Map<string, string>();
  for (const row of t.slice(at + MARKER.length).split("```")[0].split("\n")) {
    const i = row.indexOf(":");
    if (i >= 0) status.set(row.slice(0, i).trim(), row.slice(i + 1).trim());
  }
  if (status.size === 0) return "thiếu khối fleet-status";
  const raw = status.get("outcome");
  if (raw === undefined) return "khối fleet-status thiếu outcome";
  const outcome = raw.replace(/^[`'".]+|[`'".]+$/g, "").toLowerCase();
  if (!OUTCOMES.includes(outcome)) return `outcome không hợp lệ: '${outcome.slice(0, 40)}'`;
  if (outcome === "blocked" || outcome === "rejected") return `outcome: ${outcome}`;
  return "";
}
