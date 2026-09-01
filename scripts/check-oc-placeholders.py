#!/usr/bin/env python3
"""Kiểm tra vị trí hợp lệ của ${BIẾN} trong cấu hình OpenClaw.

Ba quy tắc, đã đối chiếu với binary OpenClaw 2026.8.1:

  1. Trường credential (token, botToken, appToken, apiKey, password, secret…)
     CHẤP NHẬN mẫu "${BIẾN}" — đó là cách duy nhất để không ghi khoá vào git
     ở những trường "runtime-mutable" không nhận SecretRef object.
  2. Khối `mcp` cũng có thay thế ${BIẾN}.
  3. Mọi chỗ khác bị đọc NGUYÊN VĂN. Đây là lớp lỗi tốn nhiều thời gian nhất:
     cấu hình đúng cú pháp, gateway vẫn chết, và thông báo lỗi không hề nhắc
     tới biến môi trường (ví dụ: bind: "${X:-lan}" → `Invalid --bind`).

Ngoài ra: `${BIẾN:-mặc-định}` không được hỗ trợ ở bất kỳ đâu, và `env.vars`
ghi thẳng ra biến môi trường nên sẽ ghi đè khoá API thật do Docker tiêm vào.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from json5_to_json import loads  # noqa: E402

PLACEHOLDER = re.compile(r"\$\{[^}]*\}")

# Tên khoá được phép chứa ${BIẾN} (khớp không phân biệt hoa thường, dạng chứa).
CREDENTIAL_KEYS = (
    "token", "secret", "password", "apikey", "key", "credential", "auth",
)


def is_credential(path: list[str]) -> bool:
    return any(any(c in part.lower() for c in CREDENTIAL_KEYS) for part in path)


def is_secret_ref(node) -> bool:
    return (
        isinstance(node, dict)
        and set(node) >= {"source", "id"}
        and node.get("source") in ("env", "file", "exec", "store")
    )


def walk(node, path, problems, in_mcp=False):
    if isinstance(node, dict):
        # SecretRef object { source, provider, id }: hợp lệ theo SCHEMA nhưng
        # `provider` phải là một secret provider đã đăng ký — và khối `secrets`
        # trong cấu hình chỉ nói về egress proxy, không phải nơi đăng ký provider.
        # Hậu quả: cấu hình qua được `config validate` VÀ `security audit`, rồi
        # gateway chết lúc khởi động:
        #     SecretProviderResolutionError: Secret provider "x" is not configured
        # Trong repo này quy ước dùng chuỗi "${BIẾN}" cho mọi credential.
        if is_secret_ref(node):
            problems.append(
                f"{'.'.join(path)}: SecretRef {{source,provider,id}} — dùng chuỗi "
                f'"${{{node.get("id")}}}" thay thế. SecretRef qua được mọi phép kiểm '
                "tĩnh rồi làm gateway chết lúc khởi động nếu provider chưa đăng ký."
            )
        for key, value in node.items():
            walk(value, [*path, str(key)], problems, in_mcp or key == "mcp")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            walk(value, [*path, f"[{i}]"], problems, in_mcp)
    elif isinstance(node, str):
        for hit in PLACEHOLDER.findall(node):
            where = ".".join(path)
            if ":-" in hit:
                problems.append(f"{where}: {hit} — cú pháp ${{BIẾN:-mặc-định}} KHÔNG được hỗ trợ")
            elif not (in_mcp or is_credential(path)):
                problems.append(
                    f"{where}: {hit} — chỗ này bị đọc nguyên văn; viết thẳng giá trị"
                )


def main() -> int:
    problems: list[str] = []
    for name in sys.argv[1:]:
        try:
            cfg = loads(Path(name).read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}: không phân tích được ({exc})")
            continue
        walk(cfg, [], problems)
        if (cfg.get("env") or {}).get("vars"):
            problems.append(
                f"{name}: env.vars ghi thẳng ra biến môi trường và sẽ GHI ĐÈ khoá API "
                "do Docker tiêm vào — bỏ khối này đi"
            )
    for p in problems:
        print(f"  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
