"""/sansang chỉ liệt kê video READY còn file reup."""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.bootstrap_hooks import register_feature_hooks
from app.constants import JobStatus, ViralStatus
from app.core import feature_hooks
from app.core.database.models import Base, Job, ViralMaterial
from app.features.viral_intake.service import ViralService


def test_sansang_bo_video_het_file(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    db.add(ViralMaterial(platform="tiktok", url="https://t/old", title="het file", status=ViralStatus.READY))
    db.add(ViralMaterial(platform="tiktok", url="https://t/new", title="con file", status=ViralStatus.READY))
    db.commit()
    ids = {m.url: m.id for m in db.query(ViralMaterial).all()}

    def _path(material_id, platform=None):
        if material_id == ids["https://t/new"]:
            return "/tmp/viral_reup.mp4"
        return None

    monkeypatch.setattr(ViralService, "find_reup_path", staticmethod(_path))
    register_feature_hooks()
    rows = feature_hooks.call("viral.list_materials", db, "READY", 10)
    db.close()
    engine.dispose()
    assert [r["id"] for r in rows] == [ids["https://t/new"]]


def test_sansang_bo_video_da_xep_buffer(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    queued = ViralMaterial(platform="tiktok", url="https://t/queued", title="da xep", status=ViralStatus.READY)
    waiting = ViralMaterial(platform="tiktok", url="https://t/wait", title="chua xep", status=ViralStatus.READY)
    cancelled = ViralMaterial(platform="tiktok", url="https://t/cancel", title="da huy", status=ViralStatus.READY)
    db.add_all([queued, waiting, cancelled])
    db.commit()
    db.add(Job(platform="buffer", viral_material_id=queued.id, status=JobStatus.DONE, external_post_id="p1"))
    db.add(Job(platform="buffer", viral_material_id=cancelled.id, status=JobStatus.CANCELLED, external_post_id="p2"))
    db.commit()

    monkeypatch.setattr(ViralService, "find_reup_path", staticmethod(lambda material_id, platform=None: "/tmp/x.mp4"))
    register_feature_hooks()
    rows = feature_hooks.call("viral.list_materials", db, "READY", 10)
    db.close()
    engine.dispose()
    assert [r["title"] for r in rows] == ["da huy", "chua xep"]
