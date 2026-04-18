# Instagram Selectors — Heuristic fallback locators
# Priority: role/label → text → placeholder → stable attr → CSS last resort
# See app/adapters/common/locator.py
from app.config import INSTAGRAM_HOST

HEURISTIC_SELECTORS = {
    "login": {
        "login_indicators": [
            ("css", 'input[name="username"]'),
            ("css", 'input[name="password"]'),
            ("text", "Log in"),
            ("text", "Đăng nhập"),
        ],
        "authenticated_indicators": [
            ("css", 'a[href="/direct/inbox/"], svg[aria-label="Home"]'),
            ("css", 'a[href*="/accounts/edit/"]'),
            ("role", "navigation"),
        ],
    },
    "upload": {
        "upload_page_url": f"{INSTAGRAM_HOST}/",
        "new_post_button": [
            ("css", 'svg[aria-label="New post"], a[href="#"]'),
            ("role", "link:New post"),
            ("label", "New post"),
            ("text", "Tạo"),
            ("text", "Create"),
        ],
        "file_input": [
            ("css", 'input[type="file"][accept*="video"]'),
            ("css", 'input[type="file"][accept*="image"]'),
            ("css", 'input[type="file"]'),
        ],
        "select_from_computer": [
            ("role", "button:Select from computer"),
            ("role", "button:Chọn từ máy tính"),
            ("text", "Select from computer"),
            ("text", "Chọn từ máy tính"),
        ],
    },
    "caption": {
        "caption_input": [
            ("placeholder", "Write a caption..."),
            ("placeholder", "Viết chú thích..."),
            ("label", "Write a caption..."),
            ("css", 'textarea[aria-label*="caption"], textarea[aria-label*="chú thích"]'),
            ("css", 'div[contenteditable="true"][role="textbox"]'),
            ("role", "textbox"),
        ],
    },
    "publish": {
        "next_button": [
            ("role", "button:Next"),
            ("role", "button:Tiếp"),
            ("text", "Next"),
            ("text", "Tiếp"),
        ],
        "share_button": [
            ("role", "button:Share"),
            ("role", "button:Chia sẻ"),
            ("text", "Share"),
            ("text", "Chia sẻ"),
        ],
    },
    "confirmation": {
        "success_indicators": [
            ("text", "Your reel has been shared"),
            ("text", "Reel của bạn đã được chia sẻ"),
            ("text", "Post shared"),
            ("text", "shared"),
        ],
        "error_indicators": [
            ("text", "couldn't upload"),
            ("text", "không thể tải lên"),
            ("text", "error"),
            ("text", "lỗi"),
        ],
    },
}
