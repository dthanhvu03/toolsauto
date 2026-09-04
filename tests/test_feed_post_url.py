"""
PLAN-053 — suy ra link bài feed + gắn comment cho bài feed.

Phần suy ra link là hàm thuần nên test được không cần mở trình duyệt; phần
`mark_done` chạy trên Postgres thật vì nó ghi DB.
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from app.features.facebook.adapter import FacebookAdapter

ADAPTER_PY = Path(__file__).resolve().parents[1] / "app" / "features" / "facebook" / "adapter.py"
PAGE = "https://www.facebook.com/kids0810"


# ── suy ra link từ payload GraphQL ────────────────────────────────────────────

def test_lay_link_khi_payload_co_san_url():
    payload = {"data": {"story_create": {"story": {"url": "https://www.facebook.com/kids0810/posts/pfbid0abc?x=1"}}}}
    assert FacebookAdapter._post_url_from_payload(payload, PAGE) == "https://www.facebook.com/kids0810/posts/pfbid0abc"


def test_ghep_link_tu_post_id_khi_khong_co_url():
    payload = {"data": {"feedback": {"post_id": "1234567890123456"}}}
    assert (
        FacebookAdapter._post_url_from_payload(payload, PAGE)
        == "https://www.facebook.com/kids0810/posts/1234567890123456"
    )


def test_ghep_link_tu_story_fbid_long_nhieu_tang():
    payload = {"a": [{"b": {"c": {"story_fbid": "9876543210987"}}}]}
    assert FacebookAdapter._post_url_from_payload(payload, PAGE).endswith("/posts/9876543210987")


def test_khong_co_page_thi_ve_host_goc():
    payload = {"post_id": "1234567890123456"}
    url = FacebookAdapter._post_url_from_payload(payload, None)
    assert url.endswith("/1234567890123456") and "/posts/" not in url


def test_payload_khong_lien_quan_thi_khong_bia_link():
    payload = {"data": {"viewer": {"actor": {"id": "42"}, "unread": 3}}}
    assert FacebookAdapter._post_url_from_payload(payload, PAGE) is None


def test_id_qua_ngan_khong_duoc_nhan_nham():
    # id ngắn là của widget UI, không phải bài viết
    assert FacebookAdapter._walk_for_post_ids({"post_id": "123"}) == []


def test_id_khong_phai_so_bi_bo_qua():
    assert FacebookAdapter._walk_for_post_ids({"post_id": "abcdefghij"}) == []


# ── kỷ luật của listener (đọc source) ─────────────────────────────────────────

def test_listener_khong_con_loc_theo_ten_mutation_doan_truoc():
    src = ADAPTER_PY.read_text(encoding="utf-8")
    assert '"StoryCreate", "Composer", "FeedPost", "CometComposer"' not in src


def test_link_tu_mutation_duoc_uu_tien_hon_link_tren_feed():
    src = ADAPTER_PY.read_text(encoding="utf-8")
    assert 'is_mutation = "Mutation" in req_post' in src
    assert "bucket = captured_urls if is_mutation else fallback_urls" in src


def test_listener_chi_gan_khi_sap_bam_dang():
    """Nghe từ lúc mở trang thì bắt nhầm link bài cũ đang cuộn qua."""
    src = ADAPTER_PY.read_text(encoding="utf-8")
    attach = src.index('self.page.on("response", _capture_story_url)')
    submit = src.index('update_active_node(job.id, "submit")')
    browse = src.index('update_active_node(job.id, "feed_browse")')
    assert browse < submit < attach, "listener phải gắn sau bước cuộn feed"


# ── mark_done sinh COMMENT job cho bài feed (DB thật) ─────────────────────────

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


def _make_job(session, created, *, job_type: str, auto_comment: str | None, post_url: str | None):
    from app.core.database.models import Account, Job

    tag = f"__pytest_c_{uuid.uuid4().hex[:8]}"
    account = Account(name=f"{tag}_acc", platform="facebook", is_active=True, login_status="ACTIVE")
    session.add(account)
    session.flush()
    created.append(account.id)

    job = Job(
        platform=tag,
        account_id=account.id,
        job_type=job_type,
        status="RUNNING",
        caption="pytest feed comment",
        schedule_ts=int(time.time()),
        auto_comment_text=auto_comment,
        post_url=post_url,
    )
    session.add(job)
    session.commit()
    return account.id, job


def _comment_jobs_of(session, account_id):
    from app.core.database.models import Job

    return session.query(Job).filter(Job.account_id == account_id, Job.job_type == "COMMENT").all()


@pytest.mark.integration
def test_bai_feed_co_comment_thi_sinh_comment_job(db):
    from app.core.queue.job import JobService

    session, created = db
    account_id, job = _make_job(
        session, created, job_type="FEED", auto_comment="link aff nè", post_url=f"{PAGE}/posts/123456789012"
    )

    JobService.mark_done(session, job, post_url=f"{PAGE}/posts/123456789012")

    comments = _comment_jobs_of(session, account_id)
    assert len(comments) == 1, "bài feed có auto_comment mà không sinh COMMENT job"
    assert comments[0].post_url == f"{PAGE}/posts/123456789012"
    assert comments[0].parent_job_id == job.id


@pytest.mark.integration
def test_bai_feed_khong_co_link_thi_khong_sinh_comment_mo_coi(db):
    from app.core.queue.job import JobService

    session, created = db
    account_id, job = _make_job(session, created, job_type="FEED", auto_comment="link aff nè", post_url=None)

    JobService.mark_done(session, job, post_url=None)

    assert _comment_jobs_of(session, account_id) == []


@pytest.mark.integration
def test_reels_van_sinh_comment_nhu_cu(db):
    from app.core.queue.job import JobService

    session, created = db
    account_id, job = _make_job(
        session, created, job_type="POST", auto_comment="cmt", post_url=f"{PAGE}/videos/999"
    )

    JobService.mark_done(session, job, post_url=f"{PAGE}/videos/999")

    assert len(_comment_jobs_of(session, account_id)) == 1


@pytest.mark.integration
def test_story_khong_sinh_comment_job(db):
    """Story Facebook không có bình luận công khai — không tạo COMMENT job vô nghĩa."""
    from app.core.queue.job import JobService

    session, created = db
    account_id, job = _make_job(
        session, created, job_type="STORY", auto_comment="cmt", post_url=f"{PAGE}/stories/111"
    )

    JobService.mark_done(session, job, post_url=f"{PAGE}/stories/111")

    assert _comment_jobs_of(session, account_id) == []
