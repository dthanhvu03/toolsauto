"""
Đính ảnh vào comment tự động — PLAN-055.

Ảnh chỉ là phần phụ của bình luận: đính hỏng thì vẫn phải gửi được comment chữ.
Test khoá đúng kỷ luật đó, cộng với việc COMMENT job con phải kế thừa ảnh.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from app.core.queue.job import JobService
from app.features.facebook.adapter import FacebookAdapter

ROOT = Path(__file__).resolve().parents[1]
PAGE = "https://www.facebook.com/kids0810"


# ── validate ảnh ──────────────────────────────────────────────────────────────

def test_anh_comment_la_tuy_chon():
    JobService.assert_comment_image(None)
    JobService.assert_comment_image("")


def test_chi_nhan_dinh_dang_anh():
    JobService.assert_comment_image("a.jpg")
    JobService.assert_comment_image("a.jpeg")
    JobService.assert_comment_image("a.png")


def test_tu_choi_video_va_file_la():
    """Facebook không cho gắn video vào bình luận."""
    for bad in ("clip.mp4", "clip.mov", "tai-lieu.pdf", "virus.exe"):
        with pytest.raises(ValueError):
            JobService.assert_comment_image(bad)


def test_anh_sai_dinh_dang_khong_de_lai_file_rac(tmp_path, monkeypatch):
    """Lô bị từ chối thì không được ghi byte nào xuống đĩa."""
    import app.config as config

    monkeypatch.setattr(config, "CONTENT_DIR", tmp_path, raising=False)

    class _Upload:
        filename = "khong-phai-anh.mp4"
        file = None  # cố tình để None: nếu code ghi file trước khi kiểm là sẽ nổ khác kiểu

    with pytest.raises(ValueError):
        JobService.save_comment_image(_Upload())

    assert list(tmp_path.rglob("*")) == [], "đã ghi file dù ảnh bị từ chối"


def test_khong_co_file_thi_tra_none():
    assert JobService.save_comment_image(None) is None

    class _Empty:
        filename = ""

    assert JobService.save_comment_image(_Empty()) is None


# ── nối dây ───────────────────────────────────────────────────────────────────

def test_dispatcher_truyen_anh_xuong_adapter():
    src = (ROOT / "app" / "adapters" / "dispatcher.py").read_text(encoding="utf-8")
    assert 'getattr(job, "resolved_comment_image_path", None)' in src
    assert "image_path=comment_image" in src


def test_moi_adapter_deu_nhan_image_path():
    """Dispatcher gọi chung một chữ ký — adapter nào thiếu là vỡ lúc chạy thật."""
    import inspect

    from app.adapters.generic.adapter import GenericAdapter
    from app.features.instagram.adapter import InstagramAdapter
    from app.features.tiktok.adapter import TiktokAdapter

    for cls in (FacebookAdapter, InstagramAdapter, TiktokAdapter, GenericAdapter):
        params = inspect.signature(cls.post_comment).parameters
        assert "image_path" in params, cls.__name__
        assert params["image_path"].default is None, cls.__name__


def test_dinh_anh_that_bai_van_gui_comment_chu():
    """Mất ảnh còn hơn mất cả bình luận — comment là bước phụ, không bao giờ fatal."""
    src = (ROOT / "app" / "features" / "facebook" / "adapter.py").read_text(encoding="utf-8")
    block = src.split("image_attached = self._attach_comment_image(image_path)", 1)[1]
    submit_part = block.split("keyboard.press(\"Enter\")", 1)[0]
    assert "return PublishResult" not in submit_part, "đính ảnh hỏng mà lại bỏ luôn comment"


def test_anh_khong_ton_tai_thi_bao_va_di_tiep():
    import logging

    adapter = FacebookAdapter()
    adapter.logger = logging.getLogger("test")
    assert adapter._attach_comment_image("D:/khong/co/that.jpg") is False


def test_bulk_form_co_o_upload_anh_comment():
    src = (ROOT / "app" / "templates" / "fragments" / "create_job_form.html").read_text(encoding="utf-8")
    assert 'id="bulk-comment-image"' in src
    assert "formData.append('comment_image', commentImage)" in src


def test_migration_them_cot_nullable():
    """Cột phải nullable: job cũ không có ảnh vẫn chạy như trước."""
    src = (ROOT / "alembic" / "versions" / "i7d4e5f6a7b8_job_comment_image.py").read_text(encoding="utf-8")
    assert 'sa.Column("comment_image_path", sa.String(), nullable=True)' in src
    assert 'op.drop_column("jobs", "comment_image_path")' in src, "thiếu downgrade"
    assert 'down_revision: Union[str, None] = "h6c3d4e5f6a7"' in src


# ── COMMENT job con kế thừa ảnh (DB thật) ─────────────────────────────────────

@pytest.fixture()
def db():
    try:
        from sqlalchemy import text

        from app.core.database.core import SessionLocal

        session = SessionLocal()
        session.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover - phụ thuộc môi trường
        pytest.skip(f"Không có Postgres: {e}")

    created: list[int] = []
    try:
        yield session, created
    finally:
        from sqlalchemy import text

        session.rollback()
        if created:
            session.execute(
                text("DELETE FROM job_events WHERE job_id IN (SELECT id FROM jobs WHERE account_id = ANY(:ids))"),
                {"ids": created},
            )
            session.execute(text("DELETE FROM jobs WHERE account_id = ANY(:ids)"), {"ids": created})
            session.execute(text("DELETE FROM accounts WHERE id = ANY(:ids)"), {"ids": created})
            session.commit()
        session.close()


@pytest.mark.integration
def test_comment_job_ke_thua_anh_tu_job_cha(db):
    from app.core.database.models import Account, Job

    session, created = db
    tag = f"__pytest_ci_{uuid.uuid4().hex[:8]}"
    account = Account(name=f"{tag}_acc", platform="facebook", is_active=True, login_status="ACTIVE")
    session.add(account)
    session.flush()
    created.append(account.id)

    job = Job(
        platform=tag,
        account_id=account.id,
        job_type="POST",
        status="RUNNING",
        caption="pytest",
        schedule_ts=int(time.time()),
        auto_comment_text="link aff",
        comment_image_path="content/comment_images/cmt_abc.jpg",
        post_url=f"{PAGE}/videos/1",
    )
    session.add(job)
    session.commit()

    JobService.mark_done(session, job, post_url=f"{PAGE}/videos/1")

    comment = (
        session.query(Job)
        .filter(Job.account_id == account.id, Job.job_type == "COMMENT")
        .one()
    )
    assert comment.comment_image_path == "content/comment_images/cmt_abc.jpg"
