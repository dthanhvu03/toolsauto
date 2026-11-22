"""PLAN189: bounded owner-authorized public conversation agent; old workers stay stopped."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import random
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

from app.features.threads.growth import browser as module_import

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
STATE = FOLDER / "state.json"
PATTERN = re.compile(r"^https://www\.threads\.com/@([\w.]+)/post/([\w-]+)$")
QUERIES = ("mang cơm đi làm", "bàn phím cơ", "mua đồ", "đồ gia dụng", "góc làm việc", "săn sale")
KEYWORDS = re.compile(r"cơm|bàn phím|đi làm|văn phòng|mua|hộp|đồ|sale|chiikawa|giá|tiền", re.I)


def now():
    return datetime.now(timezone.utc)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def save(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def helper():
    spec = importlib.util.spec_from_file_location("conversation_publisher", ROOT / "reports/threads-genz-20261121/publish_two_posts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def policy_blocks(state, at, author=None, code=None):
    if not state.get("enabled"):
        return ["disabled"]
    if at >= datetime.fromisoformat(state["deadline"]):
        return ["complete"]
    history = state.get("history", [])
    if state.get("paused") or any(h["status"] == "unknown" for h in history):
        return ["paused_or_unknown"]
    recent = [h for h in history if datetime.fromisoformat(h["at"]) >= at - timedelta(hours=24)]
    blocked = ["daily_cap"] if len(recent) >= 3 else []
    if history and (at - max(datetime.fromisoformat(h["at"]) for h in history)).total_seconds() < 2700:
        blocked.append("comment_spacing")
    if author and any(h["author"] == author and datetime.fromisoformat(h["at"]) >= at - timedelta(days=7) for h in history):
        blocked.append("author_cooldown")
    if code and any(h["code"] == code for h in history):
        blocked.append("target_attempted")
    return blocked


def eligible(post, at):
    try:
        age = (at - datetime.fromtimestamp(post["taken_at"], timezone.utc)).total_seconds()
        return (0 <= age <= 172800 and not post["is_reply"] and post["author"] not in ("us28qt", "anlinh_08_10")
                and (post["likes"] >= 50 or post["replies"] >= 15) and KEYWORDS.search(post["text"])
                and re.search(r"[ăđơưĂĐƠƯ\u1ea0-\u1ef9]", post["text"]))
    except (KeyError, TypeError, ValueError):
        return False


def collect(node, out):
    if isinstance(node, dict):
        caption, user = node.get("caption"), node.get("user")
        if isinstance(caption, dict) and isinstance(caption.get("text"), str) and isinstance(user, dict) and node.get("code"):
            info = node.get("text_post_app_info") or {}
            code, author = node["code"], user.get("username")
            if author:
                out[code] = {"code": code, "author": author, "text": caption["text"], "sha256": digest(caption["text"]),
                             "url": f"https://www.threads.com/@{author}/post/{code}", "taken_at": node.get("taken_at"),
                             "likes": node.get("like_count") or 0, "replies": info.get("direct_reply_count") or 0,
                             "is_reply": bool(info.get("is_reply")), "can_reply": info.get("can_reply"),
                             "already_replied": info.get("has_viewer_replied"),
                             "reply_to_author": (info.get("reply_to_author") or {}).get("username")}
        for value in node.values():
            collect(value, out)
    elif isinstance(node, list):
        for value in node:
            collect(value, out)


def page_posts(page, payloads=()):
    out = {}
    for raw in page.locator('script[type="application/json"]').all_text_contents():
        try:
            collect(json.loads(raw), out)
        except (ValueError, TypeError):
            pass
    for payload in payloads:
        collect(payload, out)
    return out


def old_author(module, author, at):
    with closing(sqlite3.connect(Path(module.DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        row = db.execute("SELECT 1 FROM growth_posts WHERE author=? AND status='posted' AND julianday(posted_at)>=julianday(?) LIMIT 1",
                         (author, (at - timedelta(days=7)).isoformat())).fetchone()
        return bool(row)


def guards(module, state, text="scan", code="scan", author=None, owned=False):
    blocked = policy_blocks(state, now(), author, code)
    module.POSTS = {"current": {"text": text, "sha256": digest(text), "slot": "conversation189-" + code, "label": "conversation"}}
    check = module.preflight("current", profile_owned=owned)
    blocked += check["blocked"]
    latest = check.get("last_post_at")
    if latest and (now() - datetime.fromisoformat(latest)).total_seconds() < module.load_limits().min_delay_sec:
        blocked.append("configured_post_spacing")
    with closing(sqlite3.connect(Path(module.DB_PATH).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        if db.execute("SELECT 1 FROM own_posts WHERE slot LIKE ? AND status='unknown' LIMIT 1", ("conversation189-%",)).fetchone():
            blocked.append("unresolved_attempt_in_db")
    if author and old_author(module, author, now()):
        blocked.append("previous_growth_author")
    if not owned and module.profile_locked(module.PROFILE):
        blocked.append("profile_busy")
    return sorted(set(blocked))


def scan(module, state):
    blocked = guards(module, state)
    if blocked:
        return {"status": "blocked", "blocked": blocked}
    candidates = {}
    offset = state.get("scan_round", 0) % len(QUERIES)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            try:
                for index in range(3):
                    page = context.new_page()
                    try:
                        query = QUERIES[(offset + index) % len(QUERIES)]
                        page.goto("https://www.threads.com/search?q=" + quote(query) + "&serp_type=default", wait_until="domcontentloaded", timeout=45000)
                        page.wait_for_timeout(int(random.uniform(3000, 4500)))
                        for code, post in page_posts(page).items():
                            if eligible(post, now()) and not policy_blocks(state, now(), post["author"], code) and not old_author(module, post["author"], now()):
                                candidates[code] = post
                    finally:
                        page.close()
            finally:
                context.close()
        finally:
            browser.close()
    state["scan_round"] = offset + 3
    state["last_scan_at"] = now().isoformat()
    save(STATE, state)
    result = {"status": "scanned", "at": state["last_scan_at"], "candidates": list(candidates.values())[:12]}
    save(FOLDER / "candidates.json", result)
    return result


def inspect(url):
    if not PATTERN.fullmatch(url):
        raise ValueError("Unexpected public target URL")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            try:
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_timeout(int(random.uniform(3000, 4500)))
                    post = page_posts(page).get(PATTERN.fullmatch(url)[2])
                    return {"status": "inspected", "at": now().isoformat(), "post": post,
                            "visible_context": page.locator("body").inner_text().split("Related threads")[0][:6500]}
                finally:
                    page.close()
            finally:
                context.close()
        finally:
            browser.close()


def validate_proposal(proposal, target, at):
    text = proposal["text"]
    if not 15 <= len(text) <= 280 or re.search(r"https?://|www\.|t\.me|shopee\.|@[\w.]|inbox|ib mình|link bio", text, re.I):
        raise ValueError("Reply length/link/promotion restriction")
    if not proposal.get("reason") or not proposal.get("context_read_at"):
        raise ValueError("Missing editorial justification or inspected context")
    age = (at - datetime.fromisoformat(proposal["context_read_at"])).total_seconds()
    if not 0 <= age <= 900 or not PATTERN.fullmatch(proposal["url"]):
        raise ValueError("Invalid target or stale context")
    if (not target or target["url"] != proposal["url"] or target["sha256"] != proposal["parent_sha256"]
            or not eligible(target, at) or target["can_reply"] is False or target["already_replied"] is True):
        raise ValueError("Target changed, ineligible or already answered")


def publish(module, state, proposal):
    match = PATTERN.fullmatch(proposal["url"])
    if not match:
        raise ValueError("Invalid target URL")
    author, code = match.groups()
    blocked = guards(module, state, proposal["text"], code, author)
    if blocked:
        return {"status": "blocked", "blocked": blocked}
    attempt = None
    try:
        with module.GrowthBrowser(str(module.PROFILE)) as browser:
            handle = (browser.adapter._discover_own_handle() or "").lstrip("@").lower()
            if handle != "us28qt":
                raise ValueError("Live identity mismatch")
            browser.adapter._own_handle = handle
            browser.page.goto(proposal["url"], wait_until="domcontentloaded", timeout=45000)
            browser._pause(3, 4)
            browser._check_session()
            if browser.page.url.split("?")[0].rstrip("/") != proposal["url"]:
                raise ValueError("Target redirected")
            target = page_posts(browser.page, browser._payloads).get(code)
            validate_proposal(proposal, target, now())
            box = browser.adapter._find_first_visible(module_import.INLINE_REPLY_SELECTORS, timeout_ms=6000)
            if box is None:
                button = browser.adapter._find_first_visible(module_import.REPLY_BUTTON_SELECTORS, timeout_ms=5000)
                if button is None:
                    raise ValueError("Reply control missing")
                button.click()
                browser._pause(1, 2)
                box = browser.adapter._find_first_visible(tuple(browser.adapter.TEXTBOX_SELECTORS), timeout_ms=8000)
            if box is None:
                raise ValueError("Reply textbox missing")
            box.click()
            box.fill(proposal["text"])
            if " ".join(box.inner_text().split()) != " ".join(proposal["text"].split()):
                raise ValueError("Composer mismatch")
            scope = box.locator(f"xpath=ancestor::div[.//div[@role='button'][{module_import._POST_LABEL_XPATH}]][1]")
            button = None
            if scope.count():
                loc = scope.first.locator(f"xpath=.//div[@role='button'][{module_import._POST_LABEL_XPATH}]").last
                if loc.count() and loc.is_visible():
                    button = loc
            button = button or browser.adapter._find_first_visible(module_import.DIALOG_POST_SELECTORS, timeout_ms=4000)
            if button is None or not browser.adapter._wait_for_post_button_ready(button):
                raise ValueError("Reply submit missing")
            blocked = guards(module, state, proposal["text"], code, author, owned=True)
            if blocked:
                return {"status": "blocked", "blocked": blocked}
            attempt = {"code": code, "author": author, "target_url": proposal["url"], "text": proposal["text"],
                       "reason": proposal["reason"], "at": now().isoformat(), "status": "unknown", "submit_called": False}
            module.claim(module.POSTS["current"])
            with closing(sqlite3.connect(module.DB_PATH)) as db:
                db.execute("UPDATE own_posts SET kind='viral_comment',ref=? WHERE slot=?", (proposal["url"], "conversation189-" + code))
                db.commit()
            state["history"].append(attempt)
            save(STATE, state)
            attempt["submit_called"] = True
            save(STATE, state)
            browser._payloads.clear()
            button.click(timeout=10000)
            browser._pause(3, 4)
            browser._check_session()
            # Verify on the exact parent page; only an own reply directed at this author qualifies.
            browser.page.goto(proposal["url"], wait_until="domcontentloaded", timeout=45000)
            browser._pause(3, 4)
            browser._check_session()
            found = [x for x in page_posts(browser.page, browser._payloads).values()
                     if x["author"] == "us28qt" and x["text"] == proposal["text"] and x["reply_to_author"] == author]
            if len({x["code"] for x in found}) == 1:
                reply = found[0]
                browser.page.goto(reply["url"], wait_until="domcontentloaded", timeout=45000)
                browser._pause(2, 3)
                own = page_posts(browser.page, browser._payloads).get(reply["code"])
                if own and own["text"] == proposal["text"] and own["author"] == "us28qt" and own["reply_to_author"] == author:
                    attempt.update(status="posted", post_url=reply["url"], exact_caption_verified=True, parent_verified=True)
    except Exception as exc:
        state["paused"] = True
        state["last_error_type"] = type(exc).__name__
        save(STATE, state)
        raise
    finally:
        if attempt is not None:
            if attempt["status"] == "unknown":
                state["paused"] = True
            module.update_attempt(module.POSTS["current"], attempt)
            save(STATE, state)
            save(FOLDER / ("attempt-" + code + ".json"), attempt)
    return attempt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("scan", "inspect", "publish", "status"))
    parser.add_argument("--url")
    parser.add_argument("--proposal", type=Path)
    args = parser.parse_args()
    with (FOLDER / "agent.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(STATE.read_text())
        module = helper()
        if args.command == "scan":
            result = scan(module, state)
        elif args.command == "inspect":
            result = inspect(args.url)
            save(FOLDER / "inspection.json", result)
        elif args.command == "publish":
            result = publish(module, state, json.loads(args.proposal.read_text()))
        else:
            result = {"status": "checked", "blocked": guards(module, state), "state": state}
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()