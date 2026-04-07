import sqlite3, json

conn = sqlite3.connect('data/auto_publisher.db')
c = conn.cursor()

# Restore comment_facebook steps
original_steps = json.dumps([
    'open_session','navigate_to_post','dismiss_overlay',
    'scroll_to_comment','open_comment_section','find_comment_box',
    'type_comment','submit_comment','close_session'
])
c.execute('UPDATE workflow_definitions SET steps=? WHERE name=?', (original_steps, 'comment_facebook'))

# Restore post_facebook_reels steps  
original_post_steps = json.dumps([
    'open_session','navigate_to_page','check_login',
    'open_reels_entry','upload_media','fill_caption',
    'click_next_steps','click_post','wait_submission',
    'verify_published','close_session'
])
c.execute('UPDATE workflow_definitions SET steps=? WHERE name=?', (original_post_steps, 'post_facebook_reels'))

conn.commit()

# Verify
for row in c.execute('SELECT name, steps FROM workflow_definitions WHERE platform=?', ('facebook',)):
    steps = json.loads(row[1])
    print(f'{row[0]}: {len(steps)} steps, type={type(steps[0]).__name__}')
conn.close()
print('Done - steps restored.')
