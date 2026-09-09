"""
ADR-032 — chọn mốc cắt bằng một cú bấm: dải khung hình + giữ file gốc.

ADR-031 cho chọn mốc, nhưng thao tác thật vẫn phiền: xem hết video 9 phút để tìm chỗ hay, gõ
số giây, rồi tải lại cả trăm MB. ADR này bỏ cả ba chỗ đó.
"""
from __future__ import annotations

import os
import subprocess

import pytest

from app.features.viral_intake.service import ViralService


# ── mốc giây của 12 khung ────────────────────────────────────────────────────


def test_muoi_hai_moc_trai_deu_va_tranh_hai_dau():
    """Bỏ 2% đầu/cuối cho khỏi dính màn đen hoặc cảnh chưa vào."""
    secs = ViralService.source_frame_seconds(573)

    assert len(secs) == 12
    assert secs == sorted(secs), "phải tăng dần"
    assert secs[0] >= 11 and secs[-1] <= 562
    # video 573s có cá ở giây ~320 ⇒ phải có khung rơi gần đó
    assert any(300 <= s <= 340 for s in secs)


@pytest.mark.parametrize("duration", [0, -5])
def test_do_dai_vo_ly_thi_khong_co_khung_nao(duration):
    assert ViralService.source_frame_seconds(duration) == []


# ── tìm file gốc: KHÔNG được nhầm với bản đã cắt ─────────────────────────────


@pytest.fixture
def reup_dir(tmp_path, monkeypatch):
    import app.config as config

    monkeypatch.setattr(config, "REUP_DIR", tmp_path)
    (tmp_path / "tiktok").mkdir()
    return tmp_path


def test_tim_file_goc_bo_qua_ban_da_cat(reup_dir):
    """
    Chỗ nguy hiểm nhất: lẫn bản `_reup.mp4` vào thì cắt lại sẽ cắt trên chính bản đã cắt còn
    90 giây — mất đúng đoạn Owner muốn, mà không có lỗi nào báo.
    """
    d = reup_dir / "tiktok"
    (d / "viral_7_abc.mp4").write_bytes(b"x" * 100)
    (d / "viral_7_abc_reup.mp4").write_bytes(b"y" * 100)

    found = ViralService.find_source_path(7, "tiktok")

    assert found is not None and found.endswith("viral_7_abc.mp4")
    assert "_reup" not in found


def test_chi_con_ban_da_cat_thi_coi_nhu_khong_co_goc(reup_dir):
    (reup_dir / "tiktok" / "viral_8_abc_reup.mp4").write_bytes(b"y" * 100)

    assert ViralService.find_source_path(8, "tiktok") is None


def test_file_rong_khong_tinh_la_co(reup_dir):
    (reup_dir / "tiktok" / "viral_9_abc.mp4").write_bytes(b"")

    assert ViralService.find_source_path(9, "tiktok") is None


def test_bo_qua_duoi_file_khong_phai_video(reup_dir):
    (reup_dir / "tiktok" / "viral_10_abc.json").write_text("{}", encoding="utf-8")

    assert ViralService.find_source_path(10, "tiktok") is None


# ── tên file khung tự mô tả số giây ─────────────────────────────────────────


def test_doc_lai_duoc_giay_tu_ten_file_ke_ca_khi_video_goc_da_bi_don(reup_dir):
    """Số giây nằm trong TÊN FILE nên không cần cột DB, không cần đo lại độ dài."""
    d = reup_dir / "frames" / "77"
    d.mkdir(parents=True)
    for idx, sec in ((0, 11), (8, 332), (11, 515)):
        (d / f"f{idx:02d}_{sec}.jpg").write_bytes(b"jpg-gia")

    assert ViralService.list_source_frames(77) == [(0, 11), (8, 332), (11, 515)]
    assert ViralService.source_frame_path(77, 8).endswith("f08_332.jpg")


def test_khung_rong_bi_loai(reup_dir):
    d = reup_dir / "frames" / "78"
    d.mkdir(parents=True)
    (d / "f00_11.jpg").write_bytes(b"")

    assert ViralService.list_source_frames(78) == []
    assert ViralService.source_frame_path(78, 0) is None


def test_chua_trich_khung_thi_tra_rong_khong_nem(reup_dir):
    assert ViralService.list_source_frames(999) == []


# ── trích khung THẬT bằng ffmpeg ────────────────────────────────────────────


def test_trich_khung_that_bang_ffmpeg(reup_dir, tmp_path):
    """Chạy ffmpeg thật: video 60 giây ⇒ 12 ảnh jpg có nội dung, tên mang đúng số giây."""
    video = tmp_path / "src.mp4"
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "testsrc=size=160x284:rate=10:duration=60",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "35", str(video),
        ],
        capture_output=True, timeout=180,
    )
    if not video.is_file() or video.stat().st_size == 0:
        pytest.skip("máy không có ffmpeg dùng được")

    made = ViralService.ensure_source_frames(11, str(video))

    assert len(made) == 12
    for idx, sec in made:
        path = ViralService.source_frame_path(11, idx)
        assert path and os.path.getsize(path) > 0
        assert path.endswith(f"_{sec}.jpg")
    assert ViralService.list_source_frames(11) == made


def test_video_khong_ton_tai_thi_tra_rong_khong_nem(reup_dir):
    assert ViralService.ensure_source_frames(12, "/khong/co/file.mp4") == []


def test_khong_suy_duong_dan_ffprobe_bang_replace():
    """
    Hồi quy: bản đầu suy ffprobe bằng `resolve_ffmpeg().replace("ffmpeg", "ffprobe")`. Nó thay
    cả TÊN THƯ MỤC — `…/Programs/ffmpeg/bin/ffmpeg.EXE` thành `…/Programs/ffprobe/bin/…` —
    nên ra đường dẫn không tồn tại. `probe_duration` nuốt lỗi, trả 0, và cả dải khung hình im
    lặng biến mất. Repo có sẵn `ffmpeg_path.ffprobe_bin()`.
    """
    import pathlib

    from app.features.viral_intake import service

    code = pathlib.Path(service.__file__).read_text(encoding="utf-8")

    assert 'replace("ffmpeg", "ffprobe")' not in code
    assert "ffmpeg_path.ffprobe_bin()" in code


def test_probe_duration_doc_duoc_do_dai_that(tmp_path):
    video = tmp_path / "d.mp4"
    subprocess.run(
        [
            "ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi",
            "-i", "testsrc=size=64x64:rate=5:duration=8",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "40", str(video),
        ],
        capture_output=True, timeout=120,
    )
    if not video.is_file() or video.stat().st_size == 0:
        pytest.skip("máy không có ffmpeg dùng được")

    assert 7.0 <= ViralService.probe_duration(str(video)) <= 9.0


def test_probe_duration_file_hong_thi_tra_0_khong_nem():
    assert ViralService.probe_duration("/khong/co/file.mp4") == 0.0


# ── processor: dùng lại file gốc, chỉ xoá khi hết hạn giữ ───────────────────


def _processor_code() -> str:
    import pathlib

    from app.features.viral_intake import processor

    return pathlib.Path(processor.__file__).read_text(encoding="utf-8")


def test_processor_dung_lai_file_goc_truoc_khi_tai():
    code = _processor_code()
    moc_tim = "ViralService.find_source_path(mat.id, mat.platform)"
    moc_tai = "# Tải video bằng yt-dlp vào thư mục platform riêng"

    assert moc_tim in code
    assert code.index(moc_tim) < code.index(moc_tai), "phải kiểm file có sẵn TRƯỚC khi tải"


def test_processor_trich_khung_truoc_khi_co_the_xoa_goc():
    """Trích sau khi xoá thì không còn gì để trích — thứ tự là bắt buộc."""
    code = _processor_code()

    assert code.index("ViralService.ensure_source_frames(mat.id, media_path)") < code.index("if _keep_days <= 0:")


def test_doc_o_cai_dat_hong_thi_XOA_chu_khong_giu():
    """Mặc định an toàn phải nghiêng về xoá — giữ nhầm thì phình đĩa âm thầm."""
    code = _processor_code()
    block = code.split("viral.keep_source_days", 1)[1][:200]

    assert "_keep_days = 0" in block


# ── dọn file gốc quá hạn ────────────────────────────────────────────────────


def _fake_keep_days(monkeypatch, days):
    from app.features.system_panel.workers import maintenance

    monkeypatch.setattr(maintenance.runtime_settings, "get_int", lambda key, default=0, db=None: days)


def test_don_file_goc_qua_han_khong_dung_ban_da_cat(reup_dir, monkeypatch):
    import time

    from app.features.system_panel.workers import maintenance

    _fake_keep_days(monkeypatch, 7)
    d = reup_dir / "tiktok"
    cu, moi, reup = d / "viral_1_old.mp4", d / "viral_2_new.mp4", d / "viral_1_old_reup.mp4"
    for f in (cu, moi, reup):
        f.write_bytes(b"x" * 100)
    qua_han = time.time() - 8 * 86400
    os.utime(cu, (qua_han, qua_han))
    os.utime(reup, (qua_han, qua_han))

    removed = maintenance.cleanup_old_source_files(db=None)

    assert removed == 1
    assert not cu.exists(), "file gốc quá hạn phải bị xoá"
    assert moi.exists(), "file gốc còn hạn phải giữ"
    assert reup.exists(), "bản _reup là thứ Owner đăng — không được đụng"


def test_dat_0_ngay_thi_khong_don_gi_o_day(reup_dir, monkeypatch):
    import time

    from app.features.system_panel.workers import maintenance

    _fake_keep_days(monkeypatch, 0)
    f = reup_dir / "tiktok" / "viral_1_old.mp4"
    f.write_bytes(b"x" * 100)
    qua_han = time.time() - 99 * 86400
    os.utime(f, (qua_han, qua_han))

    assert maintenance.cleanup_old_source_files(db=None) == 0
    assert f.exists(), "0 ngày nghĩa là đã xoá ngay lúc xử lý, ở đây không còn gì để dọn"


def test_don_file_hong_thi_khong_nem(monkeypatch):
    from app.features.system_panel.workers import maintenance

    def boom(*a, **k):
        raise RuntimeError("settings chết")

    monkeypatch.setattr(maintenance.runtime_settings, "get_int", boom)

    assert maintenance.cleanup_old_source_files(db=None) == 0
