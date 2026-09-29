"""Kiểm thử các hàm quyết định.

Đây là phần QUAN TRỌNG NHẤT của bộ test: nếu logic chặn/không chặn sai, cả hệ
thống mất tác dụng kiểm soát. Các hàm này thuần tuý nên test được không cần model.
"""
import pytest

from fleet.policies import (
    allowed_backends, assert_backend_allowed, over_budget, parse_findings, risk_from_text,
)
from fleet.state import blockers, initial_state


class TestRiskParsing:
    def test_nhan_don_gian(self):
        assert risk_from_text("standard") == "standard"

    def test_co_loi_dan(self):
        assert risk_from_text("Tôi cho rằng đây là: risky") == "risky"

    def test_lay_nhan_cuoi_cung(self):
        assert risk_from_text("không phải trivial, đây là standard") == "standard"

    def test_khong_nhan_dang_duoc_thi_nghieng_ve_an_toan(self):
        # Khi không chắc, hệ thống phải chọn mức kiểm soát CHẶT hơn.
        assert risk_from_text("¯\\_(ツ)_/¯") == "risky"


class TestFindingParsing:
    def test_phat_hien_day_du(self):
        out = parse_findings("reviewer", "[BLOCKER] src/api.ts:42 | Chèn SQL từ req.query")
        assert len(out) == 1
        assert out[0]["severity"] == "BLOCKER"
        assert out[0]["location"] == "src/api.ts:42"

    def test_blocker_khong_co_vi_tri_thi_bi_loai(self):
        # "Bằng chứng hoặc im lặng" — câu văn hoa không được phép chặn PR.
        assert parse_findings("reviewer", "[CRITICAL] đây là vấn đề nghiêm trọng") == []

    def test_minor_khong_can_vi_tri(self):
        assert len(parse_findings("reviewer", "[NIT] nên đổi tên biến")) == 1


class TestModelPolicy:
    def test_du_lieu_han_che_chi_dung_model_noi_bo(self):
        assert_backend_allowed("local-llm", "restricted")
        with pytest.raises(PermissionError):
            assert_backend_allowed("claude", "restricted")

    def test_du_lieu_cong_khai_dung_moi_backend(self):
        for b in ("claude", "codex", "gemini", "local-llm"):
            assert_backend_allowed(b, "public")

    def test_du_lieu_mat_chi_claude_va_model_noi_bo(self):
        # Đúng vi phạm cũ của support.yaml: confidential từng phân loại và thẩm
        # định trên Gemini.
        for b in ("claude", "local-llm"):
            assert_backend_allowed(b, "confidential")
        for b in ("gemini", "codex"):
            with pytest.raises(PermissionError):
                assert_backend_allowed(b, "confidential")

    @pytest.mark.parametrize("data_class", ["", "bi-mat", "Restricted"])
    def test_muc_du_lieu_la_thi_tu_choi_moi_backend(self, data_class):
        # Fail closed: hồ sơ quên khai hoặc gõ nhầm dataClass KHÔNG được hiểu
        # là "không ràng buộc" (trước đây là KeyError, lọt qua `except
        # PermissionError` của bên gọi).
        for b in ("claude", "codex", "gemini", "local-llm"):
            with pytest.raises(PermissionError):
                assert_backend_allowed(b, data_class)
        assert allowed_backends(data_class) == []

    def test_allowed_backends_khong_lo_bang_chinh_sach(self):
        # Bên gọi sửa danh sách trả về không được nới chính sách cho lần gọi sau.
        allowed_backends("restricted").append("gemini")
        with pytest.raises(PermissionError):
            assert_backend_allowed("gemini", "restricted")


class TestBudget:
    def test_vuot_han_muc(self):
        assert over_budget(9.0, 8.0)
        assert not over_budget(7.99, 8.0)


class TestState:
    def test_dem_muc_chan(self):
        s = initial_state(task_id="X-1", title="t", repo="/r")
        s["findings"] = [
            {"role": "reviewer", "severity": "BLOCKER", "location": "a.ts:1", "detail": "d"},
            {"role": "reviewer", "severity": "NIT", "location": "", "detail": "d"},
        ]
        assert len(blockers(s)) == 1
