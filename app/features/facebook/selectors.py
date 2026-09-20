# Selectors mapping - NO XPATHS allowed, no nth-child hooks.
# See 14_PROJECT_DISCIPLINE_RULES.md - V. Selector Discipline
from pathlib import Path

SELECTORS = {
    "login": {
        "username_input": "get_by_label('Email address or phone number')",
        "password_input": "get_by_label('Password')",
        "login_button": "get_by_role('button', name='Log In')"
    },
    "post": {
        "create_post_button": "get_by_role('button', name='Create post')",
        "text_area": "get_by_role('textbox', name='What\\'s on your mind?')",
        "photo_video_button": "get_by_label('Photo/video')",
        "file_input": "input[type='file'][accept*='image']", # The hidden input
        "post_btn": "get_by_role('button', name='Post', exact=True)"
    },
    "switch_menu": {
        "switch_now_button": "div[role=\"button\"]:has-text(\"Switch now\"), div[role=\"button\"]:has-text(\"Chuyển ngay\")",
        "account_menu_button": 'div[aria-label="Trang cá nhân của bạn"], div[aria-label="Tài khoản của bạn"], div[aria-label="Your profile"], div[aria-label="Account"], div[aria-label="Menu tài khoản"], div[aria-label="Account controls and settings"], div[aria-label="Cài đặt và quyền riêng tư"]',
        "see_all_profiles": "div[role=\"button\"]:has-text(\"Xem tất cả trang cá nhân\"), div[role=\"button\"]:has-text(\"See all profiles\")",
        "target_profile_btn": "div[role=\"dialog\"] *[role=\"button\"][aria-label*=\"{target_page_name}\"], div[role=\"dialog\"] *[role=\"radio\"][aria-label*=\"{target_page_name}\"], div[role=\"dialog\"] *[role=\"link\"][aria-label*=\"{target_page_name}\"], div[role=\"dialog\"] div[role=\"button\"]:has-text(\"{target_page_name}\"), div[role=\"dialog\"] div[role=\"radio\"]:has-text(\"{target_page_name}\")",
        "any_profile_btn": "div[role=\"dialog\"] div[role=\"button\"]"
    }
}

# Central checkpoint/logout markers (GEMINI_SELECTORS-style: one dict, no scatter).
# Detect + abort only — never solve, never navigate away, never auto-login.
CHECKPOINT = {
    "url_markers": (
        "checkpoint",
        "unusual login",
        "unusual_login",
        "xác nhận danh tính",
        "/login/",
        "/checkpoint/",
        "login_attempt",
        "account_locked",
    ),
    "text_markers": (
        "checkpoint",
        "unusual login",
        "xác nhận danh tính",
        "account locked",
        "login_attempt",
    ),
}


def looks_like_checkpoint(url: str | None, text: str | None = None) -> bool:
    """True if URL or visible text matches centralized checkpoint markers."""
    hay_url = (url or "").lower()
    hay_text = (text or "").lower()
    for marker in CHECKPOINT["url_markers"]:
        if marker.lower() in hay_url:
            return True
    for marker in CHECKPOINT["text_markers"]:
        needle = marker.lower()
        if needle in hay_text or needle in hay_url:
            return True
    return False


def checkpoint_screenshot_path(account_id=None, job_id=None, suffix: str = "checkpoint") -> Path:
    """logs/screenshots/{ts}_{account_id}[_job{id}]_checkpoint.png"""
    from datetime import datetime

    from app.config import LOGS_DIR

    shot_dir = Path(LOGS_DIR) / "screenshots"
    shot_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    acc = account_id if account_id is not None else "na"
    job_part = f"_job{job_id}" if job_id is not None else ""
    return shot_dir / f"{ts}_{acc}{job_part}_{suffix}.png"

