"""Kiểm thử lệnh ngoài (git/gh/chown) trong các nút của đồ thị.

Hai tính chất được bảo vệ ở đây:

  1. **Không chặn event loop.** server.py phục vụ mọi run trên MỘT event loop.
     Một `git fetch` đồng bộ mất vài phút là cả server treo theo: các run khác,
     `/ok`, `/runs/{id}` đều im. Lệnh ngoài phải đi qua `graph._run`.
  2. **Lỗi vẫn là lỗi.** Chuyển sang async không được nuốt mã thoát khác 0:
     fetch/worktree/chown/push/gh hỏng thì nút phải ném lỗi và DỪNG ngay đó,
     không chạy tiếp các bước sau như thể mọi việc suôn sẻ.

Không cần git thật. Test của các nút thay `asyncio.create_subprocess_exec` bằng
bản giả ghi lại argv và trả mã thoát theo kịch bản. Vài test của `_run` chạy
tiến trình con thật là chính trình thông dịch Python: bản giả chỉ chứng minh ta
gọi đúng API, còn "giết khi hết giờ" và "event loop vẫn chạy" phải thấy trên
asyncio thật mới tính.
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time

import pytest

from fleet import graph, memory, trajectory

ROOT = "/srv/repos"
REPO = f"{ROOT}/api"
WT = f"{ROOT}/wt-eng-1"
HEAD_MASTER = (0, b"origin/master\n", b"")      # symbolic-ref đọc được origin/HEAD

STATE = {"task_id": "ENG-1", "title": "Thêm rate limit", "repo": REPO, "profile": "engineering"}
PR_STATE = {"task_id": "ENG-1", "title": "Thêm rate limit", "worktree": WT,
            "branch": "feat/eng-1", "risk": "standard", "findings": []}


class FakeProc:
    """Phần giao diện của `asyncio.subprocess.Process` mà `graph._run` dùng."""

    def __init__(self, rc: int, out: bytes, err: bytes, *, piped: bool, hang: bool) -> None:
        self._rc, self._hang = rc, hang
        self._out, self._err = (out, err) if piped else (None, None)
        self.returncode: int | None = None
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.Event().wait()        # treo cho tới khi bị huỷ
        self.returncode = self._rc
        return self._out, self._err

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int | None:
        return self.returncode


class FakeExec:
    """Thay `asyncio.create_subprocess_exec`: ghi lại argv/cwd, không tạo tiến trình nào.

    `results[i]` = (mã thoát, stdout, stderr) của lời gọi thứ i; không khai thì
    thành công với đầu ra rỗng.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.cwds: list[str | None] = []
        self.procs: list[FakeProc] = []
        self.results: dict[int, tuple[int, bytes, bytes]] = {}
        self.hang = False

    async def __call__(self, *argv, cwd=None, stdout=None, stderr=None, **_):
        rc, out, err = self.results.get(len(self.calls), (0, b"", b""))
        self.calls.append(list(argv))
        self.cwds.append(cwd)
        self.procs.append(FakeProc(rc, out, err, piped=stdout is not None, hang=self.hang))
        return self.procs[-1]


@pytest.fixture()
def fake_exec(monkeypatch):
    fake = FakeExec()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake)
    return fake


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    """Không ghi bộ nhớ/vết chạy ra /srv, /var/log của máy chạy test."""
    monkeypatch.setattr(memory, "MEMORY_DIR", tmp_path / "memory")
    monkeypatch.setattr(trajectory, "TRAJECTORY_DIR", tmp_path / "trajectory")
    monkeypatch.setattr(graph, "REPO_ROOT", ROOT)
    return tmp_path


def _prepare_calls(base_ref: str = "origin/master") -> list[list[str]]:
    """Đúng các lệnh `prepare` phải chạy, đúng thứ tự."""
    owner = f"{graph.WORKTREE_OWNER_UID}:{graph.WORKTREE_OWNER_GID}"
    return [
        ["git", "-C", REPO, "fetch", "--prune", "origin"],
        ["git", "-C", REPO, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"],
        ["git", "-C", REPO, "worktree", "add", "-B", "feat/eng-1", WT, base_ref],
        ["chown", "-R", owner, REPO],
        ["chown", "-R", owner, WT],
    ]


class TestRun:
    async def test_ma_thoat_khac_0_thi_nem_loi(self):
        argv = [sys.executable, "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"]
        with pytest.raises(subprocess.CalledProcessError) as exc:
            await graph._run(argv, capture=True)
        assert exc.value.returncode == 3
        assert exc.value.cmd == argv
        assert exc.value.stderr == "boom"       # chuỗi, như capture_output=True, text=True

    async def test_het_gio_thi_giet_tien_trinh_con(self, fake_exec):
        fake_exec.hang = True
        with pytest.raises(subprocess.TimeoutExpired):
            await graph._run(["git", "-C", REPO, "fetch", "--prune", "origin"], timeout_s=0.05)
        assert fake_exec.procs[0].killed

    async def test_het_gio_voi_tien_trinh_that_khong_treo(self):
        t0 = time.monotonic()
        with pytest.raises(subprocess.TimeoutExpired):
            await graph._run([sys.executable, "-c", "import time; time.sleep(30)"], timeout_s=0.2)
        # Không phải chờ đủ 30s: kill + wait trên asyncio thật trả về ngay.
        assert time.monotonic() - t0 < 10

    async def test_bi_huy_thi_giet_tien_trinh_con(self, fake_exec):
        fake_exec.hang = True
        task = asyncio.create_task(graph._run(["git", "-C", WT, "push", "-u", "origin", "x"]))
        await asyncio.sleep(0.05)               # để task chạy tới communicate() rồi treo ở đó
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        # Run bị huỷ thì `git push` phải chết theo, không đẩy nhánh sau lưng ai.
        assert fake_exec.procs[0].killed

    async def test_khong_chan_event_loop(self):
        # Lý do `_run` tồn tại. Bản subprocess.run cũ cho ra đúng 0 nhịp ở đây.
        ticks = 0

        async def heartbeat():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.01)
                ticks += 1

        hb = asyncio.create_task(heartbeat())
        try:
            await graph._run([sys.executable, "-c", "import time; time.sleep(0.5)"])
        finally:
            hb.cancel()
        assert ticks >= 3


class TestPrepare:
    async def test_chay_dung_lenh_dung_thu_tu(self, fake_exec):
        fake_exec.results = {1: HEAD_MASTER}
        out = await graph.prepare(STATE)
        assert fake_exec.calls == _prepare_calls()
        assert out["branch"] == "feat/eng-1" and out["worktree"] == WT

    async def test_khong_doc_duoc_origin_head_thi_lui_ve_origin_main(self, fake_exec):
        # symbolic-ref chạy với check=False: hỏng ở bước này KHÔNG phải lỗi.
        fake_exec.results = {1: (1, b"", b"fatal: ref origin/HEAD is not a symbolic ref")}
        await graph.prepare(STATE)
        assert fake_exec.calls == _prepare_calls(base_ref="origin/main")

    @pytest.mark.parametrize(
        "fail_at", [0, 2, 3, 4], ids=["fetch", "worktree-add", "chown-repo", "chown-worktree"]
    )
    async def test_lenh_hong_thi_nem_loi_va_dung_ngay(self, fake_exec, isolated, fail_at):
        fake_exec.results = {1: HEAD_MASTER, fail_at: (128, b"", b"fatal: boom")}
        with pytest.raises(subprocess.CalledProcessError) as exc:
            await graph.prepare(STATE)
        assert exc.value.returncode == 128
        assert exc.value.cmd == _prepare_calls()[fail_at]
        # Dừng ngay tại bước hỏng: không lệnh nào sau nó được chạy...
        assert fake_exec.calls == _prepare_calls()[: fail_at + 1]
        # ...kể cả sổ sách — memory/trajectory chỉ mở SAU khi mọi lệnh đã thành công.
        assert not (isolated / "memory").exists()
        assert not (isolated / "trajectory").exists()


class TestOpenPr:
    async def test_push_hong_thi_khong_tao_pr(self, fake_exec):
        fake_exec.results = {0: (1, b"", b"")}
        with pytest.raises(subprocess.CalledProcessError):
            await graph.open_pr(PR_STATE)
        assert fake_exec.calls == [["git", "-C", WT, "push", "-u", "origin", "feat/eng-1"]]

    async def test_gh_hong_thi_nem_loi_kem_stderr(self, fake_exec):
        fake_exec.results = {1: (1, b"", "đã có PR cho nhánh này".encode())}
        with pytest.raises(subprocess.CalledProcessError) as exc:
            await graph.open_pr(PR_STATE)
        assert exc.value.stderr == "đã có PR cho nhánh này"

    async def test_thanh_cong_tra_ve_url_pr(self, fake_exec):
        fake_exec.results = {1: (0, b"https://github.com/o/r/pull/7\n", b"")}
        out = await graph.open_pr(PR_STATE)
        assert out == {"pr_url": "https://github.com/o/r/pull/7", "outcome": "success"}
        assert fake_exec.calls[1][:3] == ["gh", "pr", "create"]
        assert fake_exec.cwds[1] == WT          # gh suy ra repo từ thư mục làm việc
