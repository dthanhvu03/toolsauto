"""VIP monetize / strategic helpers — unit tests (no DB)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.core.queue.job import JobService
from app.constants import ViralStatus


def test_attach_affiliate_sets_tracking_and_comment():
    job = SimpleNamespace(
        tracking_code=None,
        affiliate_url=None,
        tracking_url=None,
        auto_comment_text=None,
    )
    with patch("app.config.VERCEL_REDIRECT_URL", "https://track.example"):
        JobService.attach_affiliate_to_job(
            job,
            affiliate_url="https://shopee.vn/a",
            comment_template="Mua ngay [LINK]",
        )
    assert job.affiliate_url == "https://shopee.vn/a"
    assert job.tracking_code and len(job.tracking_code) == 8
    assert job.tracking_url == f"https://track.example/r/{job.tracking_code}"
    assert job.auto_comment_text == f"Mua ngay {job.tracking_url}"


def test_viral_status_has_boost_pending():
    assert ViralStatus.BOOST_PENDING == "BOOST_PENDING"
