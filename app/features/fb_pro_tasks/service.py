"""
Hybrid tracker for Meta Professional Dashboard weekly tasks.

Scoped per account + target_page (Meta tasks are page-level).
Runtime JSON under storage/db/config/.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import RUNTIME_CONFIG_DIR
from app.constants import JobStatus, JobType
from app.core.database.models import Account, Job

logger = logging.getLogger(__name__)

CONFIG_PATH = RUNTIME_CONFIG_DIR / "fb_pro_weekly_tasks.json"
META_DASHBOARD_URL = "https://www.facebook.com/professional_dashboard/status"
LOCAL_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

DEFAULT_TARGETS = {"posts": 5, "reels": 5, "interactions": 10}


def _today_local() -> date:
    return datetime.now(LOCAL_TZ).date()


def _sunday_week_bounds(ref: date | None = None) -> tuple[date, date]:
    """Meta VN weekly tasks: Sunday → Saturday."""
    d = ref or _today_local()
    days_since_sun = (d.weekday() + 1) % 7
    start = d - timedelta(days=days_since_sun)
    end = start + timedelta(days=6)
    return start, end


def _parse_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _day_start_ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 0, 0, 0, tzinfo=LOCAL_TZ).timestamp())


def _day_end_exclusive_ts(d: date) -> int:
    nxt = d + timedelta(days=1)
    return _day_start_ts(nxt)


def normalize_page_url(url: str | None) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    try:
        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        path = (parsed.path or "").rstrip("/").lower()
        return f"https://{host}{path}" if host else raw.rstrip("/").lower()
    except Exception:
        return raw.rstrip("/").lower()


def page_slug(url: str | None) -> str:
    norm = normalize_page_url(url)
    if not norm:
        return ""
    path = urlparse(norm).path.strip("/")
    return path.split("/")[0] if path else urlparse(norm).netloc


def scope_key(account_id: int | None, target_page: str | None) -> str:
    page = normalize_page_url(target_page)
    if account_id and page:
        return f"acc:{int(account_id)}|page:{page}"
    if page:
        return f"page:{page}"
    if account_id:
        return f"acc:{int(account_id)}"
    return "global"


def default_scope_body() -> dict[str, Any]:
    start, end = _sunday_week_bounds()
    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "targets": dict(DEFAULT_TARGETS),
        "manual": {
            "interactions": 0,
            "posts_override": None,
            "reels_override": None,
        },
        "notes": "",
    }


def _empty_store() -> dict[str, Any]:
    return {
        "version": 2,
        "active_key": "",
        "scopes": {},
        "updated_at": 0,
    }


def load_raw() -> dict[str, Any]:
    try:
        if not CONFIG_PATH.exists():
            return _empty_store()
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _empty_store()
        return data
    except Exception as exc:
        logger.warning("[FB_PRO_TASKS] load failed: %s", exc)
        return _empty_store()


def save_store(store: dict[str, Any]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    store = dict(store)
    store["updated_at"] = int(time.time())
    store["version"] = 2
    CONFIG_PATH.write_text(
        json.dumps(store, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _migrate_v1_if_needed(store: dict[str, Any], db: Session) -> dict[str, Any]:
    """Promote flat v1 JSON into scopes[key] for the first facebook account/page."""
    if store.get("version") == 2 and isinstance(store.get("scopes"), dict):
        return store
    # Flat v1: has week_start/targets at top level
    if "week_start" not in store and "scopes" in store:
        store["version"] = 2
        store.setdefault("scopes", {})
        store.setdefault("active_key", "")
        return store

    options = list_scope_options(db)
    key = options[0]["key"] if options else "global"
    body = default_scope_body()
    if store.get("week_start"):
        body["week_start"] = store["week_start"]
    if store.get("week_end"):
        body["week_end"] = store["week_end"]
    if isinstance(store.get("targets"), dict):
        body["targets"] = {
            "posts": int(store["targets"].get("posts") or DEFAULT_TARGETS["posts"]),
            "reels": int(store["targets"].get("reels") or DEFAULT_TARGETS["reels"]),
            "interactions": int(
                store["targets"].get("interactions") or DEFAULT_TARGETS["interactions"]
            ),
        }
    if isinstance(store.get("manual"), dict):
        m = store["manual"]
        body["manual"] = {
            "interactions": int(m.get("interactions") or 0),
            "posts_override": m.get("posts_override"),
            "reels_override": m.get("reels_override"),
        }
    if store.get("notes"):
        body["notes"] = str(store.get("notes") or "")

    if options:
        body["account_id"] = options[0].get("account_id")
        body["target_page"] = options[0].get("target_page")
        body["label"] = options[0].get("label")

    migrated = _empty_store()
    migrated["scopes"][key] = body
    migrated["active_key"] = key
    save_store(migrated)
    return migrated


def list_scope_options(db: Session) -> list[dict[str, Any]]:
    """Facebook accounts × their target pages (unique)."""
    options: list[dict[str, Any]] = []
    seen: set[str] = set()
    accounts = (
        db.query(Account)
        .filter(Account.platform == "facebook")
        .order_by(Account.id.asc())
        .all()
    )
    for acc in accounts:
        pages = list(acc.target_pages_list or [])
        if not pages and acc.target_page:
            pages = [acc.target_page]
        if not pages:
            key = scope_key(acc.id, None)
            if key not in seen:
                seen.add(key)
                options.append(
                    {
                        "key": key,
                        "account_id": acc.id,
                        "account_name": acc.name or f"Account {acc.id}",
                        "target_page": "",
                        "label": acc.name or f"Account {acc.id}",
                    }
                )
            continue
        for page in pages:
            key = scope_key(acc.id, page)
            if key in seen:
                continue
            seen.add(key)
            slug = page_slug(page) or page
            options.append(
                {
                    "key": key,
                    "account_id": acc.id,
                    "account_name": acc.name or f"Account {acc.id}",
                    "target_page": page,
                    "label": f"{acc.name or acc.id} · {slug}",
                }
            )

    # Also surface distinct job target_pages not on account yet
    job_pages = (
        db.query(Job.target_page, Job.account_id)
        .filter(
            Job.platform == "facebook",
            Job.target_page.isnot(None),
            Job.target_page != "",
        )
        .distinct()
        .all()
    )
    for page, account_id in job_pages:
        key = scope_key(account_id, page)
        if key in seen:
            continue
        seen.add(key)
        acc_name = ""
        if account_id:
            acc = db.get(Account, account_id)
            acc_name = (acc.name if acc else "") or f"Account {account_id}"
        slug = page_slug(page) or page
        options.append(
            {
                "key": key,
                "account_id": account_id,
                "account_name": acc_name or "—",
                "target_page": page,
                "label": f"{acc_name or 'Job'} · {slug}",
            }
        )
    return options


def ensure_scope_week(body: dict[str, Any]) -> dict[str, Any]:
    """Reset scope week if missing/expired; normalize targets/manual."""
    body = dict(body)
    today = _today_local()
    start = _parse_iso(body.get("week_start"))
    end = _parse_iso(body.get("week_end"))
    if start is None or end is None or today > end:
        new_start, new_end = _sunday_week_bounds(today)
        body["week_start"] = new_start.isoformat()
        body["week_end"] = new_end.isoformat()
        body["manual"] = {
            "interactions": 0,
            "posts_override": None,
            "reels_override": None,
        }
    targets = body.get("targets") if isinstance(body.get("targets"), dict) else {}
    manual = body.get("manual") if isinstance(body.get("manual"), dict) else {}
    body["targets"] = {
        "posts": int(targets.get("posts") or DEFAULT_TARGETS["posts"]),
        "reels": int(targets.get("reels") or DEFAULT_TARGETS["reels"]),
        "interactions": int(
            targets.get("interactions") or DEFAULT_TARGETS["interactions"]
        ),
    }
    body["manual"] = {
        "interactions": int(manual.get("interactions") or 0),
        "posts_override": manual.get("posts_override"),
        "reels_override": manual.get("reels_override"),
    }
    if body.get("notes") is None:
        body["notes"] = ""
    return body


def get_or_create_scope(
    db: Session,
    *,
    account_id: int | None = None,
    target_page: str | None = None,
    key: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """
    Returns (store, scope_body, option_meta).
    Resolves active scope from key / account+page / store.active_key / first option.
    """
    store = _migrate_v1_if_needed(load_raw(), db)
    options = list_scope_options(db)
    by_key = {o["key"]: o for o in options}

    chosen: dict[str, Any] | None = None
    if key and key in by_key:
        chosen = by_key[key]
    elif account_id is not None or target_page:
        want = scope_key(account_id, target_page)
        chosen = by_key.get(want)
        if not chosen and options:
            # Fuzzy: match account and normalized page
            page_n = normalize_page_url(target_page)
            for o in options:
                if account_id and o.get("account_id") != account_id:
                    continue
                if page_n and normalize_page_url(o.get("target_page")) != page_n:
                    continue
                chosen = o
                break
    if not chosen and store.get("active_key") in by_key:
        chosen = by_key[store["active_key"]]
    if not chosen and options:
        chosen = options[0]
    if not chosen:
        chosen = {
            "key": "global",
            "account_id": None,
            "account_name": "—",
            "target_page": "",
            "label": "Global",
        }

    scopes = store.setdefault("scopes", {})
    body = scopes.get(chosen["key"])
    if not isinstance(body, dict):
        body = default_scope_body()
    body["account_id"] = chosen.get("account_id")
    body["target_page"] = chosen.get("target_page") or ""
    body["label"] = chosen.get("label") or chosen["key"]
    body = ensure_scope_week(body)
    scopes[chosen["key"]] = body
    store["active_key"] = chosen["key"]
    save_store(store)
    return store, body, chosen


def _is_reel_job(job: Job) -> bool:
    url = (job.post_url or "").lower()
    if "/reel/" in url or "reel/" in url:
        return True
    media = (job.media_path or "").lower()
    return media.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm"))


def _job_matches_scope(
    job: Job,
    *,
    account_id: int | None,
    target_page: str | None,
    account_pages: set[str],
) -> bool:
    if account_id is not None and job.account_id != account_id:
        return False
    page_n = normalize_page_url(target_page)
    if not page_n:
        return True
    job_page = normalize_page_url(job.target_page)
    if job_page and job_page == page_n:
        return True
    # Job without target_page: attribute to account default pages
    if not job_page and page_n in account_pages:
        return True
    return False


def count_jobs_in_week(
    db: Session,
    week_start: date,
    week_end: date,
    *,
    account_id: int | None = None,
    target_page: str | None = None,
) -> dict[str, int]:
    ts0 = _day_start_ts(week_start)
    ts1 = _day_end_exclusive_ts(week_end)
    q = db.query(Job).filter(
        Job.platform == "facebook",
        Job.status == JobStatus.DONE,
        Job.finished_at.isnot(None),
        Job.finished_at >= ts0,
        Job.finished_at < ts1,
    )
    if account_id is not None:
        q = q.filter(Job.account_id == account_id)
    rows = q.all()

    account_pages: set[str] = set()
    if account_id is not None:
        acc = db.get(Account, account_id)
        if acc:
            for p in acc.target_pages_list or []:
                n = normalize_page_url(p)
                if n:
                    account_pages.add(n)
            if acc.target_page:
                n = normalize_page_url(acc.target_page)
                if n:
                    account_pages.add(n)

    reels = 0
    posts = 0
    for job in rows:
        jt = (getattr(job, "job_type", None) or JobType.POST or "POST").upper()
        if jt != JobType.POST and jt != "POST":
            continue
        if not _job_matches_scope(
            job,
            account_id=account_id,
            target_page=target_page,
            account_pages=account_pages,
        ):
            continue
        if _is_reel_job(job):
            reels += 1
        else:
            posts += 1
    return {"reels": reels, "posts": posts}


def _override_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def list_queue_hints(
    db: Session,
    *,
    account_id: int | None = None,
    target_page: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    q = db.query(Job).filter(
        Job.platform == "facebook",
        Job.status.in_([JobStatus.PENDING, JobStatus.DRAFT]),
    )
    if account_id is not None:
        q = q.filter(Job.account_id == account_id)
    rows = q.order_by(Job.id.desc()).limit(40).all()

    account_pages: set[str] = set()
    if account_id is not None:
        acc = db.get(Account, account_id)
        if acc:
            for p in acc.target_pages_list or []:
                n = normalize_page_url(p)
                if n:
                    account_pages.add(n)

    out: list[dict[str, Any]] = []
    for job in rows:
        jt = (getattr(job, "job_type", None) or JobType.POST or "POST").upper()
        if jt == JobType.COMMENT or jt == "COMMENT":
            continue
        if not _job_matches_scope(
            job,
            account_id=account_id,
            target_page=target_page,
            account_pages=account_pages,
        ):
            continue
        path = job.resolved_media_path if job.media_path else ""
        if not path or not os.path.exists(path):
            continue
        out.append(
            {
                "id": job.id,
                "status": job.status,
                "target_page": job.target_page or "",
                "caption": (job.caption or "")[:80],
                "media_name": Path(path).name,
                "is_video": path.lower().endswith(
                    (".mp4", ".mov", ".avi", ".mkv", ".webm")
                ),
            }
        )
        if len(out) >= limit:
            break
    return out


def build_dashboard(
    db: Session,
    *,
    account_id: int | None = None,
    target_page: str | None = None,
    key: str | None = None,
) -> dict[str, Any]:
    store, cfg, option = get_or_create_scope(
        db, account_id=account_id, target_page=target_page, key=key
    )
    week_start = _parse_iso(cfg["week_start"]) or _today_local()
    week_end = _parse_iso(cfg["week_end"]) or week_start
    acc_id = option.get("account_id")
    page = option.get("target_page") or ""

    auto = count_jobs_in_week(
        db, week_start, week_end, account_id=acc_id, target_page=page or None
    )
    manual = cfg["manual"]
    targets = cfg["targets"]

    posts_ov = _override_int(manual.get("posts_override"))
    reels_ov = _override_int(manual.get("reels_override"))
    posts_current = posts_ov if posts_ov is not None else auto["posts"]
    reels_current = reels_ov if reels_ov is not None else auto["reels"]
    interactions_current = int(manual.get("interactions") or 0)

    tasks = [
        {
            "key": "posts",
            "label": "Tạo bài viết công khai mới",
            "current": posts_current,
            "target": int(targets["posts"]),
            "source": "manual" if posts_ov is not None else "auto",
            "auto": auto["posts"],
        },
        {
            "key": "reels",
            "label": "Tạo thước phim công khai mới",
            "current": reels_current,
            "target": int(targets["reels"]),
            "source": "manual" if reels_ov is not None else "auto",
            "auto": auto["reels"],
        },
        {
            "key": "interactions",
            "label": "Thu hút tương tác với bài viết",
            "current": interactions_current,
            "target": int(targets["interactions"]),
            "source": "manual",
            "auto": None,
        },
    ]

    done_units = 0
    total_units = 0
    for t in tasks:
        tgt = max(1, int(t["target"]))
        cur = min(int(t["current"]), tgt)
        done_units += cur
        total_units += tgt
        t["pct"] = int(round(100 * cur / tgt))
        t["remaining"] = max(0, tgt - int(t["current"]))

    overall_pct = int(round(100 * done_units / total_units)) if total_units else 0
    today = _today_local()
    days_left = max(0, (week_end - today).days)
    options = list_scope_options(db)

    return {
        "config": cfg,
        "scope_key": option["key"],
        "scope_label": option.get("label") or option["key"],
        "account_id": acc_id,
        "account_name": option.get("account_name") or "",
        "target_page": page,
        "page_slug": page_slug(page),
        "scope_options": options,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "week_label": f"{week_start.day}/{week_start.month} – {week_end.day}/{week_end.month}",
        "days_left": days_left,
        "overall_pct": overall_pct,
        "tasks": tasks,
        "auto": auto,
        "meta_url": META_DASHBOARD_URL,
        "queue_hints": list_queue_hints(
            db, account_id=acc_id, target_page=page or None
        ),
        "updated_at": store.get("updated_at") or 0,
    }


def update_from_form(payload: dict[str, Any], db: Session) -> dict[str, Any]:
    """
    Apply operator edits for a scope.

    Payload may include: scope_key / account_id / target_page, plus week/manual/targets.
    """
    key = (payload.get("scope_key") or "").strip() or None
    account_id = payload.get("account_id")
    if account_id is not None and str(account_id).strip() != "":
        try:
            account_id = int(account_id)
        except (TypeError, ValueError):
            account_id = None
    else:
        account_id = None
    target_page = (payload.get("target_page") or "").strip() or None

    store, cfg, option = get_or_create_scope(
        db, account_id=account_id, target_page=target_page, key=key
    )

    week_start = payload.get("week_start")
    week_end = payload.get("week_end")
    if week_start and _parse_iso(str(week_start)):
        cfg["week_start"] = _parse_iso(str(week_start)).isoformat()
    if week_end and _parse_iso(str(week_end)):
        cfg["week_end"] = _parse_iso(str(week_end)).isoformat()

    if payload.get("target_posts") is not None:
        cfg["targets"]["posts"] = max(1, int(payload["target_posts"]))
    if payload.get("target_reels") is not None:
        cfg["targets"]["reels"] = max(1, int(payload["target_reels"]))
    if payload.get("target_interactions") is not None:
        cfg["targets"]["interactions"] = max(1, int(payload["target_interactions"]))

    if payload.get("interactions") is not None:
        cfg["manual"]["interactions"] = max(0, int(payload["interactions"]))

    if payload.get("clear_overrides"):
        cfg["manual"]["posts_override"] = None
        cfg["manual"]["reels_override"] = None
    else:
        if "posts_override" in payload:
            raw = str(payload.get("posts_override") or "").strip()
            cfg["manual"]["posts_override"] = int(raw) if raw != "" else None
        if "reels_override" in payload:
            raw = str(payload.get("reels_override") or "").strip()
            cfg["manual"]["reels_override"] = int(raw) if raw != "" else None

    if "notes" in payload and payload.get("notes") is not None:
        cfg["notes"] = str(payload.get("notes") or "")[:2000]

    cfg = ensure_scope_week(cfg)
    store["scopes"][option["key"]] = cfg
    store["active_key"] = option["key"]
    save_store(store)
    return cfg


def reset_week_now(db: Session, *, key: str | None = None) -> dict[str, Any]:
    store, _cfg, option = get_or_create_scope(db, key=key)
    body = default_scope_body()
    body["account_id"] = option.get("account_id")
    body["target_page"] = option.get("target_page") or ""
    body["label"] = option.get("label") or option["key"]
    store["scopes"][option["key"]] = body
    store["active_key"] = option["key"]
    save_store(store)
    return body
