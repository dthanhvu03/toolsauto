"""File reup phát qua /buffer-media — không login, chữ ký cố định, chỉ khi base là https."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.config as config
from app.features.buffer.adapter import public_media_url
from app.features.buffer.client import BufferError
from app.features.buffer.media import media_sig, public_reup_url


@pytest.fixture
def reup_file(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "REUP_DIR", tmp_path / "reup")
    monkeypatch.setattr(config, "SECRET_KEY", "test-secret")
    d = tmp_path / "reup" / "tiktok"
    d.mkdir(parents=True)
    (d / "viral_7_abc_reup.mp4").write_bytes(b"reup-bytes")
    return 7


def test_khong_co_chu_ky_thi_404(reup_file):
    from app.main import app

    r = TestClient(app).get(f"/buffer-media/{reup_file}/sai.mp4")
    assert r.status_code == 404


def test_chu_ky_dung_tra_file_khong_can_dang_nhap(reup_file):
    from app.main import app

    sig = media_sig(reup_file)
    r = TestClient(app).get(f"/buffer-media/{reup_file}/{sig}.mp4")
    assert r.status_code == 200, r.text[:200]
    assert r.content == b"reup-bytes"
    assert r.headers["content-type"].startswith("video/mp4")


def test_head_tra_header_video_khong_can_dang_nhap(reup_file):
    """Buffer đọc video bằng HEAD. 405 thì họ báo không đọc được URL."""
    from app.main import app

    sig = media_sig(reup_file)
    r = TestClient(app).head(f"/buffer-media/{reup_file}/{sig}.mp4")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("video/mp4")
    assert r.headers["content-length"] == str(len(b"reup-bytes"))
    assert r.content == b""


def test_base_http_khong_tao_url(reup_file, monkeypatch):
    monkeypatch.setattr(
        "app.features.buffer.media.media_base",
        lambda: "http://192.168.1.10:8002",
    )
    assert public_reup_url(reup_file) is None


def test_base_https_tao_url_on_dinh(reup_file, monkeypatch):
    monkeypatch.setattr(
        "app.features.buffer.media.media_base",
        lambda: "https://media.example.com",
    )
    url = public_reup_url(reup_file)
    assert url == f"https://media.example.com/buffer-media/{reup_file}/{media_sig(reup_file)}.mp4"
    assert public_reup_url(reup_file) == url


def test_job_local_dung_url_reup_khi_co_base(reup_file, monkeypatch):
    monkeypatch.setattr(
        "app.features.buffer.media.media_base",
        lambda: "https://media.example.com",
    )
    job = SimpleNamespace(
        media_path="/home/vu/toolsauto/storage/media/reup/tiktok/viral_7_abc_reup.mp4",
        processed_media_path=None,
        viral_material_id=reup_file,
    )
    assert public_media_url(job).endswith(f"/{reup_file}/{media_sig(reup_file)}.mp4")


def test_job_local_khong_co_material_van_loi(monkeypatch):
    monkeypatch.setattr("app.features.buffer.media.media_base", lambda: "https://media.example.com")
    job = SimpleNamespace(media_path="/tmp/clip.mp4", processed_media_path=None, viral_material_id=None)
    with pytest.raises(BufferError, match="file local"):
        public_media_url(job)
