"""Unit tests for FacebookIdentitySwitcher's pure-Python helpers.

The Playwright-driven `switch_to_page` flow is exercised end-to-end via the
ad-hoc browser script (see TASK-053 verify); these tests cover the URL→name
resolution that the switcher uses to map form input to FB popup labels.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.features.facebook.identity import _normalize_url, resolve_page_name


def test_normalize_url_strips_protocol_www_query():
    assert _normalize_url("https://www.facebook.com/MePage?ref=1") == "facebook.com/mepage"
    assert _normalize_url("http://facebook.com/mepage/") == "facebook.com/mepage"
    assert _normalize_url("FACEBOOK.COM/MePage") == "facebook.com/mepage"
    assert _normalize_url(None) == ""
    assert _normalize_url("") == ""


def test_resolve_page_name_exact_url_match():
    pages = [
        {"name": "Mẹ Sún Riviu", "url": "https://www.facebook.com/mesunriviu"},
        {"name": "Da Đẹp Lì Tu", "url": "facebook.com/dadeplitu"},
    ]
    assert resolve_page_name("https://facebook.com/mesunriviu", pages) == "Mẹ Sún Riviu"
    assert resolve_page_name("https://www.facebook.com/dadeplitu/", pages) == "Da Đẹp Lì Tu"


def test_resolve_page_name_substring_match_handles_query_diff():
    pages = [{"name": "My Page", "url": "facebook.com/mypage"}]
    # form value carries extra query params
    assert resolve_page_name("https://www.facebook.com/mypage?ref=manage", pages) == "My Page"


def test_resolve_page_name_returns_none_when_no_match():
    pages = [{"name": "Other", "url": "facebook.com/other"}]
    assert resolve_page_name("https://facebook.com/missing", pages) is None
    assert resolve_page_name("https://facebook.com/anything", []) is None
    assert resolve_page_name(None, pages) is None
    assert resolve_page_name("", pages) is None


def test_resolve_page_name_skips_blank_url_entries():
    pages = [
        {"name": "Blank", "url": ""},
        {"name": "Real", "url": "facebook.com/real"},
    ]
    assert resolve_page_name("https://facebook.com/real", pages) == "Real"
