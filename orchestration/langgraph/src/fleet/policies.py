"""Chính sách và bộ phân tích — tất cả đều là hàm thuần tuý, kiểm thử được.

Nguyên tắc quan trọng của kiến trúc này: **mọi quyết định chặn/không chặn phải
nằm trong code xác định, không nằm trong prompt.** Model đưa ra *phát hiện*;
code đưa ra *quyết định*. Nếu để model tự quyết "có nên chặn không", kết quả sẽ
đổi giữa hai lần chạy giống hệt nhau — và không thể kiểm toán.
"""

from __future__ import annotations

import re
from typing import Literal, get_args

from .state import Finding, Risk

_RISK_VALUES = set(get_args(Risk))

# [BLOCKER] src/api/user.ts:142 | mô tả | kịch bản
_FINDING_RE = re.compile(
    r"^\s*\[?(?P<sev>BLOCKER|CRITICAL|MAJOR|MINOR|NIT)\]?\s*"
    r"(?P<loc>[\w./\-]+:\d+)?\s*[|:\-]?\s*(?P<detail>.+)$",
    re.IGNORECASE,
)


def risk_from_text(text: str) -> Risk:
    """Ép đầu ra của model về đúng một nhãn hợp lệ.

    Model được yêu cầu chỉ in ra nhãn, nhưng đôi khi vẫn thêm lời dẫn. Ta quét
    từ cuối lên vì nhãn kết luận thường nằm ở cuối câu trả lời. Không nhận dạng
    được thì trả về mức an toàn nhất ("risky"), KHÔNG phải mức dễ dãi nhất —
    khi không chắc, hệ thống phải nghiêng về phía kiểm soát chặt hơn.
    """
    tokens = re.findall(r"[a-z]+", text.lower())
    for token in reversed(tokens):
        if token in _RISK_VALUES:
            return token  # type: ignore[return-value]
    return "risky"


def parse_findings(role: str, text: str) -> list[Finding]:
    """Trích danh sách phát hiện có cấu trúc từ câu trả lời tự do của model.

    Bỏ qua mọi dòng không có `file:dòng` khi mức là BLOCKER/CRITICAL — quy tắc
    "bằng chứng hoặc im lặng" trong hiến chương fleet. Nhờ vậy một câu văn hoa
    kiểu "đây là một vấn đề CRITICAL cần lưu ý" không tự động chặn được PR.
    """
    findings: list[Finding] = []
    for line in text.splitlines():
        m = _FINDING_RE.match(line)
        if not m:
            continue
        sev = m.group("sev").upper()
        loc = m.group("loc") or ""
        detail = m.group("detail").strip(" |-—")
        if sev in ("BLOCKER", "CRITICAL") and not loc:
            continue  # không có vị trí cụ thể → không đủ tư cách chặn
        findings.append({"role": role, "severity": sev, "location": loc, "detail": detail[:500]})
    return findings


# ---------------------------------------------------------------------------
# Chính sách model theo phòng ban / mức nhạy cảm dữ liệu
# ---------------------------------------------------------------------------
DataClass = Literal["public", "internal", "confidential", "restricted"]

# `restricted` = dữ liệu không được rời hạ tầng công ty (lương, hồ sơ nhân sự,
# dữ liệu khách hàng có định danh). Chỉ model tự host được phép xử lý.
#
# Bản sao của `policy/model-routing.yaml` (nguồn sự thật) và `allowed_backends`
# trong `policy/opa/fleet.rego`. validate.sh bước 8a kiểm ba bảng khớp nhau.
MODEL_POLICY: dict[DataClass, list[str]] = {
    "public": ["claude", "codex", "gemini", "local-llm"],
    "internal": ["claude", "codex", "gemini", "local-llm"],
    "confidential": ["claude", "local-llm"],
    "restricted": ["local-llm"],
}


def allowed_backends(data_class: str) -> list[str]:
    """Backend được xử lý dữ liệu mức này. Mức lạ → danh sách rỗng (fail closed)."""
    return list(MODEL_POLICY.get(data_class, []))  # type: ignore[call-overload]


def assert_backend_allowed(backend: str, data_class: str) -> None:
    """Ném PermissionError nếu `backend` không được xử lý dữ liệu mức `data_class`.

    `data_class` đến từ YAML của hồ sơ nên có thể thiếu hoặc gõ nhầm. Mức không
    có trong MODEL_POLICY bị từ chối với MỌI backend — không bao giờ được hiểu
    là "không ràng buộc".
    """
    allowed = MODEL_POLICY.get(data_class)  # type: ignore[call-overload]
    if allowed is None:
        raise PermissionError(
            f"dataClass '{data_class}' không có trong chính sách model "
            f"({', '.join(MODEL_POLICY)}) — không backend nào được phép"
        )
    if backend not in allowed:
        raise PermissionError(
            f"Backend '{backend}' không được phép xử lý dữ liệu mức '{data_class}'. "
            f"Được phép: {', '.join(allowed)}"
        )


# ---------------------------------------------------------------------------
# Hạn mức chi phí — chặn "agent chạy hoang" đốt hết ngân sách trong một đêm
# ---------------------------------------------------------------------------
BUDGET_PER_TASK_USD = 8.0
BUDGET_PER_DAY_USD = 400.0


def over_budget(spent_usd: float, limit_usd: float = BUDGET_PER_TASK_USD) -> bool:
    return spent_usd >= limit_usd
