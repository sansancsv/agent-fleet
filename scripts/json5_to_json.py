#!/usr/bin/env python3
"""Chuyển JSON5 (định dạng cấu hình của OpenClaw) sang JSON thuần để kiểm chứng.

Vì sao tự viết thay vì dùng thư viện: `validate.sh` phải chạy được trên máy
trần, trong CI, và trong container tối giản — không phụ thuộc npm/pip.
Bộ chuyển này xử lý đúng những gì OpenClaw cho phép:

  * chú thích `//` và `/* */`
  * dấu phẩy thừa trước `}` hoặc `]`
  * khoá không có dấu nháy  ({ agents: {...} })
  * chuỗi trong nháy đơn

Nó bỏ qua một cách có chủ đích các tính năng JSON5 mà cấu hình fleet không dùng
(số hex, số dẫn đầu bằng dấu chấm, xuống dòng trong chuỗi).

Dùng:  python3 scripts/json5_to_json.py <file>   → in JSON ra stdout, mã 0 nếu hợp lệ
"""

from __future__ import annotations

import json
import sys


def strip_comments(src: str) -> str:
    """Bỏ chú thích nhưng KHÔNG đụng vào nội dung nằm trong chuỗi."""
    out: list[str] = []
    i, n = 0, len(src)
    quote: str | None = None
    while i < n:
        ch = src[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            out.append(ch)
            i += 1
            continue
        if ch == "/" and i + 1 < n:
            nxt = src[i + 1]
            if nxt == "/":
                while i < n and src[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (src[i] == "*" and src[i + 1] == "/"):
                    i += 1
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def single_to_double_quotes(src: str) -> str:
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                out.append(src[i])
                if src[i] == "\\":
                    i += 1
                    if i < n:
                        out.append(src[i])
                elif src[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == "'":
            out.append('"')
            i += 1
            while i < n and src[i] != "'":
                if src[i] == "\\":
                    out.append(src[i])
                    i += 1
                    if i < n:
                        out.append(src[i])
                        i += 1
                    continue
                out.append('\\"' if src[i] == '"' else src[i])
                i += 1
            out.append('"')
            i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def strip_trailing_commas(src: str) -> str:
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                out.append(src[i])
                if src[i] == "\\":
                    i += 1
                    if i < n:
                        out.append(src[i])
                elif src[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == ",":
            j = i + 1
            while j < n and src[j] in " \t\r\n":
                j += 1
            if j < n and src[j] in "}]":
                i += 1
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def quote_bare_keys(src: str) -> str:
    """Bọc nháy cho khoá trần, bỏ qua mọi thứ nằm trong chuỗi.

    Phải quét theo ký tự chứ không thay thế bằng regex trên cả file: một chuỗi
    như "${VAR:-mặc định}" chứa cả `{` lẫn `:` và sẽ bị regex hiểu nhầm là khoá.
    """
    out: list[str] = []
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                out.append(src[i])
                if src[i] == "\\":
                    i += 1
                    if i < n:
                        out.append(src[i])
                elif src[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch in "{,":
            out.append(ch)
            i += 1
            j = i
            while j < n and src[j] in " \t\r\n":
                j += 1
            k = j
            while k < n and (src[k].isalnum() or src[k] in "_$"):
                k += 1
            m = k
            while m < n and src[m] in " \t\r\n":
                m += 1
            if k > j and m < n and src[m] == ":" and (src[j].isalpha() or src[j] in "_$"):
                out.append(src[i:j])
                out.append('"' + src[j:k] + '"')
                i = k
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def loads(src: str):
    text = strip_comments(src)
    text = single_to_double_quotes(text)
    text = quote_bare_keys(text)
    text = strip_trailing_commas(text)
    return json.loads(text)


def main() -> int:
    if len(sys.argv) != 2:
        print("dùng: json5_to_json.py <file>", file=sys.stderr)
        return 64
    try:
        with open(sys.argv[1], encoding="utf-8") as fh:
            data = loads(fh.read())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"{sys.argv[1]}: {exc}", file=sys.stderr)
        return 1
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
