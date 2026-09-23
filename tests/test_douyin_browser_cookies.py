from __future__ import annotations

from app.core.yt_dlp_path import browser_cookie_args, resolve_chrome_user_data
from app.features.viral_intake.processor import (
    _extend_yt_dlp_with_cookies,
    _humanize_yt_dlp_error,
)


def test_browser_cookie_args_only_douyin(tmp_path, monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.delenv("YTDLP_CHROME_USER_DATA", raising=False)
    monkeypatch.setattr("app.core.yt_dlp_path.resolve_chrome_user_data", lambda: None)
    assert browser_cookie_args("tiktok") == ()
    assert browser_cookie_args("douyin") == ()


def test_browser_cookie_args_file_and_chrome(tmp_path, monkeypatch):
    ck = tmp_path / "douyin_cookies.txt"
    ck.write_text("# Netscape\n", encoding="utf-8")
    monkeypatch.setenv("YTDLP_COOKIES_FILE", str(ck))
    assert browser_cookie_args("douyin") == ("--cookies", str(ck))

    monkeypatch.delenv("YTDLP_COOKIES_FILE")
    ud = tmp_path / "User Data"
    ud.mkdir()
    monkeypatch.setenv("YTDLP_CHROME_USER_DATA", str(ud))
    assert browser_cookie_args("douyin") == ("--cookies-from-browser", f"chrome:{ud}")


def test_extend_yt_dlp_prefers_account_profile():
    class Acc:
        profile_path = "/tmp/chromium-profile"

    cmd = ["yt-dlp", "https://v.douyin.com/x"]
    out = _extend_yt_dlp_with_cookies(cmd, Acc(), "douyin")
    assert "--cookies-from-browser" in out
    assert "chromium:/tmp/chromium-profile" in out


def test_extend_yt_dlp_douyin_uses_chrome_when_no_account(tmp_path, monkeypatch):
    ud = tmp_path / "User Data"
    ud.mkdir()
    monkeypatch.setenv("YTDLP_CHROME_USER_DATA", str(ud))
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    cmd = ["yt-dlp", "https://v.douyin.com/x"]
    out = _extend_yt_dlp_with_cookies(cmd, None, "douyin")
    assert out[-2:] == ["--cookies-from-browser", f"chrome:{ud}"]


def test_humanize_douyin_fresh_cookies():
    msg = _humanize_yt_dlp_error(
        "douyin",
        "ERROR: [Douyin] 7684786365369163690: Fresh cookies (not necessarily logged in) are needed",
        None,
    )
    assert "cookie" in msg.lower() or "Cookie" in msg
    assert "Chrome" in msg


def test_douyin_cookie_and_timeout_not_auto_retried():
    from app.features.viral_intake.processor import _is_retryable_error

    assert _is_retryable_error("yt-dlp timed out while fetching media.") is False
    assert _is_retryable_error("Fresh cookies (not necessarily logged in) are needed") is False
    assert _is_retryable_error("Douyin đòi cookie Chrome. Mở douyin.com") is False
    assert _is_retryable_error("network 429 rate limit") is True


def test_resolve_chrome_user_data_env(tmp_path, monkeypatch):
    ud = tmp_path / "Chrome User Data"
    ud.mkdir()
    monkeypatch.setenv("YTDLP_CHROME_USER_DATA", str(ud))
    assert resolve_chrome_user_data() == ud


def test_best_chrome_profile_skips_stub_default(tmp_path):
    from app.core.yt_dlp_path import _best_chrome_profile

    ud = tmp_path / "User Data"
    (ud / "Default").mkdir(parents=True)
    (ud / "Default" / "Preferences").write_text("{}", encoding="utf-8")
    assert _best_chrome_profile(ud) is None

    net = ud / "Profile 18" / "Network"
    net.mkdir(parents=True)
    (net / "Cookies").write_bytes(b"sqlite-header-fake")
    assert _best_chrome_profile(ud).name == "Profile 18"


def test_auto_browser_cookies_skip_when_unreadable(tmp_path, monkeypatch):
    monkeypatch.delenv("YTDLP_COOKIES_FILE", raising=False)
    monkeypatch.delenv("YTDLP_COOKIES_FROM_BROWSER", raising=False)
    monkeypatch.delenv("YTDLP_CHROME_USER_DATA", raising=False)
    monkeypatch.setattr("app.core.yt_dlp_path.resolve_chrome_user_data", lambda: tmp_path / "missing")
    monkeypatch.setattr("app.core.yt_dlp_path._best_chrome_profile", lambda _ud: None)
    assert browser_cookie_args("douyin") == ()


def test_real_douyin_cdn_url_filter():
    from app.features.viral_intake.douyin_fallback import is_real_douyin_cdn_url

    assert is_real_douyin_cdn_url(
        "https://v5-dy-ov-experiment.zjcdn.com/x/video/tos/cn/tos-cn-ve-15/a/?mime_type=video_mp4"
    )
    assert not is_real_douyin_cdn_url("https://lf-douyin-pc-web.douyinstatic.com/obj/douyin-pc-web/uuu_265.mp4")
    assert not is_real_douyin_cdn_url("blob:https://www.douyin.com/abc")


def test_processor_has_find_duplicate():
    from app.features.viral_intake import processor as pm
    from app.features.viral_intake.dedup import find_duplicate

    assert pm.find_duplicate is find_duplicate
