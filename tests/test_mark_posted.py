"""
ADR-042 — "Đã đăng" là một trạng thái, thư mục là hệ quả.

Chạy thật trên SQLite + đĩa tạm + thư mục Drive giả: bấm Đã đăng ⇒ trạng thái, file cục bộ,
bản Drive đúng chỗ; bấm Chưa đăng ⇒ về nguyên trạng. Và cái quan trọng nhất: chống trùng
(ADR-024) phải soi cả video đã đăng.
"""
from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
from app.constants import ViralStatus
from app.core.database.models import Account, Job, ViralMaterial
from app.core.storage import offsite
from app.features.viral_intake.dedup import DEDUP_STATUSES, find_duplicate
from app.features.viral_intake.service import ViralService


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'posted.sqlite'}")
    Account.__table__.create(engine)
    ViralMaterial.__table__.create(engine)
    Job.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def disks(tmp_path, monkeypatch):
    """REUP_DIR tạm + Drive giả (root = tmp/drive, bật chép video)."""
    reup = tmp_path / "reup"
    drive = tmp_path / "drive"
    monkeypatch.setattr(config, "REUP_DIR", reup)
    monkeypatch.setattr(offsite, "get_root", lambda: drive)
    return reup, drive


def _ready(session_factory, reup, drive, *, title="Câu cá đêm", with_drive=True, **over) -> int:
    with session_factory() as db:
        base = dict(platform="tiktok", url=f"https://t/{title}", title=title, views=5, status=ViralStatus.READY)
        base.update(over)
        mat = ViralMaterial(**base)
        db.add(mat)
        db.commit()
        mid = mat.id
    d = reup / "tiktok"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"viral_{mid}_abc.mp4").write_bytes(b"\x00" * 100)  # gốc
    (d / f"viral_{mid}_abc_reup.mp4").write_bytes(b"\x01" * 100)  # đã cắt
    if with_drive:
        m = drive / "videos" / "2026-09"
        m.mkdir(parents=True, exist_ok=True)
        (m / f"{mid} - {title}.mp4").write_bytes(b"\x01" * 100)
    return mid


# ── đã đăng ─────────────────────────────────────────────────────────────────


def test_da_dang_doi_trang_thai_va_doi_ca_hai_file(session_factory, disks):
    reup, drive = disks
    mid = _ready(session_factory, reup, drive)

    with session_factory() as db:
        ok, msg = ViralService.mark_posted(db, mid)

        assert ok, msg
        mat = db.get(ViralMaterial, mid)
        assert mat.status == ViralStatus.POSTED and mat.posted_at

    assert (reup / "tiktok" / "da-dang" / f"viral_{mid}_abc_reup.mp4").is_file()
    assert not (reup / "tiktok" / f"viral_{mid}_abc_reup.mp4").exists()
    assert (reup / "tiktok" / f"viral_{mid}_abc.mp4").is_file(), "file GỐC không đụng — còn cắt lại được"
    assert (drive / "videos" / "2026-09" / "Đã đăng" / f"{mid} - Câu cá đêm.mp4").is_file(), "Drive: cùng tháng, không gom chung"
    assert "da-dang" in msg and "Đã đăng" in msg, "tin phải nói file nằm đâu"


def test_gui_lai_van_tim_thay_file_trong_da_dang(session_factory, disks):
    """Nút Gửi lại và Tải file dùng `find_reup_path` — dời file rồi mà không thấy là nút chết."""
    reup, drive = disks
    mid = _ready(session_factory, reup, drive)
    with session_factory() as db:
        ViralService.mark_posted(db, mid)

    found = ViralService.find_reup_path(mid, "tiktok")

    assert found and os.path.basename(os.path.dirname(found)) == "da-dang"


def test_khong_co_ban_drive_van_ghi_nhan_da_dang(session_factory, disks):
    """Drive là bản phụ. Không thấy bản chép không được từ chối ghi 'đã đăng'."""
    reup, drive = disks
    mid = _ready(session_factory, reup, drive, with_drive=False)

    with session_factory() as db:
        ok, msg = ViralService.mark_posted(db, mid)

        assert ok
        assert db.get(ViralMaterial, mid).status == ViralStatus.POSTED
    assert "không thấy bản chép" in msg


def test_drive_tat_thi_im_ve_drive(session_factory, disks, monkeypatch):
    reup, drive = disks
    monkeypatch.setattr(offsite, "get_root", lambda: None)
    mid = _ready(session_factory, reup, drive)

    with session_factory() as db:
        ok, msg = ViralService.mark_posted(db, mid)

    assert ok and "Drive" not in msg


@pytest.mark.parametrize("status", [ViralStatus.NEW, ViralStatus.PROCESSING, ViralStatus.FAILED, ViralStatus.DUPLICATE])
def test_chua_san_sang_thi_khong_danh_dau_duoc(session_factory, disks, status):
    reup, drive = disks
    mid = _ready(session_factory, reup, drive, status=status)

    with session_factory() as db:
        ok, msg = ViralService.mark_posted(db, mid)

        assert not ok and status in msg


def test_danh_dau_hai_lan_thi_bao(session_factory, disks):
    reup, drive = disks
    mid = _ready(session_factory, reup, drive)
    with session_factory() as db:
        assert ViralService.mark_posted(db, mid)[0]

        ok, msg = ViralService.mark_posted(db, mid)

        assert not ok and "rồi" in msg


def test_phan_con_da_dang_thi_tin_ghi_phan_may(session_factory, disks):
    reup, drive = disks
    mid = _ready(session_factory, reup, drive, parent_material_id=1, part_index=2, part_total=3)
    with session_factory() as db:
        ok, msg = ViralService.mark_posted(db, mid)

    assert ok and "Phần 2/3" in msg


# ── chưa đăng (bấm nhầm) ────────────────────────────────────────────────────


def test_bam_nham_thi_ve_nguyen_trang(session_factory, disks):
    reup, drive = disks
    mid = _ready(session_factory, reup, drive)
    with session_factory() as db:
        ViralService.mark_posted(db, mid)

        ok, msg = ViralService.unmark_posted(db, mid)

        assert ok, msg
        mat = db.get(ViralMaterial, mid)
        assert mat.status == ViralStatus.READY and mat.posted_at is None

    assert (reup / "tiktok" / f"viral_{mid}_abc_reup.mp4").is_file()
    assert not (reup / "tiktok" / "da-dang" / f"viral_{mid}_abc_reup.mp4").exists()
    assert (drive / "videos" / "2026-09" / f"{mid} - Câu cá đêm.mp4").is_file()
    assert not (drive / "videos" / "2026-09" / "Đã đăng" / f"{mid} - Câu cá đêm.mp4").exists()


def test_chua_dang_ma_bam_chua_dang_thi_bao(session_factory, disks):
    reup, drive = disks
    mid = _ready(session_factory, reup, drive)
    with session_factory() as db:
        ok, msg = ViralService.unmark_posted(db, mid)

        assert not ok and "READY" in msg


# ── chống trùng phải soi cả POSTED ─────────────────────────────────────────


def test_POSTED_nam_trong_nhom_chong_trung():
    """Lý do quan trọng nhất để trạng thái này tồn tại: thứ đã đăng không được lọt vào lại."""
    assert ViralStatus.POSTED in DEDUP_STATUSES


def test_ban_copy_cua_video_da_dang_bi_bat(session_factory, disks):
    reup, drive = disks
    mid = _ready(session_factory, reup, drive, content_hash="abc123")
    with session_factory() as db:
        ViralService.mark_posted(db, mid)
        moi = ViralMaterial(platform="tiktok", url="https://t/copy", title="copy", views=1, status=ViralStatus.NEW,
                            content_hash="abc123")
        db.add(moi)
        db.commit()

        dup = find_duplicate(db, content_hash="abc123", phash_map={}, exclude_id=moi.id, max_distance=8)

        assert dup and dup[0] == mid, "video đã đăng phải bắt được bản copy của chính nó"


# ── /dadang ────────────────────────────────────────────────────────────────


def test_list_posted_moi_nhat_len_dau(session_factory, disks):
    reup, drive = disks
    a = _ready(session_factory, reup, drive, title="a", with_drive=False)
    b = _ready(session_factory, reup, drive, title="b", with_drive=False)
    with session_factory() as db:
        ViralService.mark_posted(db, b)
        db.get(ViralMaterial, b).posted_at = 100
        db.commit()
        ViralService.mark_posted(db, a)
        db.get(ViralMaterial, a).posted_at = 200
        db.commit()

        assert [m.id for m in ViralService.list_posted(db)] == [a, b]


# ── tin video có nút ────────────────────────────────────────────────────────


def test_tin_video_san_sang_mang_nut_da_dang():
    from types import SimpleNamespace

    from app.core.notifier import formatting as nf

    buttons = nf.material_ready_buttons(SimpleNamespace(id=12))

    assert buttons == [[{"text": "✅ Đã đăng", "callback_data": "dadang:12"}]]


def test_notify_material_ready_truyen_nut_xuong_kenh(monkeypatch):
    from types import SimpleNamespace

    from app.core.notifier import service as ns

    seen = {}
    monkeypatch.setattr(ns.NotifierService, "_broadcast_video", classmethod(lambda cls, p, c, b=None: seen.update(video=(c, b))))
    monkeypatch.setattr(ns.NotifierService, "_broadcast_with_buttons", classmethod(lambda cls, m, b: seen.update(text=(m, b))))
    monkeypatch.setattr(ns.os.path, "exists", lambda p: True)
    monkeypatch.setattr(ns.media_thumb, "telegram_video_within_size_limit", lambda p: True)
    monkeypatch.setattr("app.core.media.thumbnail.media_info", lambda p: {"duration": 10})
    mat = SimpleNamespace(id=7, platform="tiktok", title="x", views=1, ai_caption=None, ai_hashtags_list=[],
                          ai_caption_error=None, clip_start_sec=None)

    ns.NotifierService.notify_material_ready(mat, "/x/a.mp4")

    assert seen["video"][1] == [[{"text": "✅ Đã đăng", "callback_data": "dadang:7"}]]
