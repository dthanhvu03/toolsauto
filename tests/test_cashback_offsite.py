"""D3 (PLAN-094): chép backup ra ngoài máy bằng rclone. rclone giả chép qua thư mục tạm, không gọi mạng."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cashback_bot import insights, offsite
from cashback_bot.backup import run_scheduled_backup
from cashback_bot.db import TrackingRepository

NOW = datetime(2026, 10, 26, 3, 30, tzinfo=timezone.utc)
REMOTE = "fake:"


class FakeRclone:
    """Hiểu đúng 4 lệnh offsite dùng: copyto, lsf --files-only, deletefile. `remote:` → thư mục `root`."""

    def __init__(self, root: Path, corrupt_download: bool = False):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.corrupt_download = corrupt_download
        self.calls: list[list[str]] = []

    def _path(self, ref: str) -> Path:
        return self.root / ref[len(REMOTE):] if ref.startswith(REMOTE) else Path(ref)

    def __call__(self, args, **_kwargs):
        self.calls.append(list(args))
        command = args[1]
        if command == "copyto":
            source, dest = args[2], args[3]
            shutil.copyfile(self._path(source), self._path(dest))
            if self.corrupt_download and source.startswith(REMOTE):
                self._path(dest).write_bytes(b"hong")
            return subprocess.CompletedProcess(args, 0, "", "")
        if command == "lsf":
            names = "\n".join(sorted(p.name for p in self.root.iterdir() if p.is_file()))
            return subprocess.CompletedProcess(args, 0, names + "\n", "")
        if command == "deletefile":
            self._path(args[2]).unlink()
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(args)


def _repo_with_backup(tmp_path) -> tuple[TrackingRepository, Path]:
    repo = TrackingRepository(str(tmp_path / "cashback.sqlite"))
    repo.migrate()
    backups = tmp_path / "backups"
    run_scheduled_backup(Path(repo.path), backups, keep=5, now=NOW)
    return repo, backups


def _offsite_check(repo) -> insights.Check:
    with insights.open_readonly(repo.path) as conn:
        return next(c for c in insights.operations(conn, NOW) if c.code == "offsite")


def test_chep_kiem_tra_lai_va_don_ban_cu(tmp_path):
    repo, backups = _repo_with_backup(tmp_path)
    assert not _offsite_check(repo).ok and "chưa cài" in _offsite_check(repo).value
    fake = FakeRclone(tmp_path / "drive")
    for day in range(35):
        stamp = (NOW - timedelta(days=40 - day)).strftime("%Y%m%dT%H%M%SZ")
        (fake.root / f"cashback-{stamp}.sqlite").write_bytes(b"cu")
    (fake.root / "ghi-chu.txt").write_text("không phải backup")
    assert offsite.run(repo, backups, REMOTE, keep=30, runner=fake, now=NOW.timestamp())
    names = sorted(p.name for p in fake.root.iterdir())
    latest = next(backups.iterdir()).name
    assert latest in names and "ghi-chu.txt" in names, "chỉ xoá file đúng mẫu tên backup"
    assert len([n for n in names if n.startswith("cashback-")]) == 30
    assert repo.get_state(offsite.FILE_KEY) == latest and repo.get_state(offsite.ERROR_KEY) == ""
    assert [c[1] for c in fake.calls[:2]] == ["copyto", "copyto"], "chép lên rồi tải lại để so"
    assert _offsite_check(repo).ok


def test_ban_tai_lai_khong_khop_thi_bao_loi(tmp_path):
    repo, backups = _repo_with_backup(tmp_path)
    assert not offsite.run(repo, backups, REMOTE, runner=FakeRclone(tmp_path / "drive", corrupt_download=True))
    assert "không khớp" in repo.get_state(offsite.ERROR_KEY) and repo.get_state(offsite.OK_KEY) is None
    check = _offsite_check(repo)
    assert not check.ok and "không khớp" in check.value


def test_chua_cai_rclone_hoac_chua_co_backup(tmp_path):
    repo, backups = _repo_with_backup(tmp_path)

    def missing(*_args, **_kwargs):
        raise FileNotFoundError("rclone")

    assert not offsite.run(repo, backups, REMOTE, runner=missing)
    assert repo.get_state(offsite.ERROR_KEY) == "chưa cài rclone"
    assert not offsite.run(repo, tmp_path / "trong", REMOTE, runner=FakeRclone(tmp_path / "drive"))
    assert repo.get_state(offsite.ERROR_KEY) == "chưa có bản backup nào trong máy"


def test_rclone_loi_chi_giu_dong_cuoi(tmp_path):
    repo, backups = _repo_with_backup(tmp_path)

    def failing(args, **_kwargs):
        raise subprocess.CalledProcessError(1, args, "", "dòng 1\nFailed to copy: googleapi: Error 403")

    assert not offsite.run(repo, backups, REMOTE, runner=failing)
    assert repo.get_state(offsite.ERROR_KEY) == "rclone copyto lỗi: Failed to copy: googleapi: Error 403"
