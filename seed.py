import sqlite3, json, time

conn = sqlite3.connect('data/auto_publisher.db')
cursor = conn.cursor()
now = int(time.time())

# ── Platform config: Facebook ────────────────────────────────
cursor.execute('''
    INSERT OR IGNORE INTO platform_configs
    (platform, adapter_class, display_name, display_emoji,
     is_active, base_urls, viewport, media_extensions,
     created_at, updated_at)
    VALUES (?,?,?,?,1,?,?,?,?,?)
''', (
    'facebook',
    'app.adapters.facebook.adapter.FacebookAdapter',
    'Facebook',
    '',
    json.dumps({
        'home': 'https://www.facebook.com/',
        'reels_create': 'https://www.facebook.com/reels/create',
        'profile': 'https://www.facebook.com/me'
    }),
    json.dumps({'width': 1280, 'height': 720}),
    json.dumps(['.mp4', '.jpg', '.jpeg', '.png']),
    now, now
))

# ── Workflow: POST Facebook ──────────────────────────────────
cursor.execute('''
    INSERT OR IGNORE INTO workflow_definitions
    (name, platform, job_type, is_active, steps,
     timing_config, retry_config, created_at, updated_at)
    VALUES (?,?,?,1,?,?,?,?,?)
''', (
    'post_facebook_reels',
    'facebook', 'POST',
    json.dumps([
        'open_session',
        'navigate_to_page',
        'check_login',
        'open_reels_entry',
        'upload_media',
        'fill_caption',
        'click_next_steps',
        'click_post',
        'wait_submission',
        'verify_published',
        'close_session'
    ]),
    json.dumps({
        'post_navigation_wait_ms': 4000,
        'session_recovery_wait_ms': 8000,
        'upload_preview_wait_ms': 8000,
        'next_button_wait_ms': 3000,
        'post_enabled_timeout_ms': 120000,
        'post_submit_wait_ms': 10000,
        'max_next_steps': 6,
        'typing_delay_min': 0.03,
        'typing_delay_max': 0.12,
        'scroll_delta_min': 300,
        'scroll_delta_max': 900,
        'pre_post_delay_min_ms': 2000,
        'pre_post_delay_max_ms': 6000
    }),
    json.dumps({
        'max_tries': 3,
        'backoff_minutes': [5, 15, 30],
        'fatal_threshold': 3
    }),
    now, now
))

# ── Workflow: COMMENT Facebook ───────────────────────────────
cursor.execute('''
    INSERT OR IGNORE INTO workflow_definitions
    (name, platform, job_type, is_active, steps,
     timing_config, retry_config, created_at, updated_at)
    VALUES (?,?,?,1,?,?,?,?,?)
''', (
    'comment_facebook',
    'facebook', 'COMMENT',
    json.dumps([
        'open_session',
        'navigate_to_post',
        'dismiss_overlay',
        'scroll_to_comment',
        'open_comment_section',
        'find_comment_box',
        'type_comment',
        'submit_comment',
        'close_session'
    ]),
    json.dumps({
        'navigation_wait_ms': 3000,
        'overlay_dismiss_wait_ms': 2000,
        'comment_section_wait_ms': 3000,
        'typing_delay_min': 0.05,
        'typing_delay_max': 0.15,
        'submit_wait_ms': 2000
    }),
    json.dumps({
        'max_tries': 3,
        'backoff_minutes': [5, 15],
        'fatal_threshold': 3
    }),
    now, now
))

# ── Selectors: Facebook ──────────────────────────────────────
selectors = [
    # category, name, type, value, locale, priority, notes
    ('post', 'post_button',
     'css', '[aria-label="Post"]', 'en', 10,
     'Main post button'),
    ('post', 'post_button',
     'css', '[aria-label="Đăng"]', 'vi', 9,
     'Vietnamese post button'),
    ('post', 'caption_field',
     'css', '[aria-label="Create a public post"]', 'en', 10,
     'Caption input'),
    ('post', 'caption_field',
     'css', '[aria-label="Tạo bài viết công khai"]', 'vi', 9,
     'Caption input VN'),
    ('comment', 'comment_box',
     'placeholder', 'Write a comment', 'en', 10,
     'Comment input box'),
    ('comment', 'comment_box',
     'placeholder', 'Viết bình luận', 'vi', 9,
     'Comment input VN'),
    ('comment', 'comment_box',
     'css', '[aria-label="Write a comment"]', 'en', 8,
     'Comment aria'),
    ('comment', 'comment_box',
     'css', '.UFIAddCommentInput', '*', 5,
     'Legacy comment box'),
    ('comment', 'comment_section_btn',
     'text', 'Comment', 'en', 10,
     'Open comments button'),
    ('comment', 'comment_section_btn',
     'text', 'Bình luận', 'vi', 9,
     'Open comments VN'),
    ('login', 'continue_as_btn',
     'css', '[aria-label*="Continue as"]', 'en', 10,
     'Continue as user'),
    ('login', 'checkpoint_indicator',
     'css', '#checkpointFriendlyLoginForm', '*', 10,
     'Checkpoint detection'),
    ('reels', 'reels_entry_page',
     'css', '[aria-label="Reels"]', 'en', 10,
     'Page reels entry'),
    ('reels', 'reels_create_btn',
     'css', '[aria-label="Create reel"]', 'en', 10,
     'Create reel button'),
    ('reels', 'next_button',
     'text', 'Next', 'en', 10,
     'Next step button'),
    ('reels', 'next_button',
     'text', 'Tiếp', 'vi', 9,
     'Next step VN'),
]

for cat, name, stype, val, locale, pri, notes in selectors:
    cursor.execute('''
        INSERT OR IGNORE INTO platform_selectors
        (platform, category, selector_name, selector_type,
         selector_value, locale, priority, version,
         valid_from, is_active, notes, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,1,?,1,?,?,?)
    ''', ('facebook', cat, name, stype, val,
          locale, pri, now, notes, now, now))

# ── CTA Templates ────────────────────────────────────────────
cta_templates = [
    ('Link mình để ở đây nè:\n{link}', 'vi', None, None, 10),
    ('Xem chi tiết sản phẩm tại đây: {link}', 'vi', None, None, 9),
    ('Mình hay mua ở đây, deal tốt lắm: {link}', 'vi', None, None, 8),
    ('Bạn nào cần link thì đây nha: {link}', 'vi', None, None, 7),
    ('Check link này nè: {link}', 'vi', None, None, 6),
    ('Sản phẩm mình dùng đây: {link}', 'vi', None, None, 5),
]

for template, locale, page_url, niche, priority in cta_templates:
    cursor.execute('''
        INSERT OR IGNORE INTO cta_templates
        (platform, template, locale, page_url, niche,
         priority, is_active, created_at)
        VALUES (?,?,?,?,?,?,1,?)
    ''', ('facebook', template, locale, page_url, niche,
          priority, now))

conn.commit()
conn.close()
print('Seed complete')
