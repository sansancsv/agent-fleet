#!/usr/bin/env python3
"""Bắt lỗi "named volume gắn vào thư mục con của image người khác".

VÌ SAO CÓ PHÉP KIỂM NÀY: khi một named volume được gắn vào một đường dẫn CHƯA
tồn tại trong image, Docker tạo thư mục đó với chủ sở hữu root:root. Nếu tiến
trình trong container chạy bằng user thường (rất nên như vậy), nó sẽ không ghi
hay chmod được, và container chết ngay lúc khởi động với thông báo khó đoán:

    EPERM: operation not permitted, chmod '/home/node/.openclaw/state'

Với image do CHÍNH TA build, cách xử lý là tạo sẵn thư mục trong Dockerfile rồi
chown — volume sẽ kế thừa đúng chủ sở hữu. Với image của người khác, phải có một
init container chạy bằng root để chown trước.

Phép kiểm: mọi service dùng image bên ngoài (`image:`, không có `build:`) mà gắn
named volume vào thư mục con của /home hoặc /root thì PHẢI phụ thuộc vào một
service init (`service_completed_successfully`) — hoặc nằm trong danh sách miễn
trừ bên dưới, kèm lý do.
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

# Miễn trừ: đường dẫn mà image thượng nguồn ĐÃ tạo sẵn với đúng chủ sở hữu.
KNOWN_GOOD = {
    ("n8n", "/home/node/.n8n"),          # image n8n tạo sẵn, đây là volume chuẩn của họ
    ("n8n-worker", "/home/node/.n8n"),
}


def main(path: str) -> int:
    compose = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    services = compose.get("services", {})
    named_volumes = set(compose.get("volumes") or {})
    problems: list[str] = []

    for name, svc in services.items():
        if "build" in svc:          # image của ta — xử lý trong Dockerfile
            continue
        if str(svc.get("user", "")).split(":")[0] in ("root", "0"):
            continue                # chính là container init dọn quyền
        deps = svc.get("depends_on") or {}
        has_init = any(
            isinstance(v, dict) and v.get("condition") == "service_completed_successfully"
            for v in deps.values()
        ) if isinstance(deps, dict) else False

        for mount in svc.get("volumes", []) or []:
            if not isinstance(mount, str) or ":" not in mount:
                continue
            src, dst = mount.split(":")[0], mount.split(":")[1]
            if src not in named_volumes:
                continue                      # bind mount — chủ sở hữu theo host
            if not dst.startswith(("/home/", "/root/")):
                continue
            depth = dst.rstrip("/").count("/")
            if depth < 3:                     # ví dụ /home/node — image thường có sẵn
                continue
            if (name, dst) in KNOWN_GOOD or has_init:
                continue
            problems.append(
                f"{name}: volume '{src}' gắn vào '{dst}' (thư mục con) trên image bên ngoài "
                f"mà không có init container chown trước → sẽ EPERM khi chạy bằng user thường"
            )

    for p in problems:
        print(f"  {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "deploy/docker/docker-compose.yml"))
