# TikTok Selectors — Heuristic fallback locators
# These serve as LAST RESORT when DB selectors are missing or broken.
# Priority order: role/label → text → placeholder → stable attr → CSS
#
# Format follows LocatorCandidate(strategy, locator_type, value, source)
# See app/adapters/common/locator.py

HEURISTIC_SELECTORS = {
    "login": {
        "login_indicators": [
            # Locators that indicate user is on the login page
            ("css", 'input[name="username"], input[placeholder*="email"], input[placeholder*="phone"]'),
            ("css", 'input[type="password"]'),
            ("text", "Log in"),
            ("text", "Đăng nhập"),
        ],
        "authenticated_indicators": [
            # Locators that indicate user is authenticated
            ("css", 'div[data-e2e="profile-icon"], a[data-e2e="upload-icon"]'),
            ("css", 'button[data-e2e="top-upload-button"]'),
            ("role", "navigation"),
        ],
    },
    "upload": {
        "upload_page_url": "https://www.tiktok.com/upload",
        "file_input": [
            ("css", 'input[type="file"][accept*="video"]'),
            ("css", 'input[type="file"]'),
        ],
        "upload_button": [
            ("role", "button:Upload video"),
            ("role", "button:Select file"),
            ("text", "Select file"),
            ("text", "Chọn tệp"),
            ("css", 'button[class*="upload"]'),
        ],
    },
    "caption": {
        "caption_input": [
            ("css", 'div[data-e2e="caption-editor"] div[contenteditable="true"]'),
            ("css", 'div[contenteditable="true"][data-text="true"]'),
            ("role", "textbox"),
            ("css", 'div[contenteditable="true"]'),
        ],
    },
    "publish": {
        "post_button": [
            ("role", "button:Post"),
            ("role", "button:Đăng"),
            ("text", "Post"),
            ("text", "Đăng"),
            ("css", 'button[data-e2e="post-button"]'),
            ("css", 'button[class*="post"], button[class*="submit"]'),
        ],
        "schedule_button": [
            ("role", "button:Schedule"),
            ("text", "Schedule"),
            ("text", "Lên lịch"),
        ],
    },
    "confirmation": {
        "success_indicators": [
            ("text", "Your video is being uploaded"),
            ("text", "Video đang được tải lên"),
            ("text", "uploaded"),
            ("css", 'div[class*="success"], div[class*="complete"]'),
        ],
        "error_indicators": [
            ("text", "failed"),
            ("text", "error"),
            ("text", "thất bại"),
            ("css", 'div[class*="error"], div[class*="fail"]'),
        ],
    },
}
