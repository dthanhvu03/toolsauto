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
    }
}
