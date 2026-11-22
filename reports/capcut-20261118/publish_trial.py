"""One owner-authorized original CapCut post; no scheduler, replies or bulk messages.

Default is read-only preflight. --publish consumes one durable attempt; never retry blindly.
"""
import argparse
import fcntl
import json
import random
import sqlite3
import subprocess
import sys
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.features.threads.growth.browser import GrowthBrowser, posts_from_payload, posts_from_dom_rows, _DOM_EXTRACT_JS
from app.features.threads.growth.config import CAPCUT_TRIAL_SOURCE
from app.features.threads.growth.session import profile_dir, profile_locked

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--publish", action="store_true")
parser.add_argument("--retry-not-published", action="store_true", help="Only retry an attempt proven to have stopped before create_post")
args = parser.parse_args()
subprocess.run([sys.executable, str(FOLDER / "readiness.py")], check=True)
readiness = json.loads((FOLDER / "trial-readiness.json").read_text())
manifest_path = FOLDER / "trial-manifest.json"
manifest = json.loads(manifest_path.read_text())
expected_url = "https://t.me/aipass_shop_bot?start=buy_2_" + CAPCUT_TRIAL_SOURCE
assert manifest["account"] == "anlinh" and manifest["account_handle"] == "anlinh_08_10"
assert manifest["source"] == CAPCUT_TRIAL_SOURCE and manifest["telegram_url"] == expected_url
assert manifest["text"].endswith(expected_url) and len(manifest["text"]) <= 470
if readiness["blocked_checks"]:
    raise SystemExit("Readiness blocked: " + ",".join(readiness["blocked_checks"]))
if not args.publish:
    print("preflight=PASS; not published (add --publish for the already authorized single attempt)")
    raise SystemExit(0)

slot = "capcut-trial-" + CAPCUT_TRIAL_SOURCE
profile = profile_dir("anlinh")
proof = {"attempt_started_at": datetime.now(timezone.utc).isoformat(), "account": "anlinh",
         "expected_handle": manifest["account_handle"], "source": CAPCUT_TRIAL_SOURCE,
         "text": manifest["text"], "status": "not_attempted", "post_url": None,
         "direct_owner_authorized": True, "reply_sent": False, "role_or_quota_changed": False}

def save_result(status, url=None, error=None):
    stamp = datetime.now(timezone.utc).isoformat()
    proof.update(status=status, post_url=url, finished_at=stamp, error=error, create_post_called=entered_create)
    (FOLDER / "trial-publication.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    manifest.update(status=status, post_url=url, published_at=stamp if status == "posted" else None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with closing(sqlite3.connect((ROOT / "data/threads_growth.sqlite").as_uri() + "?mode=rw", uri=True)) as conn:
        conn.execute("UPDATE own_posts SET status=?,post_url=?,error_message=? WHERE slot=?", (status, url, error, slot))
        conn.commit()

with open("/tmp/toolsauto-capcut-trial.lock", "w") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if profile_locked(profile):
        raise SystemExit("Profile busy; no browser opened and no post attempted")
    # Durable attempt fence before opening the browser. An interrupted run cannot silently replay.
    with closing(sqlite3.connect((ROOT / "data/threads_growth.sqlite").as_uri() + "?mode=rw", uri=True)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute("SELECT status FROM own_posts WHERE slot=?", (slot,)).fetchone()
        if existing:
            prior = json.loads((FOLDER / "trial-publication.json").read_text())
            if not (args.retry_not_published and existing[0] == "not_published" and
                    prior.get("create_post_called") is False and prior.get("status") == "not_published"):
                raise SystemExit("Trial already has an attempt record; no replay of an uncertain or posted attempt")
            conn.execute("UPDATE own_posts SET status='unknown',error_message=NULL,created_at=? WHERE slot=?",
                         (proof["attempt_started_at"], slot))
        else:
            conn.execute("INSERT INTO own_posts(slot,kind,ref,text,status,created_at,account) VALUES (?,?,?,?,?,?,?)",
                         (slot, "capcut_trial", "product:2", manifest["text"], "unknown", proof["attempt_started_at"], "anlinh"))
        conn.commit()
    proof["status"] = "unknown"
    (FOLDER / "trial-publication.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
    entered_create = False
    try:
        with GrowthBrowser(str(profile)) as browser:
            # Resolve authenticated identity again from the live session, not only its cached file.
            discovered = browser.adapter._discover_own_handle()
            live_handle = (discovered or "").lstrip("@").lower()
            if live_handle != manifest["account_handle"]:
                raise RuntimeError("Live authenticated account does not match the approved An Linh account")
            browser.adapter._own_handle = discovered
            proof["verified_live_handle"] = live_handle
            time.sleep(random.uniform(2.0, 4.0))
            entered_create = True
            url = browser.create_post(manifest["text"])
            if not url:
                save_result("unknown", error="Publish returned without a verifiable permalink; no retry")
            else:
                parsed = urlsplit(url)
                if parsed.hostname not in ("www.threads.net", "threads.net", "www.threads.com", "threads.com") or not parsed.path.startswith("/@" + live_handle + "/post/"):
                    raise RuntimeError("Returned permalink does not match the approved account")
                browser._payloads.clear()
                browser.page.goto(url, wait_until="domcontentloaded", timeout=60000)
                time.sleep(random.uniform(3.0, 5.0))
                browser._check_session()
                found = []
                for payload in [*browser._payloads, *browser._embedded_payloads(wide=True)]:
                    found.extend(posts_from_payload(payload, "", keep_closed=True))
                found.extend(posts_from_dom_rows(browser.page.evaluate(_DOM_EXTRACT_JS) or [], ""))
                matches = [p for p in found if p.author.lower() == live_handle and
                           CAPCUT_TRIAL_SOURCE in p.content and "34.000" in p.content and "CapCut" in p.content]
                if matches:
                    proof["permalink_content_verified"] = True
                    save_result("posted", url)
                else:
                    save_result("unknown", url, "Permalink returned but fresh content verification incomplete; no retry")
    except Exception as exc:
        save_result("unknown" if entered_create else "not_published", error=type(exc).__name__ + ": " + str(exc)[:300])
    print(json.dumps({"status": proof["status"], "post_url": proof["post_url"],
                      "verified_live_handle": proof.get("verified_live_handle"), "error": proof.get("error")}, ensure_ascii=False))
