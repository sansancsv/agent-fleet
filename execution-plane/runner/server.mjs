#!/usr/bin/env node
// =============================================================================
// runner/server.mjs — API HTTP của tầng thực thi (agent-runner)
// -----------------------------------------------------------------------------
// VÌ SAO CÓ FILE NÀY: trước đây n8n gọi run-role.sh bằng node executeCommand,
// nghĩa là (a) lệnh chạy TRONG container n8n-worker, nơi không có acpx/python3,
// và (b) nội dung webhook được ghép vào chuỗi shell — chèn lệnh thật sự.
// Giờ tầng thực thi là một dịch vụ: mọi bên (n8n, LangGraph, gateway) gọi HTTP,
// và dữ liệu ngoài đi vào argv của tiến trình con qua spawn(), KHÔNG qua shell.
//
// Cố ý không dùng thư viện nào ngoài Node chuẩn: image agent-runner không cần
// thêm bước cài, và bề mặt tấn công của chính dịch vụ này nhỏ nhất có thể.
//
// Điểm cuối (mọi điểm trừ /healthz cần `Authorization: Bearer $RUNNER_TOKEN`):
//   GET  /healthz                         → { ok, busy, max }
//   POST /run          { role, cwd, prompt, write?, timeoutS? }
//                                         → JSON của run-role.sh + http 200/4xx/5xx
//   POST /pr/checkout  { repo, pr }       → { path, branch }   (clone nông PR về $FLEET_REPO_ROOT/pr-<n>)
//   POST /pr/cleanup   { path }           → { removed }        (chỉ xoá đúng dạng $FLEET_REPO_ROOT/pr-<n>)
//
// Chạy:  node /fleet/execution-plane/runner/server.mjs
// =============================================================================

import http from "node:http";
import { spawn } from "node:child_process";
import { stat, rm } from "node:fs/promises";
import path from "node:path";
import { timingSafeEqual } from "node:crypto";

const PORT = Number(process.env.RUNNER_PORT || 8787);
const TOKEN = process.env.RUNNER_TOKEN || "";
const REPO_ROOT = path.resolve(process.env.FLEET_REPO_ROOT || "/srv/repos");
const RUN_ROLE = process.env.FLEET_RUN_ROLE || "/fleet/execution-plane/scripts/run-role.sh";
const MAX_CONCURRENT = Number(process.env.RUNNER_MAX_CONCURRENT || 4);
const MAX_BODY_BYTES = 1 << 20; // 1 MiB — prompt dài hơn thế là dấu hiệu sai chỗ
const DEFAULT_TIMEOUT_S = 1800;
const MAX_TIMEOUT_S = 3600;

// Fail closed: không có token thì không phục vụ ai cả.
if (!TOKEN) {
  console.error("[runner] RUNNER_TOKEN chưa đặt — từ chối khởi động");
  process.exit(78); // EX_CONFIG
}

let busy = 0;

const log = (obj) => console.log(JSON.stringify({ ts: new Date().toISOString(), ...obj }));

// --- Tiện ích HTTP -----------------------------------------------------------
function send(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "content-type": "application/json; charset=utf-8",
    "content-length": Buffer.byteLength(data),
  });
  res.end(data);
}

function readJson(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > MAX_BODY_BYTES) {
        reject(Object.assign(new Error("body quá lớn"), { status: 413 }));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => {
      try {
        resolve(chunks.length ? JSON.parse(Buffer.concat(chunks).toString("utf8")) : {});
      } catch {
        reject(Object.assign(new Error("body không phải JSON"), { status: 400 }));
      }
    });
    req.on("error", reject);
  });
}

function authorized(req) {
  const h = req.headers.authorization || "";
  if (!h.startsWith("Bearer ")) return false;
  const got = Buffer.from(h.slice(7).trim());
  const want = Buffer.from(TOKEN);
  return got.length === want.length && timingSafeEqual(got, want);
}

// --- Kiểm tra đầu vào: chặt, vì đây là ranh giới tin cậy ----------------------
const ROLE_RE = /^[a-z][a-z0-9-]{1,30}$/;
const REPO_RE = /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/;

async function safeCwd(cwd) {
  if (typeof cwd !== "string" || !path.isAbsolute(cwd) || cwd.includes("\0")) return null;
  const resolved = path.resolve(cwd);
  // Chỉ cho phép thư mục nằm trong kho repo. Không có ngoại lệ.
  if (resolved !== REPO_ROOT && !resolved.startsWith(REPO_ROOT + path.sep)) return null;
  try {
    const s = await stat(resolved);
    return s.isDirectory() ? resolved : null;
  } catch {
    return null;
  }
}

function prPath(pr) {
  return path.join(REPO_ROOT, `pr-${pr}`);
}

// --- Chạy tiến trình con KHÔNG qua shell -------------------------------------
function run(cmd, args, { cwd, env, timeoutMs, input } = {}) {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd,
      env: { ...process.env, ...(env || {}) },
      stdio: [input == null ? "ignore" : "pipe", "pipe", "pipe"],
    });
    let out = "", err = "", timedOut = false;
    child.stdout.on("data", (d) => { out += d; });
    child.stderr.on("data", (d) => { if (err.length < 64_000) err += d; });
    const timer = timeoutMs
      ? setTimeout(() => { timedOut = true; child.kill("SIGKILL"); }, timeoutMs)
      : null;
    child.on("close", (code) => {
      if (timer) clearTimeout(timer);
      resolve({ code: code ?? 1, out, err, timedOut });
    });
    child.on("error", (e) => {
      if (timer) clearTimeout(timer);
      resolve({ code: 127, out, err: String(e), timedOut: false });
    });
    if (input != null) { child.stdin.end(input); }
  });
}

// --- Handlers ----------------------------------------------------------------
async function handleRun(body) {
  const { role, cwd, prompt, write, timeoutS } = body;
  if (typeof role !== "string" || !ROLE_RE.test(role)) return [400, { error: "role không hợp lệ" }];
  if (typeof prompt !== "string" || !prompt.trim()) return [400, { error: "thiếu prompt" }];
  const dir = await safeCwd(cwd);
  if (!dir) return [400, { error: `cwd phải là thư mục có thật nằm trong ${REPO_ROOT}` }];
  const t = Math.min(Number(timeoutS) || DEFAULT_TIMEOUT_S, MAX_TIMEOUT_S);

  const args = [RUN_ROLE, role, dir, prompt];
  if (write === true) args.push("--write");

  const started = Date.now();
  // Prompt đi vào argv của spawn() — không có shell nào diễn giải nó.
  const r = await run("bash", args, { timeoutMs: t * 1000 });
  const durationMs = Date.now() - started;

  if (r.timedOut) return [504, { error: `vượt quá ${t}s`, role, durationMs }];
  if (r.code === 64) return [400, { error: r.err.trim() || "run-role.sh từ chối tham số", role }];

  // run-role.sh in đúng một dòng JSON ở cuối stdout.
  const last = r.out.trim().split("\n").filter(Boolean).pop() || "";
  let payload;
  try { payload = JSON.parse(last); } catch {
    return [502, { error: "run-role.sh không trả JSON", role, exit: r.code, stderr: r.err.slice(-2000) }];
  }
  return [200, { ...payload, durationMs }];
}

async function handleCheckout(body) {
  const { repo, pr } = body;
  if (typeof repo !== "string" || !REPO_RE.test(repo)) return [400, { error: "repo phải có dạng owner/name" }];
  if (!Number.isInteger(pr) || pr <= 0) return [400, { error: "pr phải là số nguyên dương" }];
  const token = process.env.GITHUB_TOKEN || "";
  if (!token) return [503, { error: "GITHUB_TOKEN chưa đặt trong agent-runner" }];

  const wt = prPath(pr);
  const branch = `pr-${pr}`;
  await rm(wt, { recursive: true, force: true });

  // Token đi qua biến môi trường git, KHÔNG nằm trong URL/argv (ps sẽ không thấy).
  const gitEnv = {
    GIT_TERMINAL_PROMPT: "0",
    GIT_CONFIG_COUNT: "1",
    GIT_CONFIG_KEY_0: "http.https://github.com/.extraheader",
    GIT_CONFIG_VALUE_0: `AUTHORIZATION: bearer ${token}`,
  };
  const steps = [
    ["git", ["clone", "--depth", "50", "--no-tags", `https://github.com/${repo}.git`, wt], { env: gitEnv }],
    ["git", ["-C", wt, "fetch", "--depth", "50", "origin", `pull/${pr}/head:${branch}`], { env: gitEnv }],
    ["git", ["-C", wt, "checkout", "--quiet", branch], {}],
  ];
  for (const [cmd, args, opt] of steps) {
    const r = await run(cmd, args, { ...opt, timeoutMs: 300_000 });
    if (r.code !== 0) {
      await rm(wt, { recursive: true, force: true });
      return [502, { error: `git ${args[0]} thất bại`, stderr: r.err.replace(token, "***").slice(-2000) }];
    }
  }
  return [200, { path: wt, branch, repo, pr }];
}

async function handleCleanup(body) {
  const { path: p } = body;
  if (typeof p !== "string") return [400, { error: "thiếu path" }];
  const resolved = path.resolve(p);
  // Chỉ xoá đúng thư mục do /pr/checkout tạo — không xoá bất kỳ đường dẫn nào khác.
  const m = /^pr-(\d+)$/.exec(path.basename(resolved));
  if (!m || path.dirname(resolved) !== REPO_ROOT) return [400, { error: `chỉ xoá được ${REPO_ROOT}/pr-<số>` }];
  await rm(resolved, { recursive: true, force: true });
  return [200, { removed: resolved }];
}

const ROUTES = {
  "POST /run": handleRun,
  "POST /pr/checkout": handleCheckout,
  "POST /pr/cleanup": handleCleanup,
};

// --- Server ------------------------------------------------------------------
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://runner");
  const key = `${req.method} ${url.pathname}`;

  if (key === "GET /healthz") return send(res, 200, { ok: true, busy, max: MAX_CONCURRENT });
  if (!authorized(req)) return send(res, 401, { error: "thiếu hoặc sai Bearer token" });

  const handler = ROUTES[key];
  if (!handler) return send(res, 404, { error: "không có điểm cuối này" });
  if (busy >= MAX_CONCURRENT) return send(res, 429, { error: "runner đang bận", busy, max: MAX_CONCURRENT });

  busy += 1;
  const started = Date.now();
  try {
    const body = await readJson(req);
    const [status, out] = await handler(body);
    log({ route: key, status, role: body?.role, ms: Date.now() - started });
    send(res, status, out);
  } catch (e) {
    const status = e?.status || 500;
    log({ route: key, status, error: String(e?.message || e) });
    send(res, status, { error: String(e?.message || e) });
  } finally {
    busy -= 1;
  }
});

server.listen(PORT, "0.0.0.0", () => {
  log({ msg: "agent-runner API sẵn sàng", port: PORT, repoRoot: REPO_ROOT, maxConcurrent: MAX_CONCURRENT });
});

for (const sig of ["SIGTERM", "SIGINT"]) {
  process.on(sig, () => {
    log({ msg: `nhận ${sig}, dừng nhận yêu cầu mới` });
    server.close(() => process.exit(0));
    setTimeout(() => process.exit(0), 10_000).unref();
  });
}
