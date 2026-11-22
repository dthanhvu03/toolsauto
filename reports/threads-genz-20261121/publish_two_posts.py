"""PLAN-188: one-off guarded publish of the two owner-approved Threads captions."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import random
import re
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from app.core import settings
from app.core.database.core import SessionLocal
from app.features.threads.growth.browser import GrowthBrowser, posts_from_payload
from app.features.threads.growth.config import DB_PATH, load_account_roles, load_limits, load_worker_config
from app.features.threads.growth.session import profile_dir, profile_locked
from app.features.threads.growth.worker import in_quiet_hours

FOLDER = Path(__file__).resolve().parent
PROFILE = profile_dir("us28qt")
WORKER_NAMES = {"Threads_Growth", "CapCut_Agent_Supervisor"}
MIN_DELAY = 180
POSTS = {'a-keyboard': {'slot': 'threads-genz-20261121-a-keyboard', 'label': 'A — bàn phím cơ', 'text': 'có bàn phím nào người gõ thấy vui mà người ngồi cạnh không muốn chuyển chỗ không =))))\n\nmấy bà mang phím cơ đi làm có từng bị nhắc chưa'}, 'b-lunchbox': {'slot': 'threads-genz-20261121-b-lunchbox', 'label': 'B — hộp cơm hâm nóng', 'text': 'ai còn dùng hộp cơm hâm nóng sau vài tháng mua về không?\n\nmuốn nghe nhất chuyện rửa hộp với mang đi mang về á. lúc xem review cứ để ý cơm nóng ngon, xong quên mất ngày nào cũng phải làm mấy việc đó.'}}
for _item in POSTS.values():
    _item["sha256"] = hashlib.sha256(_item["text"].encode()).hexdigest()


def now_utc():
    return datetime.now(timezone.utc)


def pm2_state():
    rows = json.loads(subprocess.check_output(["pm2", "jlist"], text=True, timeout=15))
    return {
        row["name"]: {
            "pid": row.get("pid") or 0,
            "status": row["pm2_env"]["status"],
            "restarts": row["pm2_env"]["restart_time"],
        }
        for row in rows
    }


def business_bots():
    return {
        name: subprocess.check_output(
            ["systemctl", "show", name, "-p", "MainPID", "-p", "ActiveState", "-p", "ActiveEnterTimestamp"],
            text=True,
            timeout=15,
        ).strip()
        for name in ("store-bot", "cashback-bot", "cashback-zalo")
    }


def runtime_setting(key):
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        value = settings.get_bool(key, db=db)
        db.rollback()
    return value


def login_active():
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        value = db.execute(text("SELECT login_status FROM accounts WHERE name='threads_growth'")).scalar_one_or_none()
        db.rollback()
    return value == "ACTIVE"


def posted_rows(db_path=DB_PATH):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        rows = db.execute(
            "SELECT posted_at AS at FROM growth_posts WHERE status='posted' "
            "AND COALESCE(account,'us28qt')='us28qt' "
            "UNION ALL SELECT created_at AS at FROM own_posts WHERE status='posted' "
            "AND COALESCE(account,'us28qt')='us28qt'"
        ).fetchall()
        db.rollback()
    result = []
    for (value,) in rows:
        if value:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            result.append(parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc))
    return result


def own_slot(slot, db_path=DB_PATH):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        row = db.execute("SELECT status,post_url,text FROM own_posts WHERE slot=?", (slot,)).fetchone()
        db.rollback()
    return row


def unknown_campaign_attempts(db_path=DB_PATH):
    slots = tuple(item["slot"] for item in POSTS.values())
    placeholders = ",".join("?" for _ in slots)
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            f"SELECT slot FROM own_posts WHERE status='unknown' AND slot IN ({placeholders})",
            slots,
        ).fetchall()
        db.rollback()
    return [row[0] for row in rows]


def preflight(key, db_path=DB_PATH, *, profile_owned=False):
    if key not in POSTS:
        raise ValueError("Unknown approved post key")
    item = POSTS[key]
    now = now_utc()
    role = load_account_roles()["us28qt"]
    config = load_worker_config()
    limits = load_limits()
    times = posted_rows(db_path)
    hour = sum(now - timedelta(hours=1) <= stamp <= now for stamp in times)
    day = sum(now - timedelta(days=1) <= stamp <= now for stamp in times)
    latest = max(times) if times else None
    slot = own_slot(item["slot"], db_path)
    pm2 = pm2_state()
    checks = {
        "exact_caption_length_and_hash": 1 <= len(item["text"]) <= 470
        and hashlib.sha256(item["text"].encode()).hexdigest() == item["sha256"],
        "no_urls": not re.findall(r"https?://[^\s]+", item["text"]),
        "growth_stays_disabled": runtime_setting("growth.enabled") is False and not config.enabled,
        "selected_agent_processes_stopped": all(pm2.get(name, {}).get("status") == "stopped" for name in WORKER_NAMES),
        "account_active": login_active(),
        "account_role_allows_original_posts": role.enabled and role.own_posts and role.serves("cashbot"),
        "profile_unlocked": profile_owned or not profile_locked(PROFILE),
        "outside_quiet_hours": not in_quiet_hours(now, config.quiet_hours),
        "per_hour_quota": hour < (role.max_per_hour if role.max_per_hour is not None else limits.max_replies_per_hour),
        "per_day_quota": day < (role.max_per_day if role.max_per_day is not None else limits.max_replies_per_day),
        "minimum_post_spacing": latest is None or (now - latest).total_seconds() >= MIN_DELAY,
        "slot_has_no_previous_attempt": slot is None,
        "no_unknown_campaign_attempt": not unknown_campaign_attempts(db_path),
        "not_duplicate_caption": not any(existing.get("text") == item["text"] for existing in recent_own_posts(db_path)),
    }
    return {
        "at": now.isoformat(),
        "post_key": key,
        "label": item["label"],
        "caption": item["text"],
        "sha256": item["sha256"],
        "checks": checks,
        "blocked": [name for name, passed in checks.items() if not passed],
        "posts_last_hour": hour,
        "posts_last_24h": day,
        "last_post_at": latest.isoformat() if latest else None,
        "spacing_seconds": (now - latest).total_seconds() if latest else None,
        "growth_enabled": False,
        "agents": {name: pm2[name] for name in WORKER_NAMES},
    }


def recent_own_posts(db_path=DB_PATH):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            "SELECT text,slot,status FROM own_posts WHERE COALESCE(account,'us28qt')='us28qt' "
            "ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        db.rollback()
    return [{"text": row[0], "slot": row[1], "status": row[2]} for row in rows]


def write_json(path, payload):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def claim(item, db_path=DB_PATH):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM own_posts WHERE slot=?", (item["slot"],)).fetchone():
            db.rollback()
            raise ValueError("Attempt already exists for this slot; never replay")
        db.execute(
            "INSERT INTO own_posts(slot,kind,ref,text,status,created_at,account) VALUES(?,?,?,?,?,?,?)",
            (item["slot"], "owner_ab_content_test", "PLAN-188", item["text"], "unknown", now_utc().isoformat(), "us28qt"),
        )
        db.commit()


def update_attempt(item, proof, db_path=DB_PATH):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as db:
        db.execute(
            "UPDATE own_posts SET status=?,post_url=?,error_message=? WHERE slot=?",
            (proof["status"], proof.get("post_url"), proof.get("error_type"), item["slot"]),
        )
        db.commit()


def normalized(text_value):
    return " ".join((text_value or "").split())


def find_exact_post(browser, expected):
    browser._payloads.clear()
    url = browser._find_own_post(expected)
    if not url or not url.startswith("https://www.threads.com/@us28qt/post/"):
        return None
    browser._payloads.clear()
    browser.page.goto(url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(random.uniform(3.5, 4.5))
    browser._check_session()
    code = url.rstrip("/").split("/post/")[-1]
    for payload in [*browser._payloads, *browser._embedded_payloads(wide=True)]:
        for post in posts_from_payload(payload, "", keep_closed=True):
            if post.author.lower() == "us28qt" and post.thread_id == code and normalized(post.content) == normalized(expected):
                return url
    dom_rows = browser.page.evaluate("""() => [...document.querySelectorAll('a[href*="/post/"] time')].map(t=>{
      const a=t.closest('a'); let e=a;
      for(let i=0;i<12&&e?.parentElement;i++){e=e.parentElement;if(e.getAttribute('data-pressable-container')==='true')break;}
      return {href:a?.getAttribute('href')||'',text:e?.innerText||''};
    })""") or []
    for row in dom_rows:
        if f"/post/{code}" in row["href"] and normalized(expected) in normalized(row["text"]):
            return url
    return None


def publish_one(key, *, folder=FOLDER, db_path=DB_PATH, browser_factory=GrowthBrowser):
    item = POSTS[key]
    result_path = Path(folder) / f"publication-{key}.json"
    with (Path(folder) / "publish-two-posts.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check = preflight(key, db_path)
        if check["blocked"]:
            result = {"status": "blocked", "preflight": check}
            write_json(result_path, result)
            return result
        proof = {
            "plan": "PLAN-188", "post_key": key, "slot": item["slot"], "caption": item["text"],
            "sha256": item["sha256"], "status": "not_attempted", "submit_called": False,
            "attempt_started_at": now_utc().isoformat(), "preflight": check,
        }
        browser = None
        claimed = False
        try:
            browser = browser_factory(str(PROFILE))
            browser.__enter__()
            handle = (browser.adapter._discover_own_handle() or "").lstrip("@").lower()
            if handle != "us28qt":
                raise RuntimeError("Live Threads identity mismatch")
            browser.adapter._own_handle = handle
            check = preflight(key, db_path, profile_owned=True)
            if check["blocked"]:
                proof.update(status="not_published", preflight_before_submit=check)
                return proof

            dialog, box = browser._open_composer()
            box.click(force=True)
            box.fill(item["text"])
            if normalized(box.inner_text()) != normalized(item["text"]):
                raise RuntimeError("Composer caption did not match exactly")
            buttons = dialog.get_by_role("button", name=re.compile(r"^(Post|Đăng)$"))
            if not buttons.count():
                buttons = browser.page.get_by_role("button", name=re.compile(r"^(Post|Đăng)$"))
            if buttons.count() != 1:
                raise RuntimeError("Post button is missing or ambiguous")
            button = buttons.first
            if not browser.adapter._wait_for_post_button_ready(button):
                raise RuntimeError("Post button is not ready")
            # Recheck all mutable gates immediately before the single submit.
            check = preflight(key, db_path, profile_owned=True)
            if check["blocked"] or runtime_setting("growth.enabled") is not False:
                raise RuntimeError("Pre-submit guards changed")
            claim(item, db_path)
            claimed = True
            proof.update(status="unknown", submit_called=True, click_started_at=now_utc().isoformat(), preflight_before_submit=check)
            write_json(result_path, proof)
            button.click(timeout=10000)  # one submit only; exception => unknown, never click again
            found = None
            time.sleep(random.uniform(3.0, 4.0))
            found = find_exact_post(browser, item["text"])
            if found:
                proof.update(status="posted", post_url=found, exact_caption_verified=True)
        except BaseException as exc:
            proof["error_type"] = type(exc).__name__
            if not claimed:
                proof["status"] = "not_published"
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            if browser is not None:
                try:
                    browser.__exit__(None, None, None)
                except Exception as exc:
                    proof["browser_close_error_type"] = type(exc).__name__
            proof["finished_at"] = now_utc().isoformat()
            proof["growth_enabled_after"] = runtime_setting("growth.enabled")
            proof["agents_after"] = {name: pm2_state().get(name) for name in WORKER_NAMES}
            proof["profile_unlocked_after"] = not profile_locked(PROFILE)
            if claimed:
                update_attempt(item, proof, db_path)
            write_json(result_path, proof)
        return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("post", choices=tuple(POSTS))
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()
    result = publish_one(args.post) if args.publish else preflight(args.post)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if args.publish and result.get("status") == "posted" or not args.publish and not result.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
