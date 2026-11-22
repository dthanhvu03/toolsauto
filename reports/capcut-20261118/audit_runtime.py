"""Aggregate observation only; never starts growth runner/browser or alters runtime settings."""
import json
import sqlite3
import subprocess
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from sqlalchemy import text
from app.core.database.core import SessionLocal
from app.core import settings

ROOT = Path('/home/vu/toolsauto')
SINCE = '2026-11-18T02:01:59+00:00'
keys = ['growth.keywords_ai_store', 'growth.ai_store_a_angle', 'growth.ai_store_a_hook',
        'growth.ai_store_b_angle', 'growth.ai_store_b_hook', 'growth.enabled', 'growth.own_posts_enabled']
proof = {'observed_at': datetime.now(timezone.utc).isoformat(), 'code_commit_boundary': SINCE,
         'boundary_is_not_attribution': True}
with SessionLocal() as db:
    db.execute(text('SET TRANSACTION READ ONLY'))
    rows = db.execute(text('SELECT key,value FROM runtime_settings WHERE key IN (' + ','.join(f':k{i}' for i in range(len(keys))) + ')'), {f'k{i}':key for i,key in enumerate(keys)}).all()
    overrides = dict(rows)
    proof['runtime_settings'] = {key: {'override_present': key in overrides,
        'override': overrides.get(key), 'code_default': settings.SETTINGS[key].default_getter()} for key in keys if key in settings.SETTINGS}
    db.rollback()
with closing(sqlite3.connect((ROOT/'data/threads_growth.sqlite').as_uri()+'?mode=ro', uri=True)) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute('BEGIN')
    proof['posted_after_commit'] = [dict(row) for row in conn.execute('''SELECT account,target_bot,COUNT(*) AS posted,
        SUM(CASE WHEN lower(COALESCE(actual_reply,suggested_reply,'')) LIKE '%capcut%' THEN 1 ELSE 0 END) AS mentions_capcut
        FROM growth_posts WHERE status='posted' AND julianday(posted_at)>=julianday(?) GROUP BY account,target_bot''',(SINCE,))]
    proof['queue_current'] = [dict(row) for row in conn.execute('''SELECT target_bot,status,COUNT(*) AS count,
        SUM(CASE WHEN lower(suggested_reply) LIKE '%capcut%' THEN 1 ELSE 0 END) AS mentions_capcut
        FROM growth_posts WHERE status IN ('pending','approved') GROUP BY target_bot,status''')]
    pending = conn.execute("SELECT created_at,suggested_reply FROM growth_posts WHERE target_bot='ai_store' AND status='approved'").fetchall()
    proof['approved_store_detail'] = {
        'created_before_code_commit': sum(datetime.fromisoformat(row['created_at'].replace('Z','+00:00')) < datetime.fromisoformat(SINCE) for row in pending),
        'mentions_other_products_without_capcut': sum('capcut' not in row['suggested_reply'].lower() and any(word in row['suggested_reply'].lower() for word in ('canva','chatgpt','claude','gemini','grok','cursor')) for row in pending),
        'oldest_created_at': min((row['created_at'] for row in pending), default=None),
        'content_match_is_heuristic': True,
    }
    proof['own_posts_after_commit'] = [dict(row) for row in conn.execute('''SELECT kind,status,COUNT(*) AS count FROM own_posts
        WHERE julianday(created_at)>=julianday(?) GROUP BY kind,status''',(SINCE,))]
    proof['first_last_posted_after_commit'] = dict(conn.execute('''SELECT MIN(posted_at) AS first,MAX(posted_at) AS last
        FROM growth_posts WHERE status='posted' AND julianday(posted_at)>=julianday(?)''',(SINCE,)).fetchone())
apps=json.loads(subprocess.check_output(['pm2','jlist'],text=True))
row=next(row for row in apps if row['name']=='Threads_Growth')
proof['worker']={'pid':row['pid'],'status':row['pm2_env']['status'],'restarts':row['pm2_env']['restart_time'],
                 'started_at':datetime.fromtimestamp(row['pm2_env']['pm_uptime']/1000,timezone.utc).isoformat()}
print(json.dumps(proof,ensure_ascii=False,indent=2))
(ROOT/'reports/capcut-20261118/runtime-audit.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
