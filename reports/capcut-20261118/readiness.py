"""Read-only readiness and source baseline for the single prepared CapCut trial."""
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import text

from app.core.database.core import SessionLocal
from app.features.threads.growth.config import CAPCUT_TRIAL_SOURCE, TargetBot, code_channel, code_map, load_account_roles
from app.features.threads.growth.session import profile_dir, profile_locked
from cashback_bot import store_campaign
from store_bot import hours

ROOT = Path(__file__).resolve().parents[2]
FOLDER = Path(__file__).resolve().parent
manifest = json.loads((FOLDER / "trial-manifest.json").read_text())
now = datetime.now(timezone.utc)
env = {**dotenv_values(ROOT / ".env"), **os.environ}
admins = tuple(int(x.strip()) for x in env["STORE_ADMIN_IDS"].replace(";", ",").split(",") if x.strip())
store_path = Path(env.get("STORE_DB_PATH") or "./data/store.sqlite")
if not store_path.is_absolute():
    store_path = ROOT / store_path
with closing(sqlite3.connect(store_path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute("BEGIN")
    product = dict(conn.execute("SELECT id,name,price,active,upstream_available,upstream_stock,synced_at FROM products WHERE id=2").fetchone())
    state = dict(conn.execute("SELECT key,value FROM state WHERE key IN ('closed_manual','closed_hours')"))
    closed = hours.status(hours.parse_window(state.get("closed_hours")), state.get("closed_manual") == "1", now)
with SessionLocal() as db:
    db.execute(text("SET TRANSACTION READ ONLY"))
    account = db.execute(text("SELECT login_status FROM accounts WHERE name=:name"), {"name": "threads_growth_anlinh"}).scalar_one_or_none()
    raw = dict(db.execute(text("SELECT key,value FROM runtime_settings WHERE key IN ('growth.enabled','growth.min_delay_sec')")).all())
    db.rollback()
role = load_account_roles()["anlinh"]
with closing(sqlite3.connect((ROOT / "data/threads_growth.sqlite").as_uri() + "?mode=ro", uri=True)) as conn:
    conn.row_factory = sqlite3.Row
    conn.execute("BEGIN")
    hour = conn.execute("SELECT COUNT(*) FROM growth_posts WHERE account='anlinh' AND status='posted' AND julianday(posted_at)>=julianday(?)", ((now - timedelta(hours=1)).isoformat(),)).fetchone()[0]
    day = conn.execute("SELECT COUNT(*) FROM growth_posts WHERE account='anlinh' AND status='posted' AND julianday(posted_at)>=julianday(?)", ((now - timedelta(days=1)).isoformat(),)).fetchone()[0]
    last = conn.execute("SELECT MAX(posted_at) FROM growth_posts WHERE account='anlinh' AND status='posted'").fetchone()[0]
    own = conn.execute("SELECT status,post_url FROM own_posts WHERE slot=?", ("capcut-trial-" + CAPCUT_TRIAL_SOURCE,)).fetchone()
    queue = [dict(row) for row in conn.execute("SELECT id,created_at,suggested_reply,actual_reply FROM growth_posts WHERE target_bot='ai_store' AND status='approved' ORDER BY id")]
queue_review = [{"id": r["id"], "mentions_capcut": "capcut" in (r["actual_reply"] or r["suggested_reply"] or "").lower(),
                 "suggested_action": "manual_review_before_reuse", "changed": False} for r in queue]
service = dict(line.split("=", 1) for line in subprocess.check_output(["systemctl", "show", "store-bot", "--property=ActiveState,SubState,MainPID,ExecMainStartTimestamp"], text=True).splitlines() if "=" in line)
started_raw = service.get("ExecMainStartTimestamp", "")
started = datetime.strptime(started_raw, "%a %Y-%m-%d %H:%M:%S %Z").replace(tzinfo=timezone.utc) if started_raw else None
handler = ROOT / "store_bot/bot.py"
handler_updated = datetime.fromtimestamp(handler.stat().st_mtime, timezone.utc)
pid = service.get("MainPID", "0")
try:
    service_cwd_ok = (Path("/proc") / pid / "cwd").resolve() == ROOT
except OSError:
    service_cwd_ok = False
last_time = datetime.fromisoformat(last.replace("Z", "+00:00")) if last else None
min_delay = int(raw.get("growth.min_delay_sec", "180"))
remaining_gap = max(0, min_delay - (now - last_time).total_seconds()) if last_time else 0
baseline = store_campaign.report(datetime.fromisoformat(manifest["prepared_at"].replace("Z", "+00:00")), 2, now, store_path,
                                 source_prefix=CAPCUT_TRIAL_SOURCE, exclude_user_ids=admins)
checks = {
    "source_registered_as_original_anlinh_post": code_map().get(CAPCUT_TRIAL_SOURCE) == (TargetBot.AI_STORE, None, "anlinh") and code_channel(CAPCUT_TRIAL_SOURCE) == "bài riêng",
    "catalog_price_matches": product["price"] == 34000,
    "catalog_available_cached": bool(product["active"] and product["upstream_available"] and product["upstream_stock"] > 0),
    "shop_open": not closed.closed,
    "account_active": account == "ACTIVE",
    "role_enabled_for_store": role.enabled and role.serves("ai_store"),
    "profile_unlocked": not profile_locked(profile_dir("anlinh")),
    "service_running": service.get("ActiveState") == "active" and service.get("SubState") == "running",
    "service_cwd_matches": service_cwd_ok,
    "handler_loaded_after_edit": started is not None and started > handler_updated,
    "trial_has_not_been_recorded_as_posted": not own or own["status"] != "posted",
    "baseline_read_succeeded": not baseline["errors"],
}
proof = {"observed_at": now.isoformat(), "status": "read_only_preflight_not_published", "checks": checks,
         "blocked_checks": [key for key, value in checks.items() if not value], "product": product,
         "shop": asdict(closed), "account_login_status": account, "role": asdict(role),
         "quota": {"reply_last_hour": hour, "reply_last_day": day, "min_delay_sec": min_delay, "remaining_gap_sec": remaining_gap, "reply_quota_has_room": role.max_per_hour is not None and role.max_per_day is not None and hour < role.max_per_hour and day < role.max_per_day and remaining_gap <= 0},
         "service": service, "handler_updated_at": handler_updated.isoformat(),
         "automatic_worker_enabled": str(raw.get("growth.enabled", "")).lower() in ("true", "1"),
         "queue_review": queue_review, "source_baseline": baseline,
         "notes": ["Preflight is not proof of publication; automatic worker/profile state can change before a manual post.",
                   "Cached stock is not guaranteed supply; no vendor call or purchase was made.",
                   "own_posts role is off; owner-approved one-off post is separate, not a scheduler/role change.",
                   "Reply quota applies to replies only; this owner-approved single original post does not add replies or change limits.",
                   "The Dashboard process needs its own reload for the new code_map; CLI reads fresh code."]}
(FOLDER / "trial-readiness.json").write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"observed_at": now.isoformat(), "blocked_checks": proof["blocked_checks"], "source_customers": baseline["cohort"]["customers"] if baseline["cohort"] else None,
                  "service_pid": pid, "account_login_status": account, "queue_approved": len(queue_review)}, ensure_ascii=False))
