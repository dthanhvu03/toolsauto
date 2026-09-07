"""VIP monetize / strategic helpers — unit tests (no DB)."""
from __future__ import annotations

from types import SimpleNamespace

from app.core.queue.job import JobService
from app.constants import ViralStatus


def _job():
    return SimpleNamespace(
        tracking_code=None,
        affiliate_url=None,
        tracking_url=None,
        auto_comment_text=None,
    )


def test_attach_affiliate_chen_url_goc_va_giu_sub_id():
    """ADR-015: [LINK] → URL affiliate gốc; tracking_code vẫn sinh (Sub ID gợi ý);
    tracking_url KHÔNG còn được ghi."""
    job = _job()
    JobService.attach_affiliate_to_job(
        job,
        affiliate_url="https://shopee.vn/a",
        comment_template="Mua ngay [LINK]",
    )
    assert job.affiliate_url == "https://shopee.vn/a"
    assert job.tracking_code and len(job.tracking_code) == 8
    assert job.tracking_url is None
    assert job.auto_comment_text == "Mua ngay https://shopee.vn/a"


def test_attach_affiliate_khong_con_sinh_link_rut_gon():
    """Cả [LINK] lẫn {tracking_url} đều thành URL gốc, không có /r/ trong comment."""
    job = _job()
    JobService.attach_affiliate_to_job(
        job,
        affiliate_url="https://shopee.vn/a?sub_id=post1",
        comment_template="Link: [LINK] | {tracking_url}",
    )
    assert job.auto_comment_text == (
        "Link: https://shopee.vn/a?sub_id=post1 | https://shopee.vn/a?sub_id=post1"
    )
    assert "/r/" not in job.auto_comment_text


def test_app_khong_con_route_redirect_r_code():
    """ADR-015: route GET /r/{code} và DashboardService.track_redirect_click đã gỡ."""
    from app.platform.dashboard_service import DashboardService
    from app.platform.dashboard_shell.router import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert "/r/{code}" not in paths
    assert not any(p.startswith("/r/") for p in paths)
    assert not hasattr(DashboardService, "track_redirect_click")


def test_viral_status_has_boost_pending():
    assert ViralStatus.BOOST_PENDING == "BOOST_PENDING"
