"""Chống lệch: `graph.GRAPH_ROLES` phải phủ mọi vai trò mà graph.py gọi.

Chốt dataClass của `POST /runs/wait` (server.py) chỉ kiểm backend của các vai
trò trong GRAPH_ROLES. Một nút mới gọi `run_role("tester", ...)` mà quên khai
vào đó thì chốt vẫn cho qua, trong khi dữ liệu tới một backend chưa ai kiểm.

Đọc graph.py bằng AST thay vì chạy đồ thị: bắt được cả vai trò trên nhánh hiếm
(`risky`) mà test chạy đồ thị dễ bỏ sót, và không cần git, model hay mạng.
Giới hạn: chỉ thấy tên vai trò viết thành chuỗi literal TRONG graph.py. Danh
sách vai trò mà chuyển sang module khác (ví dụ một hàm trong policies.py trả về
vai trò thẩm định) thì phải quét thêm module đó.
"""
from __future__ import annotations

import ast
from pathlib import Path

from fleet import graph
from fleet.acpx_client import ROLE_BACKENDS

GRAPH_PY = Path(graph.__file__)
SOURCE = GRAPH_PY.read_text(encoding="utf-8")


def _assigns(stmt: ast.stmt, name: str) -> bool:
    if isinstance(stmt, ast.Assign):
        return any(isinstance(t, ast.Name) and t.id == name for t in stmt.targets)
    return (isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            and stmt.target.id == name)


def _role_literals(source: str) -> dict[str, list[int]]:
    """Chuỗi literal trùng tên một vai trò trong ROLE_BACKENDS → các dòng có nó.

    Bỏ qua chính phép gán GRAPH_ROLES: tính cả nó thì phép quét luôn "thấy" đủ
    vai trò, kể cả khi đã hỏng.
    """
    found: dict[str, list[int]] = {}
    for stmt in ast.parse(source, filename=str(GRAPH_PY)).body:
        if _assigns(stmt, "GRAPH_ROLES"):
            continue
        for node in ast.walk(stmt):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and node.value in ROLE_BACKENDS):
                found.setdefault(node.value, []).append(node.lineno)
    return found


class TestGraphRoles:
    def test_moi_vai_tro_graph_py_goi_deu_nam_trong_GRAPH_ROLES(self):
        thieu = {role: lines for role, lines in _role_literals(SOURCE).items()
                 if role not in graph.GRAPH_ROLES}
        assert not thieu, (
            f"graph.py dùng vai trò chưa khai trong GRAPH_ROLES (vai trò → dòng): {thieu}. "
            "Chốt dataClass của /runs/wait không kiểm backend của chúng — thêm vào GRAPH_ROLES."
        )

    def test_GRAPH_ROLES_chi_gom_vai_tro_co_that(self):
        # Tên gõ sai ở đây: chốt tra ROLE_BACKENDS[vai trò] hỏng (500), còn vai
        # trò thật mà graph.py gọi thì không được kiểm.
        assert set(graph.GRAPH_ROLES) <= set(ROLE_BACKENDS)

    def test_phep_quet_thay_vai_tro_trong_graph_py(self):
        # Phép quét hỏng (không thấy gì) thì test đầu tiên xanh vô nghĩa.
        assert _role_literals(SOURCE)

    def test_phep_quet_bat_duoc_nut_moi_quen_khai(self):
        # Đúng kịch bản cần chặn, dựng trên chính graph.py: thêm một nút gọi một
        # vai trò chưa có trong GRAPH_ROLES.
        moi = next(r for r in ROLE_BACKENDS if r not in graph.GRAPH_ROLES)
        nut_moi = (f"\n\nasync def nut_moi(state):\n"
                   f"    return await run_role({moi!r}, 'x', cwd=state['worktree'])\n")
        assert moi in _role_literals(SOURCE + nut_moi)
