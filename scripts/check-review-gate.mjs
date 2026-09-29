#!/usr/bin/env node
// =============================================================================
// check-review-gate.mjs — cổng thẩm định PR của n8n phải FAIL CLOSED
// -----------------------------------------------------------------------------
// Chạy CHÍNH đoạn code của node "Hợp nhất phát hiện (luật)" trong
// 02-pr-review-gate.json với payload mẫu đúng hình dạng mà agent-runner trả về
// (JSON của run-role.sh, hoặc item lỗi của node HTTP khi onError = tiếp tục).
// Kiểm ba điều:
//   1. Lượt thẩm định KHÔNG hoàn tất (lỗi HTTP, thoát mã ≠ 0, thiếu khối
//      fleet-status, outcome blocked/rejected/lạ, node không chạy) KHÔNG BAO GIỜ
//      cho ra `success`. Kiểm vét cạn mọi tổ hợp của các vai trò.
//   2. Body gửi lên GitHub (node "Cập nhật trạng thái commit") mang đúng state
//      đó, và description không quá 140 ký tự (GitHub trả 422 nếu dài hơn).
//   3. Cấu trúc mà (1) dựa vào: node thẩm định để lỗi chảy tiếp, node gộp chờ đủ
//      mọi đầu vào, prompt đòi khối fleet-status, vai trò khớp bảng của node gộp.
// Không cần n8n: `$`/`$input` được giả lập đúng phần mà đoạn code dùng.
// Gọi từ validate.sh bước 5e. Chạy tay: node scripts/check-review-gate.mjs [workflow.json]
// =============================================================================
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WF = process.argv[2] ?? "orchestration/n8n/workflows/02-pr-review-gate.json";
const GATE = "Hợp nhất phát hiện (luật)";
const MERGE = "Gộp ba kết quả";
const STATUS = "Cập nhật trạng thái commit";

const problems = [];
let checks = 0;
const check = (ok, msg) => { checks += 1; if (!ok) problems.push(msg); return ok; };
const len = (s) => [...s].length;

const wf = JSON.parse(readFileSync(path.resolve(ROOT, WF), "utf8"));
const node = (name) => wf.nodes.find((n) => n.name === name);
for (const name of [GATE, MERGE, STATUS]) {
  if (!node(name)) { console.error(`  ${WF}: không có node "${name}"`); process.exit(1); }
}

// Chạy một expression n8n dạng "={{ ... }}" với `$` giả.
const evalExpr = (expr, $) => new Function("$", `return (${expr.replace(/^=\{\{/, "").replace(/\}\}$/, "")});`)($);

// --- 3. Cấu trúc ---------------------------------------------------------------
// Node thẩm định = mọi node nối vào node gộp.
const reviews = Object.entries(wf.connections).flatMap(([from, c]) =>
  (c.main?.[0] ?? []).filter((t) => t.node === MERGE).map((t) => ({ node: from, input: t.index })));
const merge = node(MERGE).parameters;
check(reviews.length === 3, `cần 3 node thẩm định nối vào "${MERGE}", thấy ${reviews.length}`);
check(merge.mode === "append", `"${MERGE}" phải là mode append (combine gộp các item làm một), đang là ${merge.mode}`);
check(merge.numberInputs === reviews.length,
  `"${MERGE}".parameters.numberInputs = ${merge.numberInputs}, phải bằng số node thẩm định (${reviews.length})`);
check(new Set(reviews.map((r) => r.input)).size === reviews.length, `hai node thẩm định cắm chung một đầu vào của "${MERGE}"`);
for (const r of reviews) {
  const n = node(r.node);
  check(n.onError === "continueRegularOutput",
    `"${r.node}" phải có onError = continueRegularOutput, nếu không lỗi của agent-runner làm workflow dừng im lặng`);
  const body = JSON.parse(evalExpr(n.parameters.jsonBody, () => ({ item: { json: { path: "/srv/repos/pr-1" } } })));
  r.role = body.role;
  check(body.prompt.includes("```fleet-status") && ["success", "partial", "blocked", "rejected"].every((o) => body.prompt.includes(o)),
    `prompt của "${r.node}" phải đòi khối fleet-status (agent qua agent-runner không thấy hiến chương)`);
}

// --- Chạy code của node gộp ----------------------------------------------------
const gateFn = new Function("$", "$input", node(GATE).parameters.jsCode);
// outputs: Map<tên node, json[] | undefined>; undefined = node không chạy.
function runGate(outputs) {
  const $ = (name) => ({
    all: () => {
      const items = outputs.get(name);
      if (items === undefined) throw new Error(`Node '${name}' hasn't been executed`);
      return structuredClone(items).map((json) => ({ json }));
    },
  });
  const all = [...outputs.values()].filter(Boolean).flat().map((json) => ({ json }));
  const out = gateFn($, { all: () => all });
  if (!Array.isArray(out) || out.length !== 1) throw new Error("node gộp phải trả đúng một item");
  return out[0].json;
}

const block = (role, outcome) =>
  `\n\`\`\`fleet-status\nrole: ${role}\noutcome: ${outcome}\nconfidence: 0.8\nartifacts: none\nnext: none\nlesson:\n\`\`\`\n`;
// Đúng hình dạng JSON mà run-role.sh in ra (agent-runner thêm durationMs).
function turn(role, { exit = 0, outcome = "success", text = "Đã xem diff. Không có phát hiện nào.", status } = {}) {
  return {
    role, exit, session: `${role}-1790000000-42`, durationMs: 5,
    status: status ?? (outcome == null ? {} : { role, outcome, confidence: "0.8", artifacts: "none", next: "none", lesson: "" }),
    text: text + (outcome == null ? "" : block(role, outcome)),
  };
}
// Item lỗi mà node HTTP sinh ra khi onError = continueRegularOutput (đối chiếu n8n 2.36.9).
const httpError = (status, message) => ({ error: { message, name: "AxiosError", code: "ERR_BAD_RESPONSE", status, stack: "AxiosError: …" } });

// [mô tả, (vai trò) => json[] | undefined, hoàn tất?]
const VARIANTS = [
  ["outcome success", (r) => [turn(r)], true],
  ["outcome partial", (r) => [turn(r, { outcome: "partial" })], true],
  ["outcome có nháy và chữ hoa", (r) => [turn(r, { status: { outcome: "`Success`." } })], true],
  ["thoát mã 1, không có gì", (r) => [turn(r, { exit: 1, outcome: null, text: "" })], false],
  ["thoát mã 2 dù có khối success", (r) => [turn(r, { exit: 2 })], false],
  ["exit là chuỗi \"0\"", (r) => [{ ...turn(r), exit: "0" }], false],
  ["thiếu exit", (r) => { const t = turn(r); delete t.exit; return [t]; }, false],
  ["thiếu khối fleet-status", (r) => [turn(r, { outcome: null })], false],
  ["khối thiếu outcome", (r) => [turn(r, { status: { role: r, confidence: "0.8" } })], false],
  ["outcome blocked", (r) => [turn(r, { outcome: "blocked" })], false],
  ["outcome rejected", (r) => [turn(r, { outcome: "rejected" })], false],
  ["outcome chép nguyên dòng mẫu", (r) => [turn(r, { outcome: "success | partial | blocked | rejected" })], false],
  ["outcome rỗng", (r) => [turn(r, { status: { outcome: "" } })], false],
  ["status là mảng", (r) => [turn(r, { status: ["success"] })], false],
  ["vai trò trả về khác", (r) => [{ ...turn(r), role: "implementer" }], false],
  ["HTTP 504", () => [httpError(504, '504 - "{\\"error\\":\\"vượt quá 1800s\\",\\"durationMs\\":1800000}"')], false],
  ["HTTP 429", () => [httpError(429, "Try spacing your requests out using the batching settings under 'Options'")], false],
  ["lỗi mạng", () => [{ error: { message: "connect ECONNREFUSED 10.0.0.5:8787", code: "ECONNREFUSED" } }], false],
  ["node không chạy", () => undefined, false],
  ["node không trả item nào", () => [], false],
  ["hai item, một hỏng", (r) => [turn(r), turn(r, { exit: 1, outcome: null })], false],
];

function checkPost(out, label) {
  const post = JSON.parse(evalExpr(node(STATUS).parameters.jsonBody, () => ({ item: { json: out } })));
  check(post.state === out.state && post.context === "fleet/cross-review",
    `${label}: body gửi GitHub có state ${post.state}, node gộp quyết ${out.state}`);
  if (check(typeof post.description === "string", `${label}: body gửi GitHub thiếu description`)) {
    check(len(post.description) <= 140, `${label}: description dài ${len(post.description)} ký tự (> 140 → GitHub trả 422)`);
  }
  return post;
}

// --- 1 + 2. Vét cạn mọi tổ hợp -------------------------------------------------
let combos = 0;
const pick = (i) => reviews.map((_, k) => Math.floor(i / VARIANTS.length ** k) % VARIANTS.length);
for (let i = 0; i < VARIANTS.length ** reviews.length; i++) {
  const chosen = pick(i).map((v, k) => ({ ...reviews[k], variant: VARIANTS[v] }));
  const label = chosen.map((c) => `${c.role}=${c.variant[0]}`).join(", ");
  const out = runGate(new Map(chosen.map((c) => [c.node, c.variant[1](c.role)])));
  const allDone = chosen.every((c) => c.variant[2]);
  combos += 1;
  if (!check(out.state === (allDone ? "success" : "error"), `${label}: state ${out.state}, phải là ${allDone ? "success" : "error"}`)) continue;
  for (const c of chosen.filter((x) => !x.variant[2])) {
    check(out.incompleteRoles.includes(c.role) && out.body.includes(`| ${c.role} |`),
      `${label}: không nêu tên vai trò hỏng ${c.role} trong kết quả`);
  }
  checkPost(out, label);
}

// --- Mục chặn: đúng luật "bằng chứng hoặc im lặng" ---------------------------
const ok = (r) => [turn(r)];
const scenario = (label, byRole, want) => {
  const out = runGate(new Map(reviews.map((r) => [r.node, (byRole[r.role] ?? ok)(r.role)])));
  for (const [k, v] of Object.entries(want)) {
    check(JSON.stringify(out[k]) === JSON.stringify(v), `${label}: ${k} = ${JSON.stringify(out[k])}, phải là ${JSON.stringify(v)}`);
  }
  checkPost(out, label);
  return out;
};
const BLOCKER = "[BLOCKER] src/db.ts:42 | chuỗi SQL ghép từ đầu vào | id=1 OR 1=1 đọc mọi dòng";
const [r0, r1, r2] = reviews.map((r) => r.role);
scenario("BLOCKER có file:dòng ở vai trò đầu", { [r0]: (r) => [turn(r, { text: BLOCKER })] }, { state: "failure", blockerCount: 1 });
scenario("BLOCKER ở vai trò cuối", { [r2]: (r) => [turn(r, { text: BLOCKER })] }, { state: "failure", blockerCount: 1 });
scenario("BLOCKER không có file:dòng bị loại", { [r1]: (r) => [turn(r, { text: "[BLOCKER] kiến trúc này có vấn đề" })] },
  { state: "success", blockerCount: 0 });
scenario("CRITICAL trong lượt thoát mã 1 vẫn chặn, lượt hỏng vẫn được nêu",
  { [r1]: (r) => [turn(r, { exit: 1, outcome: null, text: "[CRITICAL] app/auth.py:7 | bỏ qua kiểm chữ ký | token giả qua được" })] },
  { state: "failure", blockerCount: 1, incompleteRoles: [r1] });
const twice = scenario("cùng một phát hiện từ hai vai trò", {
  [r0]: (r) => [turn(r, { text: "[MAJOR] src/a.ts:3 | thiếu kiểm null" })],
  [r1]: (r) => [turn(r, { text: "[MAJOR] src/a.ts:3 | thiếu kiểm null\n[MAJOR] src/a.ts:3 | thiếu kiểm null" })],
}, { state: "success" });
check(twice.findings.length === 1 && twice.findings[0].votes === 2,
  `đồng thuận phải đếm số vai trò khác nhau: ${JSON.stringify(twice.findings)}`);
// Vai trò mà prompt thật gửi đi phải khớp bảng REVIEWS của node gộp.
scenario("vai trò lấy từ jsonBody của từng node thẩm định", {}, { state: "success", incompleteRoles: [] });

// Lý do lỗi HTTP phải đọc được: mã HTTP + trường `error` của agent-runner.
for (const [variant, want] of [["HTTP 504", "HTTP 504: vượt quá 1800s"], ["HTTP 429", "HTTP 429"], ["lỗi mạng", "ECONNREFUSED"]]) {
  const make = VARIANTS.find((v) => v[0] === variant)[1];
  const out = runGate(new Map(reviews.map((r, k) => [r.node, k === 1 ? make(r.role) : ok(r.role)])));
  const post = checkPost(out, variant);
  check(String(post.description).includes(want) && out.body.includes(want),
    `${variant}: lý do phải nêu "${want}", description là ${JSON.stringify(post.description)}`);
}

const long = runGate(new Map(reviews.map((r) => [r.node, [httpError(502, `502 - "${"x".repeat(5000)}"`)]])));
check(long.state === "error", "ba lượt 502 với thân dài: state phải là error");
checkPost(long, "ba lượt 502 với thân dài");
check(!runGate(new Map(reviews.map((r) => [r.node, [httpError(502,
  '502 - "{\\"error\\":\\"run-role.sh không trả JSON\\",\\"stderr\\":\\"Traceback: /home/node/.acpx/BI-MAT\\"}"')]]))).body.includes("BI-MAT"),
"stderr trong thân lỗi 502 không được lên nhận xét PR");

if (problems.length) {
  for (const p of problems.slice(0, 25)) console.log(`  ${p}`);
  if (problems.length > 25) console.log(`  … và ${problems.length - 25} lỗi nữa`);
  console.log(`  ${problems.length}/${checks} phép kiểm thất bại`);
  process.exit(1);
}
console.log(`${checks} phép kiểm, ${combos} tổ hợp lượt thẩm định: không lượt hỏng nào ra success`);
