"""PLAN-180: one explicit original post; default is read-only preflight."""
from __future__ import annotations

import argparse
import fcntl
import json
import random
import re
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import text

from app.core.database.core import SessionLocal
from app.features.threads.growth.browser import GrowthBrowser, _DOM_EXTRACT_JS, posts_from_dom_rows, posts_from_payload
from app.features.threads.growth.config import DB_PATH, load_account_roles, load_limits, load_worker_config
from app.features.threads.growth.session import profile_dir, profile_locked
from app.features.threads.growth.worker import in_quiet_hours

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[1]
AGENT_STATUS = ROOT / "reports/customer-agents/status.json"
WORKER = "Threads_Growth"


def stamp(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timestamp requires timezone")
    return parsed.astimezone(timezone.utc)


def validate_manifest(m, now, *, fresh=True):
    if any(m.get(k) != v for k, v in {"plan": "PLAN-180", "account": "us28qt", "account_handle": "us28qt",
                                     "slot": "threads-shopee-180-p1"}.items()):
        raise ValueError("Manifest identity/slot mismatch")
    body, products = m.get("text", ""), m.get("products", [])
    if not isinstance(body, str) or not 1 <= len(body) <= 470 or not 1 <= len(products) <= 3:
        raise ValueError("Invalid body or product count")
    if re.search(r"hoàn|chắc chắn|đảm bảo|đã mua|đã dùng", body, re.I):
        raise ValueError("Unsupported cashback/experience/guarantee claim")
    stamp(m["prepared_at"])
    ids = set()
    for p in products:
        link = urlsplit(p["affiliate_url"])
        if (link.scheme != "https" or link.hostname != "s.shopee.vn" or link.username or link.password
                or link.port not in (None, 443) or not link.path.strip("/") or p["affiliate_url"] not in body
                or not p.get("name") or not 1 <= int(p["price_vnd"]) <= 200000
                or int(p["shop_id"]) <= 0 or int(p["item_id"]) <= 0
                or not re.fullmatch(r"[A-Za-z0-9]{8}", p["sub_id"]) or p["sub_id"] in ids):
            raise ValueError("Invalid product/link/marker")
        ids.add(p["sub_id"])
        for key, age in (("quote_last_update", timedelta(hours=6)), ("verified_at", timedelta(minutes=30))):
            elapsed = now - stamp(p[key])
            if fresh and not -timedelta(minutes=5) <= elapsed <= age:
                raise ValueError("Stale or future product evidence")


def login_active():
    with SessionLocal() as db:
        db.execute(text("SET TRANSACTION READ ONLY"))
        value = db.execute(text("SELECT login_status FROM accounts WHERE name='threads_growth'" )).scalar_one_or_none()
        db.rollback()
    return value == "ACTIVE"


def preflight(m, db_path=DB_PATH, now=None):
    now = now or datetime.now(timezone.utc)
    validate_manifest(m, now)
    role, cfg, limits = load_account_roles()["us28qt"], load_worker_config(), load_limits()
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        rows = db.execute("SELECT posted_at FROM growth_posts WHERE status='posted' AND COALESCE(account,'us28qt')='us28qt' "
                          "UNION ALL SELECT created_at FROM own_posts WHERE status='posted' "
                          "AND COALESCE(account,'us28qt')='us28qt'").fetchall()
        existing = db.execute("SELECT status FROM own_posts WHERE slot=?", (m["slot"],)).fetchone()
    times = [stamp(row[0]) for row in rows if row[0]]
    hour = sum(now - timedelta(hours=1) <= t <= now for t in times)
    day = sum(now - timedelta(days=1) <= t <= now for t in times)
    gap = (now - max(times)).total_seconds() if times else None
    status = json.loads(AGENT_STATUS.read_text())
    checks = {"role": role.enabled and role.own_posts and role.serves("cashbot"), "worker_enabled": cfg.enabled,
              "outside_quiet_hours": not in_quiet_hours(now, cfg.quiet_hours), "account_active": login_active(),
              "profile_unlocked": not profile_locked(profile_dir("us28qt")),
              "worker_idle": status.get("phase") in ("waiting", "quiet_hours")
              and 0 <= (now - stamp(status["heartbeat_at"])).total_seconds() <= 180,
              "hour_budget": hour < (role.max_per_hour if role.max_per_hour is not None else limits.max_replies_per_hour),
              "day_budget": day < (role.max_per_day if role.max_per_day is not None else limits.max_replies_per_day),
              "spacing": gap is None or gap >= limits.min_delay_sec, "no_previous_attempt": existing is None}
    return {"observed_at": now.isoformat(), "checks": checks, "blocked": [k for k, v in checks.items() if not v],
            "combined_public_last_hour": hour, "combined_public_last_day": day, "gap_seconds": gap}


def write_json(path, value):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def pm2_state():
    rows = json.loads(subprocess.check_output(["pm2", "jlist"], text=True, timeout=15))
    return {r["name"]: {"pid": r["pid"], "status": r["pm2_env"]["status"],
                        "restarts": r["pm2_env"]["restart_time"]} for r in rows}


def pm2_action(action):
    subprocess.run(["pm2", action, WORKER], check=True, capture_output=True, text=True, timeout=75)


def claim(m, db_path, now):
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM own_posts WHERE slot=?", (m["slot"],)).fetchone():
            raise ValueError("Attempt already exists; use --verify only")
        db.execute("INSERT INTO own_posts(slot,kind,ref,text,status,created_at,account) VALUES(?,?,?,?,?,?,?)",
                   (m["slot"], "shopee_content_trial", ",".join("deal:" + str(p["item_id"]) for p in m["products"]),
                    m["text"], "unknown", now.isoformat(), "us28qt"))
        db.commit()


def valid_permalink(url):
    p = urlsplit(url or "")
    return p.scheme == "https" and p.hostname in ("threads.com", "www.threads.com", "threads.net", "www.threads.net") \
        and not p.username and not p.password and p.port in (None, 443) and p.path.startswith("/@us28qt/post/")


def verify_browser(browser, m, url=None):
    if url and not valid_permalink(url):
        raise ValueError("Unexpected permalink owner/domain")
    browser._payloads.clear()
    browser.page.goto(url or "https://www.threads.com/@us28qt", wait_until="domcontentloaded", timeout=60000)
    time.sleep(random.uniform(3, 5))
    browser._check_session()
    rows = []
    for payload in [*browser._payloads, *browser._embedded_payloads(wide=True)]:
        rows.extend(posts_from_payload(payload, "", keep_closed=True))
    rows.extend(posts_from_dom_rows(browser.page.evaluate(_DOM_EXTRACT_JS) or [], ""))
    for p in rows:
        if (p.author.lower() == "us28qt" and valid_permalink(p.post_url)
                and browser._content_matches_own(p.content, m["text"])
                and " ".join(m["text"].split()) in " ".join(p.content.split())
                and all(product["affiliate_url"] in p.content for product in m["products"])):
            return p.post_url
    return None


def finish(proof, m, folder, db_path):
    proof["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(folder / "trial-publication.json", proof)
    with closing(sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=rw", uri=True)) as db:
        db.execute("UPDATE own_posts SET status=?,post_url=?,error_message=? WHERE slot=?",
                   (proof["status"], proof.get("post_url"), proof.get("error_type"), m["slot"]))
        db.commit()


def execute(m, *, mode="preflight", db_path=DB_PATH, folder=FOLDER, browser_factory=GrowthBrowser):
    folder = Path(folder)
    now = datetime.now(timezone.utc)
    validate_manifest(m, now, fresh=mode != "verify")
    if mode == "preflight":
        return preflight(m, db_path, now)
    with (folder / "trial.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before, paused = pm2_state(), False
        if mode == "publish":
            check = preflight(m, db_path, now)
            if check["blocked"]:
                return {"status": "blocked", "preflight": check}
            proof = {"status": "not_attempted", "slot": m["slot"], "attempt_started_at": now.isoformat(),
                     "text": m["text"], "create_post_called": False, "post_url": None, "pm2_before": before,
                     "preflight": check}
        else:
            proof = json.loads((folder / "trial-publication.json").read_text())
            if proof.get("slot") != m["slot"] or proof.get("text") != m["text"]:
                raise ValueError("Manifest changed after publication attempt")
            if proof["status"] != "unknown":
                return {"status": "no_verification_needed"}
            if profile_locked(profile_dir("us28qt")):
                return {"status": "profile_busy"}
        claimed = mode == "verify"
        try:
            if before[WORKER]["status"] == "online":
                paused = True
                pm2_action("stop")
                if pm2_state()[WORKER]["status"] != "stopped":
                    raise RuntimeError("Worker did not stop")
            if profile_locked(profile_dir("us28qt")):
                raise RuntimeError("Profile remains locked")
            if mode == "publish":
                if in_quiet_hours(datetime.now(timezone.utc), load_worker_config().quiet_hours):
                    raise RuntimeError("Quiet hours began before publication")
                claim(m, db_path, now)
                claimed = True
                proof["status"] = "unknown"
                write_json(folder / "trial-publication.json", proof)
            with browser_factory(str(profile_dir("us28qt"))) as browser:
                live = (browser.adapter._discover_own_handle() or "").lstrip("@").lower()
                if live != "us28qt":
                    raise ValueError("Live identity mismatch")
                browser.adapter._own_handle = live
                proof["verified_live_handle"] = live
                if mode == "publish":
                    time.sleep(random.uniform(2, 4))
                    role, cfg = load_account_roles()["us28qt"], load_worker_config()
                    if not (role.enabled and role.own_posts and role.serves("cashbot") and cfg.enabled):
                        raise RuntimeError("Role or worker disabled before create_post")
                    if in_quiet_hours(datetime.now(timezone.utc), cfg.quiet_hours):
                        raise RuntimeError("Quiet hours began before create_post")
                    proof["create_post_called"] = True
                    write_json(folder / "trial-publication.json", proof)
                    proof["post_url"] = browser.create_post(m["text"])
                    write_json(folder / "trial-publication.json", proof)
                found = verify_browser(browser, m, proof.get("post_url"))
                if found:
                    proof.update(status="posted", post_url=found, permalink_content_and_links_verified=True)
        except BaseException as exc:
            proof["error_type"] = type(exc).__name__
            if not proof.get("create_post_called"):
                proof["status"] = "not_published"
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
        finally:
            try:
                if paused and pm2_state()[WORKER]["status"] == "stopped":
                    pm2_action("start")
                proof["pm2_after"] = pm2_state()
                proof["worker_restored"] = not paused or proof["pm2_after"][WORKER]["status"] == "online"
            except Exception as exc:
                proof.update(worker_restored=False, restore_error_type=type(exc).__name__)
            if claimed and (mode == "publish" or proof["status"] == "posted"):
                finish(proof, m, folder, db_path)
            elif claimed:
                write_json(folder / "trial-publication.json", proof)
            else:
                write_json(folder / "prepublication-failure.json", proof)
        return proof


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--publish", action="store_true")
    group.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    mode = "publish" if args.publish else "verify" if args.verify else "preflight"
    result = execute(json.loads((FOLDER / "manifest.json").read_text()), mode=mode)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "posted" or mode == "preflight" and not result.get("blocked") else 2


if __name__ == "__main__":
    raise SystemExit(main())
