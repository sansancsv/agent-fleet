"""Kiểm thử phần thu hẹp khoá model theo backend.

Vì sao phần này đáng có test riêng: nó là một biện pháp BẢO MẬT, và biện pháp
bảo mật chỉ tồn tại trong tài liệu là biện pháp không tồn tại. Xem
docs/adr/0001-tach-khoa-model-khoi-container-chay-code.md để biết vì sao chỉ
thu hẹp mà chưa tách hẳn.

Bản sao của cùng logic nằm ở `execution-plane/scripts/run-role.sh`;
`scripts/validate.sh` bước 5d canh cho hai bên không lệch nhau.
"""
from __future__ import annotations

import pytest

from fleet.acpx_client import BACKEND_PROVIDER, ROLE_BACKENDS, provider_env

ALL_KEYS = {
    "ACPX_AUTH_ANTHROPIC_API_KEY": "sk-ant",
    "ACPX_AUTH_OPENAI_API_KEY": "sk-oai",
    "ACPX_AUTH_GEMINI_API_KEY": "sk-gem",
    "ANTHROPIC_API_KEY": "sk-ant-2",
    "OPENAI_API_KEY": "sk-oai-2",
    "GEMINI_API_KEY": "sk-gem-2",
    "PATH": "/usr/bin",
}


class TestThuHepKhoa:
    @pytest.mark.parametrize(
        ("backend", "giu", "bo"),
        [
            ("claude", "ANTHROPIC", ("OPENAI", "GEMINI")),
            ("codex", "OPENAI", ("ANTHROPIC", "GEMINI")),
            ("gemini", "GEMINI", ("ANTHROPIC", "OPENAI")),
        ],
    )
    def test_chi_giu_khoa_cua_backend_dang_chay(self, backend, giu, bo):
        env = provider_env(backend, ALL_KEYS)
        assert env[f"ACPX_AUTH_{giu}_API_KEY"]
        assert env[f"{giu}_API_KEY"]
        for provider in bo:
            assert f"ACPX_AUTH_{provider}_API_KEY" not in env
            assert f"{provider}_API_KEY" not in env

    def test_backend_la_thi_go_tat_ca(self):
        # Fail closed: thà lượt đó hỏng vì thiếu khoá còn hơn lặng lẽ phơi cả ba
        # cho một backend chưa ai rà.
        env = provider_env("backend-chua-biet", ALL_KEYS)
        assert not [k for k in env if k.endswith("_API_KEY")]

    def test_khong_dung_toi_bien_khac(self):
        assert provider_env("claude", ALL_KEYS)["PATH"] == "/usr/bin"

    def test_khong_sua_dict_dau_vao(self):
        goc = dict(ALL_KEYS)
        provider_env("claude", goc)
        assert goc == ALL_KEYS

    def test_moi_backend_trong_ROLE_BACKENDS_deu_co_nha_cung_cap(self):
        # Thêm vai trò với backend thứ tư mà quên khai nhà cung cấp thì vai trò
        # đó sẽ chạy với KHÔNG có khoá nào. Bắt ở đây, không bắt lúc 2 giờ sáng.
        thieu = {b for b, _ in ROLE_BACKENDS.values()} - set(BACKEND_PROVIDER)
        assert not thieu, f"backend chưa khai trong BACKEND_PROVIDER: {sorted(thieu)}"
