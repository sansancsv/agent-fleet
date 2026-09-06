"""
=============================================================================
BỐN CHỈ SỐ VẬN HÀNH — điền vào bảng còn trống ở mục 3.8 của tài liệu
-----------------------------------------------------------------------------
Tài liệu tien-hoa-agentic-patterns-vi.md để sẵn một bảng trống với ghi chú:
"để điền số đo thật từ hệ thống của mình, thay vì đi mượn số của người khác."
File này tính đúng bốn chỉ số đó từ vết chạy trong fleet.trajectory.

  1. Tỉ lệ hoàn thành phiên dài   — % phiên > 1h kết thúc thành công
  2. Chi phí trung bình / tác vụ  — token + hạ tầng
  3. Tỉ lệ can thiệp của người    — % quy trình cần người quyết định
  4. Lỗi lặp lại                  — kiểm chứng cách làm của Hashimoto

MỘT ĐIỀU PHẢI NÓI THẲNG VỀ CHỈ SỐ 2
-----------------------------------
acpx hiện KHÔNG trả về số token đã dùng, nên chi phí thật chưa đo được. Chỗ này
cố ý KHÔNG bịa ra một con số quy đổi từ số ký tự: một chỉ số sai còn tệ hơn một
chỉ số trống, vì người ta sẽ ra quyết định dựa trên nó. Báo cáo trả về các đại
lượng ĐO ĐƯỢC (số lượt agent, thời gian chạy, ký tự đầu ra) kèm trường
`token_cost` = null và lý do. Khi acpx phơi số token, sửa `step()` trong
trajectory.py để ghi thêm, rồi bỏ ghi chú ở đây.

Dùng:
    python -m fleet.metrics                 # bảng Markdown, dán thẳng vào docs
    python -m fleet.metrics --json          # JSON, cho dashboard
    python -m fleet.metrics --days 30
    make metrics
=============================================================================
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .trajectory import read_all

# Ngưỡng "phiên dài" theo đúng định nghĩa trong bảng của tài liệu.
LONG_SESSION_S = 3600


def _parse_ts(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def collect(days: int = 30, directory: Path | None = None) -> dict[str, Any]:
    """Tính bốn chỉ số trên các bản ghi trong `days` ngày gần nhất."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    runs: dict[str, dict[str, Any]] = {}
    steps_by_task: dict[str, list[dict]] = defaultdict(list)
    approvals: dict[str, list[dict]] = defaultdict(list)
    # chữ ký phát hiện -> tập task đã gặp. Dùng để đếm lỗi lặp lại.
    signature_tasks: dict[str, set[str]] = defaultdict(set)

    for rec in read_all(directory):
        ts = _parse_ts(rec.get("ts", ""))
        if ts is None or ts < since:
            continue
        task = str(rec.get("task_id") or "")
        if not task:
            continue
        event = rec.get("event")
        if event == "run.end":
            runs[task] = rec
        elif event == "step":
            steps_by_task[task].append(rec)
            for sig in rec.get("blockers") or []:
                signature_tasks[str(sig)].add(task)
        elif event == "approval":
            approvals[task].append(rec)

    total_runs = len(runs)

    # --- 1. Tỉ lệ hoàn thành phiên dài --------------------------------------
    long_runs = [r for r in runs.values() if float(r.get("duration_s") or 0) > LONG_SESSION_S]
    long_ok = [r for r in long_runs if r.get("outcome") == "success"]

    # --- 2. Chi phí / tác vụ (đại lượng đo được — xem ghi chú đầu file) -----
    turns = [len(steps_by_task.get(t, [])) for t in runs] or [0]
    durations = [float(r.get("duration_s") or 0) for r in runs.values()] or [0.0]
    chars = [sum(int(s.get("output_chars") or 0) for s in steps_by_task.get(t, [])) for t in runs]

    # --- 3. Tỉ lệ can thiệp của người ---------------------------------------
    # Một quy trình "cần người" khi nó đi qua điểm chờ duyệt HOẶC bị leo thang.
    needed_human = [
        t for t, r in runs.items()
        if approvals.get(t) or r.get("escalated") or r.get("approved_by")
    ]
    total_steps = sum(len(v) for v in steps_by_task.values())

    # --- 4. Lỗi lặp lại ------------------------------------------------------
    # Một chữ ký xuất hiện ở >1 công việc = ràng buộc hiện có chưa chặn được nó.
    # Đây chính là phép kiểm chứng cách làm của Hashimoto: sau khi thêm một dòng
    # vào AGENTS.md, chữ ký tương ứng phải ngừng xuất hiện ở các công việc mới.
    repeated = {s: sorted(t) for s, t in signature_tasks.items() if len(t) > 1}

    return {
        "window_days": days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_runs": total_runs,
        "total_steps": total_steps,
        "long_session_success_rate": {
            "value": _pct(len(long_ok), len(long_runs)),
            "numerator": len(long_ok),
            "denominator": len(long_runs),
            "definition": f"% quy trình chạy > {LONG_SESSION_S}s kết thúc outcome=success",
        },
        "cost_per_task": {
            "token_cost": None,
            "token_cost_reason": "acpx chưa trả về số token — không quy đổi từ ký tự để tránh số giả",
            "avg_agent_turns": round(sum(turns) / max(len(turns), 1), 2),
            "avg_duration_s": round(sum(durations) / max(len(durations), 1), 1),
            "avg_output_chars": round(sum(chars) / max(len(chars), 1)) if chars else 0,
        },
        "human_intervention_rate": {
            "value": _pct(len(needed_human), total_runs),
            "numerator": len(needed_human),
            "denominator": total_runs,
            "definition": "% quy trình đi qua điểm chờ duyệt hoặc bị leo thang cho người",
        },
        "repeat_findings": {
            "value": _pct(len(repeated), len(signature_tasks)),
            "numerator": len(repeated),
            "denominator": len(signature_tasks),
            "definition": "% chữ ký phát hiện (mức|file) xuất hiện ở nhiều hơn một công việc",
            "top": sorted(repeated.items(), key=lambda kv: -len(kv[1]))[:10],
        },
    }


def _pct(num: int, den: int) -> float | None:
    """Không có mẫu số thì trả None, KHÔNG trả 0.

    0% và "chưa có dữ liệu" là hai điều hoàn toàn khác nhau; gộp chúng lại là
    cách nhanh nhất để báo cáo một hệ thống hoàn hảo mà chưa hề chạy lần nào.
    """
    return round(100.0 * num / den, 1) if den else None


def as_markdown(m: dict[str, Any]) -> str:
    def show(node: dict) -> str:
        v = node.get("value")
        base = "chưa có dữ liệu" if v is None else f"{v}%"
        return f"{base} ({node['numerator']}/{node['denominator']})"

    cost = m["cost_per_task"]
    lines = [
        f"# Chỉ số vận hành fleet — {m['window_days']} ngày gần nhất",
        "",
        f"Sinh lúc: {m['generated_at']}",
        f"Số quy trình đã kết thúc: {m['total_runs']} · số lượt agent: {m['total_steps']}",
        "",
        "| Chỉ số | Định nghĩa | Giá trị |",
        "|---|---|---|",
        f"| Tỉ lệ hoàn thành phiên dài | {m['long_session_success_rate']['definition']} "
        f"| {show(m['long_session_success_rate'])} |",
        f"| Chi phí trung bình / tác vụ | token + hạ tầng | **chưa đo được** — "
        f"{cost['token_cost_reason']} |",
        f"| ↳ đại lượng thay thế | lượt agent · thời gian · ký tự đầu ra | "
        f"{cost['avg_agent_turns']} lượt · {cost['avg_duration_s']}s · "
        f"{cost['avg_output_chars']} ký tự |",
        f"| Tỉ lệ can thiệp của người | {m['human_intervention_rate']['definition']} "
        f"| {show(m['human_intervention_rate'])} |",
        f"| Lỗi lặp lại sau khi thêm ràng buộc | {m['repeat_findings']['definition']} "
        f"| {show(m['repeat_findings'])} |",
    ]
    top = m["repeat_findings"]["top"]
    if top:
        lines += ["", "## Phát hiện lặp lại nhiều nhất", "",
                  "Mỗi dòng là một ràng buộc còn thiếu trong `_shared/AGENTS.md`", ""]
        lines += [f"- `{sig}` — {len(tasks)} công việc: {', '.join(tasks[:6])}"
                  for sig, tasks in top]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Chỉ số vận hành fleet từ vết chạy")
    ap.add_argument("--days", type=int, default=30, help="cửa sổ thời gian (mặc định 30)")
    ap.add_argument("--json", action="store_true", help="in JSON thay vì bảng Markdown")
    ap.add_argument("--dir", type=Path, default=None, help="thư mục vết chạy")
    args = ap.parse_args(argv)

    m = collect(days=args.days, directory=args.dir)
    print(json.dumps(m, ensure_ascii=False, indent=2) if args.json else as_markdown(m), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
