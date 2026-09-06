"""Kiểm thử vết chạy và bốn chỉ số vận hành.

Trọng tâm không phải "hàm có chạy không" mà là **số có đúng nghĩa không**. Một
chỉ số sai còn tệ hơn một chỉ số trống, vì người ta ra quyết định dựa trên nó.
Ba tính chất được bảo vệ ở đây:

  1. Không có dữ liệu thì trả `None`, KHÔNG trả 0 — "0% quy trình hỏng" và
     "chưa chạy lần nào" là hai điều khác hẳn nhau.
  2. Chi phí token phải trả `None` kèm lý do, không được quy đổi từ số ký tự.
  3. Lỗi lặp lại phải đếm được kể cả khi code đã dịch đi vài dòng.
"""
from __future__ import annotations

import json

import pytest

from fleet import metrics, trajectory


@pytest.fixture()
def traj_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(trajectory, "TRAJECTORY_DIR", tmp_path)
    return tmp_path


def _write(traj_dir, *records):
    with (traj_dir / "2026-09-06.ndjson").open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _run_end(task, outcome="success", duration_s=100.0, **extra):
    from datetime import datetime, timezone
    return {"ts": datetime.now(timezone.utc).isoformat(), "event": "run.end",
            "task_id": task, "outcome": outcome, "duration_s": duration_s, **extra}


def _step(task, node="implement", blockers=None, **extra):
    from datetime import datetime, timezone
    return {"ts": datetime.now(timezone.utc).isoformat(), "event": "step",
            "task_id": task, "node": node, "blockers": blockers or [], **extra}


class TestGhiVetChay:
    def test_ghi_ra_file_ndjson(self, traj_dir):
        trajectory.run_started("ENG-1", repo="api")
        trajectory.step("ENG-1", "triage", role="orchestrator", outcome="success")
        lines = list(traj_dir.glob("*.ndjson"))[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["event"] == "run.start"

    def test_ban_ghi_qua_lon_bi_cat(self, traj_dir):
        # Transcript đã nằm ở $FLEET_LOG_DIR/<role>/<session>.ndjson; vết chạy
        # chỉ giữ số đo. Bản ghi khổng lồ là dấu hiệu ai đó nhét nhầm chỗ.
        trajectory._append({"ts": "2026-09-06T00:00:00+00:00", "event": "step",
                            "task_id": "ENG-1", "note": "x" * 20_000})
        rec = json.loads(list(traj_dir.glob("*.ndjson"))[0].read_text(encoding="utf-8"))
        assert rec.get("truncated") is True and "note" not in rec

    def test_note_binh_thuong_thi_giu_nguyen(self, traj_dir):
        trajectory.step("ENG-1", "implement", note="một ghi chú ngắn")
        rec = json.loads(list(traj_dir.glob("*.ndjson"))[0].read_text(encoding="utf-8"))
        assert rec["note"] == "một ghi chú ngắn" and "truncated" not in rec

    def test_khong_ghi_duoc_thi_khong_nem_loi(self, monkeypatch, tmp_path):
        monkeypatch.setattr(trajectory, "TRAJECTORY_DIR", tmp_path / "a")
        monkeypatch.setattr(
            trajectory.Path, "mkdir",
            lambda *a, **k: (_ for _ in ()).throw(OSError("chỉ đọc")),
        )
        trajectory.step("ENG-1", "implement")   # không được ném

    def test_dong_hong_khong_lam_hong_ca_bao_cao(self, traj_dir):
        (traj_dir / "2026-09-06.ndjson").write_text(
            '{"event":"step","task_id":"A"}\n{ dòng cụt\n', encoding="utf-8"
        )
        assert len(list(trajectory.read_all(traj_dir))) == 1


class TestChuKyPhatHien:
    def test_bo_so_dong_khi_lam_chu_ky(self):
        # Cùng một lỗi sau khi code dịch đi vài dòng vẫn phải đếm là lặp lại,
        # nếu không chỉ số "lỗi lặp lại" luôn đẹp một cách giả tạo.
        a = trajectory.finding_signature("BLOCKER", "src/pay.py:41")
        b = trajectory.finding_signature("BLOCKER", "src/pay.py:87")
        assert a == b == "BLOCKER|src/pay.py"


class TestChiSo:
    def test_chua_co_du_lieu_thi_tra_None_khong_tra_0(self, traj_dir):
        m = metrics.collect(directory=traj_dir)
        assert m["total_runs"] == 0
        assert m["long_session_success_rate"]["value"] is None
        assert m["human_intervention_rate"]["value"] is None

    def test_ti_le_phien_dai(self, traj_dir):
        _write(traj_dir,
               _run_end("A", "success", 7200.0),    # dài, thành công
               _run_end("B", "blocked", 7200.0),    # dài, hỏng
               _run_end("C", "success", 10.0))      # ngắn — không tính vào mẫu số
        node = metrics.collect(directory=traj_dir)["long_session_success_rate"]
        assert node["denominator"] == 2 and node["value"] == 50.0

    def test_chi_phi_token_khong_duoc_bia(self, traj_dir):
        _write(traj_dir, _step("A", output_chars=9999), _run_end("A"))
        cost = metrics.collect(directory=traj_dir)["cost_per_task"]
        assert cost["token_cost"] is None and cost["token_cost_reason"]
        assert cost["avg_output_chars"] == 9999      # đại lượng đo được thì vẫn báo

    def test_ti_le_can_thiep_cua_nguoi(self, traj_dir):
        _write(traj_dir,
               _run_end("A", approved_by="sep@x.vn"),
               _run_end("B", escalated=True),
               _run_end("C"))                        # tự chạy trọn, không cần người
        node = metrics.collect(directory=traj_dir)["human_intervention_rate"]
        assert node["numerator"] == 2 and node["denominator"] == 3

    def test_dem_loi_lap_lai_giua_cac_cong_viec(self, traj_dir):
        _write(traj_dir,
               _step("A", "review:reviewer", blockers=["BLOCKER|src/pay.py"]),
               _step("B", "review:reviewer", blockers=["BLOCKER|src/pay.py"]),
               _step("C", "review:reviewer", blockers=["MAJOR|src/web.py"]),
               _run_end("A"), _run_end("B"), _run_end("C"))
        node = metrics.collect(directory=traj_dir)["repeat_findings"]
        assert node["numerator"] == 1 and node["denominator"] == 2
        assert node["top"][0][0] == "BLOCKER|src/pay.py"

    def test_ban_ghi_ngoai_cua_so_thoi_gian_bi_bo(self, traj_dir):
        _write(traj_dir, {"ts": "2020-01-01T00:00:00+00:00", "event": "run.end",
                          "task_id": "CU", "outcome": "success", "duration_s": 9999})
        assert metrics.collect(days=7, directory=traj_dir)["total_runs"] == 0

    def test_bang_markdown_noi_ro_khi_chua_co_du_lieu(self, traj_dir):
        out = metrics.as_markdown(metrics.collect(directory=traj_dir))
        assert "chưa có dữ liệu" in out and "chưa đo được" in out
