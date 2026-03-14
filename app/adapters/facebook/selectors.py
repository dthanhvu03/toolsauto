# Selectors mapping - NO XPATHS allowed, no nth-child hooks.
# See 14_PROJECT_DISCIPLINE_RULES.md - V. Selector Discipline

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
        "account_menu_button": "svg[aria-label=\"Tài khoản của bạn\"], svg[aria-label=\"Your profile\"]",
        "see_all_profiles": "div[role=\"button\"]:has-text(\"Xem tất cả trang cá nhân\"), div[role=\"button\"]:has-text(\"See all profiles\")",
        "target_profile_btn": "div[role=\"dialog\"] *[role=\"button\"][aria-label*=\"{target_page_name}\"], div[role=\"dialog\"] *[role=\"radio\"][aria-label*=\"{target_page_name}\"], div[role=\"dialog\"] *[role=\"link\"][aria-label*=\"{target_page_name}\"], div[role=\"dialog\"] div[role=\"button\"]:has-text(\"{target_page_name}\"), div[role=\"dialog\"] div[role=\"radio\"]:has-text(\"{target_page_name}\")",
        "any_profile_btn": "div[role=\"dialog\"] div[role=\"button\"]"
    }
}
