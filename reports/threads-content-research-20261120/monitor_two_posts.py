"""Read-only, logged-out snapshots for the two owner-approved public Threads posts."""
from __future__ import annotations

import fcntl
import hashlib
import json
import random
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright
from sqlalchemy import text

from app.core import settings
from app.core.database.core import SessionLocal

FOLDER = Path(__file__).resolve().parent
STATE_PATH = FOLDER / "monitor-state.json"
LOCK_PATH = FOLDER / "monitor.lock"
EXPECTED = {
    "A": {
        "code": "Df9HXiUCWG1",
        "url": "https://www.threads.com/@us28qt/post/Df9HXiUCWG1",
        "caption_sha256": "e2d3238dae99ce9b4506717b20310096bdcf3df1de95a9e0477e83d39bad1a65",
    },
    "B": {
        "code": "Df9ILO9ieoK",
        "url": "https://www.threads.com/@us28qt/post/Df9ILO9ieoK",
        "caption_sha256": "2fc201cd263602f18ab010e1a6a241bab5750099766894754281d2d8f7ae0bec",
    },
}


def utc_now():
    return datetime.now(timezone.utc)


def short_view_label(body):
    for line in (body or "").splitlines()[:8]:
        value = line.strip()
        if re.fullmatch(r"[\d.,]+\s*[KMB]?\s+views?", value, re.I):
            return value
    return None


def numeric_view_label(value):
    if not value:
        return None
    match = re.fullmatch(r"([\d,.]+)\s*([KMB]?)\s+views?", value.strip(), re.I)
    if not match:
        return None
    amount = float(match.group(1).replace(",", ""))
    scale = {"": 1, "K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[match.group(2).upper()]
    return round(amount * scale)


def walk_parent(node, code, found):
    if isinstance(node, dict):
        user = node.get("user")
        caption = node.get("caption")
        if (node.get("code") == code and isinstance(user, dict) and isinstance(caption, dict)
                and isinstance(caption.get("text"), str)):
            info = node.get("text_post_app_info") or {}
            found.append({
                "author": user.get("username"),
                "caption": caption["text"],
                "likes": node.get("like_count"),
                "replies": info.get("direct_reply_count"),
                "reposts": node.get("repost_count"),
                "quotes": node.get("quote_count"),
                "views_exact": node.get("view_count"),
            })
        for child in node.values():
            walk_parent(child, code, found)
    elif isinstance(node, list):
        for child in node:
            walk_parent(child, code, found)


def read_one(page, key, expected):
    payloads = []

    def capture(response):
        try:
            content_type = (response.headers or {}).get("content-type", "")
            if "json" not in content_type and "graphql" not in response.url:
                return
            for line in response.text().splitlines():
                line = line.removeprefix("for (;;);").strip()
                if line.startswith(("{", "[")):
                    payloads.append(json.loads(line))
        except Exception:
            return

    page.on("response", capture)
    response = page.goto(expected["url"], wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(int(random.uniform(3500, 4800)))
    if page.url.split("?")[0].rstrip("/") != expected["url"].rstrip("/"):
        raise ValueError("Threads redirected away from expected public permalink")

    found = []
    for raw in page.locator('script[type="application/json"]').all_text_contents():
        if "text_post_app_info" in raw or "thread_items" in raw:
            try:
                walk_parent(json.loads(raw), expected["code"], found)
            except (ValueError, TypeError):
                continue
    for payload in payloads:
        walk_parent(payload, expected["code"], found)
    unique = {(item["author"], item["caption"]): item for item in found}
    if len(unique) != 1:
        raise ValueError("Expected public post did not resolve uniquely")
    post = next(iter(unique.values()))
    if post["author"] != "us28qt" or hashlib.sha256(post["caption"].encode()).hexdigest() != expected["caption_sha256"]:
        raise ValueError("Public post identity/caption hash mismatch")

    header_lines = page.evaluate("() => (document.body.innerText || '').split('\\n').slice(0, 8)") or []
    snapshot = {
        "status": "available",
        "observed_at": utc_now().isoformat(),
        "http_status": response.status if response else None,
        "views_label": short_view_label("\n".join(header_lines)),
        "views_exact": post["views_exact"] if isinstance(post["views_exact"], int) else None,
        "likes": post["likes"] if isinstance(post["likes"], int) else None,
        "replies": post["replies"] if isinstance(post["replies"], int) else None,
        "reposts": post["reposts"] if isinstance(post["reposts"], int) else None,
        "quotes": post["quotes"] if isinstance(post["quotes"], int) else None,
        "caption_verified": True,
        "author_verified": True,
    }
    return snapshot



def compare(old, new, thresholds):
    changes = []
    if isinstance(old.get("replies"), int) and isinstance(new.get("replies"), int):
        if new["replies"] > old["replies"]:
            changes.append({"type": "new_reply_count", "delta": new["replies"] - old["replies"]})
    if isinstance(old.get("likes"), int) and isinstance(new.get("likes"), int):
        if new["likes"] - old["likes"] >= thresholds["new_likes"]:
            changes.append({"type": "likes_increased", "delta": new["likes"] - old["likes"]})
    old_label = numeric_view_label(old.get("views_label"))
    new_label = numeric_view_label(new.get("views_label"))
    if (old_label is not None and new_label is not None
            and new_label - old_label >= thresholds.get("views_increase", 25)):
        changes.append({"type": "views_increased", "delta": new_label - old_label,
                        "from": old.get("views_label"), "to": new["views_label"], "rounded_label": True})
    elif ((old_label is None or new_label is None) and new.get("views_label")
          and new.get("views_label") != old.get("views_label")):
        changes.append({"type": "views_label_changed", "from": old.get("views_label"), "to": new["views_label"]})
    if (isinstance(old.get("views_exact"), int) and isinstance(new.get("views_exact"), int)
            and new["views_exact"] - old["views_exact"] >= 10):
        changes.append({"type": "views_increased", "delta": new["views_exact"] - old["views_exact"]})
    return changes


def run(state_path=STATE_PATH):
    with LOCK_PATH.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = json.loads(Path(state_path).read_text())
        if set(state.get("posts", {})) != set(EXPECTED):
            raise ValueError("Monitor state has unexpected post set")
        deadline = datetime.fromisoformat(state["monitor_deadline_vn"])
        now = utc_now()
        if now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh")) >= deadline:
            state["monitor_status"] = "complete"
            state["completed_at"] = now.isoformat()
            atomic_write(state_path, state)
            return {"status": "complete", "automation_should_be_deleted": True, "public_actions": 0}

        # The monitor must never revive or compete with the agents the owner cancelled.
        try:
            pm2_rows = json.loads(subprocess.check_output(["pm2", "jlist"], text=True, timeout=15))
            pm2 = {row["name"]: row["pm2_env"]["status"] for row in pm2_rows}
            with SessionLocal() as db:
                db.execute(text("SET TRANSACTION READ ONLY"))
                growth_enabled = settings.get_bool("growth.enabled", db=db)
                db.rollback()
            agent_state_safe = (growth_enabled is False and pm2.get("Threads_Growth") == "stopped"
                                and pm2.get("CapCut_Agent_Supervisor") == "stopped")
        except Exception as exc:
            state["last_check_at"] = now.isoformat()
            state["last_security_error_type"] = type(exc).__name__
            state["last_errors"] = [{"type": "agent_state_unavailable", "notify": True}]
            state["public_actions"] = 0
            atomic_write(state_path, state)
            return {"status": "blocked_state_unavailable", "error_type": type(exc).__name__, "notify": True,
                    "public_actions": 0}
        if not agent_state_safe:
            state["last_check_at"] = now.isoformat()
            state["last_errors"] = [{"type": "growth_agent_state_changed", "notify": True}]
            state["public_actions"] = 0
            atomic_write(state_path, state)
            return {"status": "blocked_agent_state_changed", "notify": True, "public_actions": 0}

        snapshots, events, errors = {}, [], []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for key, expected in EXPECTED.items():
                    page = browser.new_page(viewport={"width": 1280, "height": 900})
                    try:
                        current = read_one(page, key, expected)
                        previous = state["posts"][key]["latest_metrics"]
                        changes = compare(previous, current, state["alert_thresholds"])
                        if changes:
                            events.append({"post": key, "changes": changes})
                            state["posts"][key]["last_alert_at"] = current["observed_at"]
                            state["posts"][key]["last_alert_metrics"] = current
                        state["posts"][key]["latest_metrics"] = current
                        state["posts"][key]["error_streak"] = 0
                        snapshots[key] = current
                    except Exception as exc:
                        row = state["posts"][key]
                        row["error_streak"] = int(row.get("error_streak", 0)) + 1
                        if row["error_streak"] >= 2 and not row.get("error_notified"):
                            errors.append({"post": key, "consecutive_failures": row["error_streak"], "error_type": type(exc).__name__})
                            row["error_notified"] = True
                        else:
                            errors.append({"post": key, "consecutive_failures": row["error_streak"], "error_type": type(exc).__name__, "notify": False})
                    finally:
                        # Closing each temporary page also discards its response listener and captured payloads.
                        page.close()
            finally:
                browser.close()

        state["last_check_at"] = now.isoformat()
        state["last_snapshot"] = snapshots
        state["last_events"] = events
        state["last_errors"] = errors
        state["public_actions"] = 0
        atomic_write(state_path, state)
        return {
            "status": "checked",
            "checked_at": now.isoformat(),
            "snapshots": snapshots,
            "new_metric_events": events,
            "errors": errors,
            "notify": bool(events or any(error.get("notify", True) for error in errors)),
            "public_actions": 0,
            "personal_data_collected": False,
        }


def atomic_write(path, payload):
    target = Path(path)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=target.parent,
                                     prefix=".threads-monitor-", suffix=".tmp", delete=False) as out:
        json.dump(payload, out, ensure_ascii=False, indent=2)
        out.write("\n")
        tmp = Path(out.name)
    tmp.replace(target)


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
