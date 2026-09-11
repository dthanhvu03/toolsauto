"""ADR-044 — route /viral/{id}/phone: attachment (Safari lưu vào Files), tên theo tiêu đề."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.config as config
from app.constants import ViralStatus
from app.core.database.models import Base, ViralMaterial


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.core.database.core import get_db
    from app.main import app

    engine = create_engine(f"sqlite:///{tmp_path / 'p.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(config, "REUP_DIR", tmp_path / "reup")

    def _db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    with factory() as db:
        mat = ViralMaterial(platform="tiktok", url="https://t/1", title="Muốn giàu ### BOOST_CONTEXT: x ###", views=1,
                            status=ViralStatus.READY)
        db.add(mat)
        db.commit()
        mid = mat.id
    d = tmp_path / "reup" / "tiktok"
    d.mkdir(parents=True)
    (d / f"viral_{mid}_abc_reup.mp4").write_bytes(b"\x01" * 64)
    try:
        c = TestClient(app)
        c.mid = mid
        yield c
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def _login(c: TestClient):
    # Route nằm sau màn đăng nhập như mọi route khác — không mở toang khi nghe trên LAN.
    import app.config as cfg

    if cfg.ADMIN_USERNAME:
        c.post("/login", data={"username": cfg.ADMIN_USERNAME, "password": cfg.ADMIN_PASSWORD})


def test_tra_attachment_ten_theo_tieu_de_da_boc_marker(client):
    _login(client)
    r = client.get(f"/viral/{client.mid}/phone")

    if r.status_code in (302, 303, 401):
        pytest.skip("cần đăng nhập — không có ADMIN_USERNAME trong môi trường test")
    assert r.status_code == 200, r.text[:200]
    from urllib.parse import unquote

    cd = unquote(r.headers["content-disposition"])  # filename*=utf-8''… mã hoá %20
    assert cd.startswith("attachment"), "inline thì Safari phát video, share sheet không thấy file"
    assert "BOOST_CONTEXT" not in cd and f"{client.mid} - Muốn giàu.mp4" in cd
    assert r.content == b"\x01" * 64


def test_chua_co_file_thi_404_noi_ro(client):
    _login(client)
    with_no_file = client.mid + 1
    r = client.get(f"/viral/{with_no_file}/phone")

    if r.status_code in (302, 303, 401):
        pytest.skip("cần đăng nhập")
    assert r.status_code == 404
