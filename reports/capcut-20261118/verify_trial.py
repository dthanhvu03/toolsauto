"""Read-only verification of the one attempted trial; never creates a post or retries."""
import json
import random
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from app.features.threads.growth.browser import GrowthBrowser, posts_from_dom_rows, posts_from_payload, _DOM_EXTRACT_JS
from app.features.threads.growth.config import CAPCUT_TRIAL_SOURCE
from app.features.threads.growth.scanner import THREADS_HOST
from app.features.threads.growth.session import profile_dir, profile_locked

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
manifest_path = FOLDER / "trial-manifest.json"
manifest = json.loads(manifest_path.read_text())
publication_path = FOLDER / "trial-publication.json"
publication = json.loads(publication_path.read_text())
if publication["status"] != "unknown":
    raise SystemExit("Only verify an unknown outcome; no publishing is performed")
profile = profile_dir("anlinh")
if profile_locked(profile):
    raise SystemExit("Profile busy; no browser opened")
proof = {"observed_at": datetime.now(timezone.utc).isoformat(), "mode": "read_only_no_create_post",
         "source": CAPCUT_TRIAL_SOURCE, "expected_handle": manifest["account_handle"], "found": False,
         "post_url": None, "retries_published": 0}
with GrowthBrowser(str(profile)) as browser:
    live = (browser.adapter._discover_own_handle() or "").lstrip("@").lower()
    if live != manifest["account_handle"]:
        raise SystemExit("Live authenticated identity differs; no action taken")
    proof["verified_live_handle"] = live
    browser._payloads.clear()
    browser.page.goto(f"{THREADS_HOST}/@{live}", wait_until="domcontentloaded", timeout=60000)
    for step in range(5):
        time.sleep(random.uniform(3.0, 5.0))
        browser._check_session()
        rows = []
        for payload in [*browser._payloads, *browser._embedded_payloads(wide=True)]:
            rows.extend(posts_from_payload(payload, "", keep_closed=True))
        rows.extend(posts_from_dom_rows(browser.page.evaluate(_DOM_EXTRACT_JS) or [], ""))
        matches = [row for row in rows if row.author.lower() == live and CAPCUT_TRIAL_SOURCE in row.content]
        if matches:
            match = matches[0]
            proof.update(found=True, post_url=match.post_url, price_visible="34.000" in match.content,
                         exact_text_visible=" ".join(manifest["text"].split()) in " ".join(match.content.split()))
            break
        browser.page.mouse.wheel(0, random.randint(450, 850))
    proof["profile_url"] = browser.page.url
    proof["source_text_visible"] = CAPCUT_TRIAL_SOURCE in (browser.page.locator("body").inner_text() or "")
(FOLDER / "trial-verification.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
if proof["found"] and proof["price_visible"]:
    publication.update(initial_publish_error=publication.get("error"), error=None,
                       status="posted", post_url=proof["post_url"], verified_at=proof["observed_at"],
                       verification="Independent read-only profile lookup found unique source and price; no repost")
    manifest.update(status="posted", post_url=proof["post_url"], published_at=publication["attempt_started_at"],
                    verified_at=proof["observed_at"], publish_time_is_attempt_start=True)
    publication_path.write_text(json.dumps(publication, ensure_ascii=False, indent=2) + "\n")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    with closing(sqlite3.connect((ROOT / "data/threads_growth.sqlite").as_uri() + "?mode=rw", uri=True)) as conn:
        conn.execute("UPDATE own_posts SET status='posted',post_url=?,error_message=NULL WHERE slot=? AND status='unknown'",
                     (proof["post_url"], "capcut-trial-" + CAPCUT_TRIAL_SOURCE))
        conn.commit()
print(json.dumps(proof, ensure_ascii=False))
