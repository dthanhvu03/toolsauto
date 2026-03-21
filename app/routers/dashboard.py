from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse, StreamingResponse
from fastapi import Form
from sqlalchemy.orm import Session
from sqlalchemy import func
import time
import os
from pathlib import Path
import re
import datetime
import asyncio
from app.database.core import get_db
from app.database.models import Job, Account, DiscoveredChannel
from app.services.worker import WorkerService
from app.services.account import get_discovery_keywords
import app.config as config
from app.services import settings as runtime_settings

# Gắn FastAPI app state or custom dependencies later if needed.
# Note: we need access to templates in routers. We'll import them from a shared location.
from app.main_templates import templates

router = APIRouter()


def _tail_file(path: str, lines: int = 200) -> str:
    """Efficient tail: read last N lines without loading entire file."""
    lines = max(50, min(2000, int(lines or 200)))
    p = Path(path)
    if not p.exists() or not p.is_file():
        return f"[missing] {path}\n"

    # Read from end in chunks until we have enough newlines.
    chunk_size = 8192
    data = b""
    try:
        with p.open("rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            while pos > 0 and data.count(b"\n") <= lines + 2:
                read_size = chunk_size if pos >= chunk_size else pos
                pos -= read_size
                f.seek(pos)
                data = f.read(read_size) + data
                if pos == 0:
                    break
    except Exception as e:
        return f"[error reading log] {e}\n"

    text = data.decode("utf-8", errors="replace")
    parts = text.splitlines()
    return "\n".join(parts[-lines:]) + ("\n" if not text.endswith("\n") else "")


_PM2_LOG_DIR = Path("/home/vu/.pm2/logs")
_PM2_LOG_MAP: dict[str, dict[str, str]] = {
    "AI_Generator": {"out": "AI-Generator-out.log", "error": "AI-Generator-error.log"},
    "FB_Publisher": {"out": "FB-Publisher-out.log", "error": "FB-Publisher-error.log"},
    "Maintenance": {"out": "Maintenance-out.log", "error": "Maintenance-error.log"},
    "Web_Dashboard": {"out": "Web-Dashboard-out.log", "error": "Web-Dashboard-error.log"},
}


_TS_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})"
)


def _parse_log_ts(line: str) -> float | None:
    """Parse common timestamp prefixes to epoch seconds for sorting."""
    m = _TS_PREFIX_RE.match(line or "")
    if not m:
        return None
    s = m.group("ts")
    try:
        # Support both "YYYY-MM-DD HH:MM:SS" and "YYYY-MM-DDTHH:MM:SS"
        dt = datetime.datetime.fromisoformat(s.replace(" ", "T"))
        return dt.timestamp()
    except Exception:
        return None


def _tail_all(kind: str, lines: int) -> str:
    """Tail across all whitelisted pm2 logs and return merged last N lines."""
    lines = max(50, min(2000, int(lines or 200)))
    kind = (kind or "out").strip()
    if kind not in ("out", "error"):
        kind = "out"

    merged: list[tuple[float | None, int, str]] = []
    for idx, proc in enumerate(_PM2_LOG_MAP.keys()):
        fname = _PM2_LOG_MAP[proc][kind]
        path = str(_PM2_LOG_DIR / fname)
        chunk = _tail_file(path, lines=lines)
        for raw_line in (chunk.splitlines() if chunk else []):
            line = f"[{proc}] {raw_line}"
            merged.append((_parse_log_ts(raw_line), idx, line))

    # Sort primarily by timestamp when present; keep stable per-proc ordering fallback.
    merged.sort(key=lambda t: (t[0] is None, t[0] or 0.0, t[1]))
    out_lines = [t[2] for t in merged[-lines:]]
    return "\n".join(out_lines) + ("\n" if out_lines else "")

def _extract_tiktok_competitors(account: Account) -> list[dict]:
    """Return list of {url, target_page} filtered to TikTok competitor urls for an account."""
    import json
    out: list[dict] = []
    raw = account.competitor_urls
    if not raw:
        return out
    try:
        data = json.loads(raw)
        if not isinstance(data, list):
            data = [{"url": str(data), "target_page": None}]
    except Exception:
        # legacy: comma-separated
        data = [{"url": u.strip(), "target_page": None} for u in str(raw).split(",") if u.strip()]

    for item in data:
        if isinstance(item, dict):
            url = str(item.get("url") or "").strip()
            tp = item.get("target_page") or None
        else:
            url = str(item).strip()
            tp = None
        if not url:
            continue
        if "tiktok.com/@" not in url.lower():
            continue
        out.append({"url": url, "target_page": tp})
    return out


def _normalize_page_url(url: str | None) -> str:
    if not url:
        return ""
    u = str(url).strip()
    if not u:
        return ""
    # strip trailing slash for stable matching
    return u.rstrip("/")


def _build_tiktok_links_context(request: Request, db: Session) -> dict:
    """Shared data loader for TikTok Links (legacy + SaaS wrapper)."""
    import math
    from app.database.models import ViralMaterial

    # Query params
    tab = (request.query_params.get("tab") or "viral").strip()
    q = (request.query_params.get("q") or "").strip().lower()
    status = (request.query_params.get("status") or "").strip().upper()
    try:
        min_views = int(request.query_params.get("min_views") or 0)
    except Exception:
        min_views = 0
    try:
        page = max(1, int(request.query_params.get("page") or 1))
    except Exception:
        page = 1
    try:
        per_page = int(request.query_params.get("per_page") or 200)
    except Exception:
        per_page = 200
    per_page = max(50, min(500, per_page))

    # Competitors (grouped server-side so UX is clean)
    accounts = db.query(Account).order_by(Account.name.asc()).all()
    competitor_groups: dict[str, dict[str, list[str]]] = {}
    competitor_total = 0

    # Page index: page_url -> {name, niches}
    page_index: dict[str, dict] = {}
    for acc in accounts:
        # managed_pages_list: [{"name","url"}, ...]
        try:
            for p in (acc.managed_pages_list or []):
                p_url = _normalize_page_url(p.get("url"))
                if not p_url:
                    continue
                entry = page_index.setdefault(p_url, {"name": None, "niches": set()})
                if not entry.get("name") and p.get("name"):
                    entry["name"] = p.get("name")
        except Exception:
            pass
        # page_niches_map: {page_url: [niche,...]}
        try:
            for p_url, niches in (acc.page_niches_map or {}).items():
                n_url = _normalize_page_url(p_url)
                if not n_url:
                    continue
                entry = page_index.setdefault(n_url, {"name": None, "niches": set()})
                for n in (niches or []):
                    if n and str(n).strip():
                        entry["niches"].add(str(n).strip())
        except Exception:
            pass

    for acc in accounts:
        links = _extract_tiktok_competitors(acc)
        for link in links:
            url = link["url"]
            tp_raw = link["target_page"] or "_unassigned"
            tp = _normalize_page_url(tp_raw) if tp_raw != "_unassigned" else "_unassigned"
            # allow search by page name/niches too
            tp_meta = page_index.get(tp, {}) if tp != "_unassigned" else {}
            tp_name = (tp_meta.get("name") or "")
            tp_niches = " ".join(sorted(tp_meta.get("niches") or []))
            if q and (q not in (acc.name or "").lower()) and (q not in (tp or "").lower()) and (q not in (url or "").lower()) and (q not in tp_name.lower()) and (q not in tp_niches.lower()):
                continue
            competitor_groups.setdefault(tp, {}).setdefault(acc.name, []).append(url)
            competitor_total += 1

    # Viral TikTok
    viral_query = db.query(ViralMaterial).filter(ViralMaterial.platform == "tiktok")
    if status:
        viral_query = viral_query.filter(ViralMaterial.status == status)
    if min_views > 0:
        viral_query = viral_query.filter(ViralMaterial.views >= min_views)
    if q:
        viral_query = viral_query.filter(ViralMaterial.url.ilike(f"%{q}%"))

    viral_total = viral_query.count()
    total_pages = max(1, int(math.ceil(viral_total / per_page))) if viral_total else 1
    if page > total_pages:
        page = total_pages
    viral_rows = (
        viral_query.order_by(ViralMaterial.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return {
        "request": request,
        "tab": tab,
        "q": q,
        "status": status,
        "min_views": min_views,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "competitor_total": competitor_total,
        "competitor_groups": competitor_groups,
        "viral_rows": viral_rows,
        "viral_total": viral_total,
        "page_index": {
            k: {"name": v.get("name"), "niches": sorted(list(v.get("niches") or []))}
            for k, v in page_index.items()
        },
    }


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """Render the main dashboard."""
    # Default: show active jobs (PENDING+RUNNING) with pagination
    query = db.query(Job).filter(Job.status.in_(["PENDING", "RUNNING"]))
    total = query.count()
    per_page = 20
    total_pages = max(1, (total + per_page - 1) // per_page)
    jobs = query.order_by(Job.schedule_ts.desc()).limit(per_page).all()
    accounts = db.query(Account).all()
    state = WorkerService.get_or_create_state(db)
    viral_min_views = (
        state.viral_min_views
        if (state and getattr(state, "viral_min_views", None) is not None)
        else getattr(config, "VIRAL_MIN_VIEWS", 10000)
    )
    viral_max_videos = (
        state.viral_max_videos_per_channel
        if (state and getattr(state, "viral_max_videos_per_channel", None) is not None)
        else getattr(config, "VIRAL_MAX_VIDEOS_PER_CHANNEL", 50)
    )
    if viral_max_videos is None or viral_max_videos <= 0:
        viral_max_videos = 50
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request, "jobs": jobs, "accounts": accounts, "state": state, "now": int(time.time()),
            "current_status": "active", "current_page": 1, "total_pages": total_pages, "total_jobs": total, "per_page": per_page,
            "viral_min_views": viral_min_views,
            "viral_max_videos": viral_max_videos,
        }
    )

@router.get("/app", response_class=HTMLResponse)
def app_overview(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): overview page (no long tables)."""
    return templates.TemplateResponse("pages/app_overview.html", {"request": request})


@router.get("/app/overview/page-posting-stats", response_class=HTMLResponse)
def app_overview_page_posting_stats(request: Request, db: Session = Depends(get_db)):
    """
    HTMX fragment: show today's per-page posting usage (DONE) + remaining vs cap.
    Cap is runtime setting POSTS_PER_PAGE_PER_DAY (0 = disabled).
    """
    try:
        cap = int(runtime_settings.get_effective(db, "POSTS_PER_PAGE_PER_DAY") or 0)
    except Exception:
        cap = int(getattr(config, "POSTS_PER_PAGE_PER_DAY", 0) or 0)

    tz = getattr(config, "TIMEZONE", "Asia/Ho_Chi_Minh")
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_dt = datetime.datetime.now(ZoneInfo(tz))
    except Exception:
        pass
    today_start = int(datetime.datetime.combine(now_dt.date(), datetime.time.min, tzinfo=getattr(now_dt, "tzinfo", None)).timestamp())

    rows = (
        db.query(Job.target_page, func.count(Job.id))
        .filter(Job.target_page.isnot(None), Job.status == "DONE", Job.finished_at >= today_start)
        .group_by(Job.target_page)
        .order_by(func.count(Job.id).desc())
        .limit(50)
        .all()
    )

    stats = []
    for page_url, done_cnt in rows:
        used = int(done_cnt or 0)
        remaining = None
        if cap > 0:
            remaining = max(0, cap - used)
        stats.append(
            {
                "page_url": page_url,
                "used": used,
                "cap": cap,
                "remaining": remaining,
            }
        )

    return templates.TemplateResponse(
        "fragments/page_posting_stats.html",
        {
            "request": request,
            "today_start": today_start,
            "cap": cap,
            "stats": stats,
        },
    )


@router.get("/app/overview/page-reup-stats", response_class=HTMLResponse)
def app_overview_page_reup_stats(request: Request, db: Session = Depends(get_db)):
    """
    HTMX fragment: show today's per-page REUP intake usage + remaining vs cap.
    We treat a job as "REUP" if its media_path/processed_media_path is under config.REUP_DIR.
    Cap is runtime setting REUP_VIDEOS_PER_PAGE_PER_DAY (0 = disabled).
    """
    try:
        cap = int(runtime_settings.get_effective(db, "REUP_VIDEOS_PER_PAGE_PER_DAY") or 0)
    except Exception:
        cap = int(getattr(config, "REUP_VIDEOS_PER_PAGE_PER_DAY", 0) or 0)

    tz = getattr(config, "TIMEZONE", "Asia/Ho_Chi_Minh")
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        now_dt = datetime.datetime.now(ZoneInfo(tz))
    except Exception:
        pass
    today_start = int(datetime.datetime.combine(now_dt.date(), datetime.time.min, tzinfo=getattr(now_dt, "tzinfo", None)).timestamp())

    reup_dir = str(getattr(config, "REUP_DIR", "/home/vu/toolsauto/content/reup")).rstrip("/")
    like_reup = f"{reup_dir}/%"
    active_statuses = ["AWAITING_STYLE", "AI_PROCESSING", "DRAFT", "PENDING", "RUNNING"]

    # Build page url -> name index from accounts.managed_pages_list
    page_name_index: dict[str, str] = {}
    try:
        accounts = db.query(Account).all()
        for acc in accounts:
            for p in (acc.managed_pages_list or []):
                p_url = _normalize_page_url(p.get("url"))
                if not p_url:
                    continue
                if p.get("name") and p_url not in page_name_index:
                    page_name_index[p_url] = str(p.get("name"))
    except Exception:
        page_name_index = {}

    # Active REUP jobs created today
    rows_active = (
        db.query(Job.target_page, func.count(Job.id))
        .filter(
            Job.target_page.isnot(None),
            Job.status.in_(active_statuses),
            Job.created_at >= today_start,
            (
                Job.media_path.ilike(like_reup)
                | Job.processed_media_path.ilike(like_reup)
            ),
        )
        .group_by(Job.target_page)
        .all()
    )
    active_map = {str(tp): int(cnt or 0) for tp, cnt in rows_active if tp}

    # DONE REUP jobs finished today
    rows_done = (
        db.query(Job.target_page, func.count(Job.id))
        .filter(
            Job.target_page.isnot(None),
            Job.status == "DONE",
            Job.finished_at >= today_start,
            (
                Job.media_path.ilike(like_reup)
                | Job.processed_media_path.ilike(like_reup)
            ),
        )
        .group_by(Job.target_page)
        .all()
    )
    done_map = {str(tp): int(cnt or 0) for tp, cnt in rows_done if tp}

    pages = sorted(
        {*(active_map.keys()), *(done_map.keys())},
        key=lambda p: (-(active_map.get(p, 0) + done_map.get(p, 0)), p),
    )

    stats = []
    for page_url in pages[:50]:
        norm = _normalize_page_url(page_url)
        used = int(active_map.get(page_url, 0) + done_map.get(page_url, 0))
        remaining = None
        if cap > 0:
            remaining = max(0, cap - used)
        stats.append(
            {
                "page_url": page_url,
                "page_name": page_name_index.get(norm) or "",
                "used": used,
                "cap": cap,
                "remaining": remaining,
                "active": int(active_map.get(page_url, 0)),
                "done": int(done_map.get(page_url, 0)),
            }
        )

    return templates.TemplateResponse(
        "fragments/page_reup_stats.html",
        {
            "request": request,
            "today_start": today_start,
            "cap": cap,
            "stats": stats,
        },
    )

@router.get("/app/jobs", response_class=HTMLResponse)
def app_jobs(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): Jobs page wrapper (uses existing /jobs/table fragment)."""
    return templates.TemplateResponse("pages/app_jobs.html", {"request": request})

@router.get("/app/viral", response_class=HTMLResponse)
def app_viral(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): Viral page wrapper."""
    return templates.TemplateResponse("pages/app_viral.html", {"request": request})

@router.get("/app/accounts", response_class=HTMLResponse)
def app_accounts(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): Accounts page wrapper (reuses /accounts/table)."""
    return templates.TemplateResponse("pages/app_accounts.html", {"request": request})


@router.get("/app/logs", response_class=HTMLResponse)
def app_logs(request: Request):
    """SaaS UI: log viewer (PM2 logs)."""
    return templates.TemplateResponse(
        "pages/app_logs.html",
        {
            "request": request,
            "default_proc": request.query_params.get("proc") or "AI_Generator",
            "default_kind": request.query_params.get("kind") or "out",
            "default_lines": int(request.query_params.get("lines") or 200),
            "procs": ["ALL", *list(_PM2_LOG_MAP.keys())],
        },
    )


@router.get("/app/logs/tail", response_class=PlainTextResponse)
def app_logs_tail(proc: str = "AI_Generator", kind: str = "out", lines: int = 200):
    """Return last N lines for whitelisted pm2 log files."""
    proc = (proc or "").strip()
    kind = (kind or "").strip()
    if proc == "ALL":
        return PlainTextResponse(_tail_all(kind=kind, lines=lines))
    if proc not in _PM2_LOG_MAP:
        return PlainTextResponse(f"[invalid proc] {proc}\n", status_code=400)
    if kind not in ("out", "error"):
        return PlainTextResponse(f"[invalid kind] {kind}\n", status_code=400)
    fname = _PM2_LOG_MAP[proc][kind]
    path = str(_PM2_LOG_DIR / fname)
    return PlainTextResponse(_tail_file(path, lines=lines))


def _read_new_lines(path: Path, pos: int) -> tuple[int, list[str]]:
    """Read newly appended lines from `pos` (non-blocking)."""
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            if pos > end:
                # log rotated/truncated
                pos = 0
            if pos == end:
                return pos, []
            f.seek(pos)
            chunk = f.read()
            pos = f.tell()
    except FileNotFoundError:
        return pos, []
    lines = chunk.splitlines() if chunk else []
    return pos, [ln.decode("utf-8", errors="replace") for ln in lines]


def _match_filters(line: str, level: str | None, q: str | None) -> bool:
    if not line:
        return True
    if level:
        lvl = level.strip().upper()
        if lvl in ("INFO", "WARN", "WARNING", "ERROR", "DEBUG"):
            # very lightweight check
            if lvl == "WARN":
                lvl = "WARNING"
            if lvl not in line.upper():
                return False
    if q:
        qq = q.strip().lower()
        if qq and (qq not in line.lower()):
            return False
    return True


@router.get("/app/logs/stream")
def app_logs_stream(
    proc: str = "AI_Generator",
    kind: str = "out",
    level: str = "",
    q: str = "",
):
    """
    Server-Sent Events stream for realtime logs.
    Query:
      - proc: AI_Generator|FB_Publisher|Maintenance|Web_Dashboard|ALL
      - kind: out|error
      - level: INFO|WARN|ERROR|DEBUG (optional)
      - q: keyword contains filter (optional)
    """
    proc = (proc or "").strip()
    kind = (kind or "").strip()
    level = (level or "").strip()
    q = (q or "").strip()
    if kind not in ("out", "error"):
        kind = "out"
    if proc != "ALL" and proc not in _PM2_LOG_MAP:
        return PlainTextResponse(f"[invalid proc] {proc}\n", status_code=400)

    async def gen():
        # comment to establish stream quickly
        yield ": stream-start\n\n"

        if proc == "ALL":
            states: list[tuple[str, Path, int]] = []
            for p in _PM2_LOG_MAP.keys():
                fname = _PM2_LOG_MAP[p][kind]
                path = _PM2_LOG_DIR / fname
                try:
                    start_pos = path.stat().st_size
                except Exception:
                    start_pos = 0
                states.append((p, path, start_pos))
            while True:
                sent = 0
                new_states: list[tuple[str, Path, int]] = []
                for p, path, pos in states:
                    pos2, lines = _read_new_lines(path, pos)
                    new_states.append((p, path, pos2))
                    for line in lines:
                        out = f"[{p}] {line}"
                        if _match_filters(out, level, q):
                            yield f"data: {out.replace(chr(10),' ')}\n\n"
                            sent += 1
                states = new_states
                if sent == 0:
                    await asyncio.sleep(0.3)
        else:
            fname = _PM2_LOG_MAP[proc][kind]
            path = _PM2_LOG_DIR / fname
            try:
                pos = path.stat().st_size
            except Exception:
                pos = 0
            while True:
                pos, lines = _read_new_lines(path, pos)
                sent = 0
                for line in lines:
                    if _match_filters(line, level, q):
                        yield f"data: {line.replace(chr(10),' ')}\n\n"
                        sent += 1
                if sent == 0:
                    await asyncio.sleep(0.3)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/app/settings", response_class=HTMLResponse)
def app_settings(request: Request, db: Session = Depends(get_db)):
    grouped = runtime_settings.list_specs_by_section()
    overrides = runtime_settings.get_overrides(db, use_cache=False)
    effective: dict[str, dict] = {}
    for key, spec in runtime_settings.SETTINGS.items():
        default_val = spec.default_getter()
        ov = overrides.get(key, None)
        effective[key] = {
            "key": key,
            "type": spec.type,
            "title": spec.title,
            "section": spec.section,
            "default": default_val,
            "override": ov,
            "has_override": key in overrides,
            "min": spec.min,
            "max": spec.max,
            "choices": spec.choices or [],
        }
    return templates.TemplateResponse(
        "pages/app_settings.html",
        {
            "request": request,
            "sections": grouped,
            "effective": effective,
            "message": request.query_params.get("m") or "",
        },
    )


@router.post("/app/settings/save", response_class=RedirectResponse)
def app_settings_save(
    request: Request,
    db: Session = Depends(get_db),
    key: str = Form(...),
    value: str = Form(""),
):
    # updated_by: best-effort; no auth system yet
    updated_by = request.client.host if request.client else None
    runtime_settings.upsert_setting(db, key=key, raw_value=value, updated_by=updated_by)
    return RedirectResponse(url="/app/settings?m=saved", status_code=303)


@router.post("/app/settings/reset", response_class=RedirectResponse)
def app_settings_reset(
    request: Request,
    db: Session = Depends(get_db),
    key: str = Form(...),
):
    updated_by = request.client.host if request.client else None
    runtime_settings.reset_setting(db, key=key, updated_by=updated_by)
    return RedirectResponse(url="/app/settings?m=reset", status_code=303)


@router.post("/app/settings/bulk-save", response_class=RedirectResponse)
async def app_settings_bulk_save(request: Request, db: Session = Depends(get_db)):
    """
    Bulk save settings from a single form submission.
    Rule:
    - If submitted value == default => remove override (reset) if exists; else no-op.
    - Else => upsert override.
    """
    form = await request.form()
    updated_by = request.client.host if request.client else None

    overrides = runtime_settings.get_overrides(db, use_cache=False)
    changed = 0
    reset = 0

    for key in runtime_settings.SETTINGS.keys():
        if key not in form:
            continue
        raw = form.get(key)
        try:
            v = runtime_settings.normalize_for_compare(key, raw)
            d = runtime_settings.default_value(key)
        except Exception:
            continue

        if v == d:
            if key in overrides:
                runtime_settings.reset_setting(db, key=key, updated_by=updated_by)
                reset += 1
            continue

        runtime_settings.upsert_setting(db, key=key, raw_value=str(raw), updated_by=updated_by)
        changed += 1

    return RedirectResponse(url=f"/app/settings?m=bulk_saved_{changed}_reset_{reset}", status_code=303)

@router.get("/app/viral/table", response_class=HTMLResponse)
def app_viral_table(
    request: Request,
    page: int = 1,
    per_page: int = 100,
    q: str = "",
    status: str = "",
    platform: str = "",
    min_views: int = 0,
    db: Session = Depends(get_db),
):
    """SaaS UI: paginated viral table with filters (does not change ingestion logic)."""
    import math
    from app.database.models import ViralMaterial, Account

    per_page = max(50, min(200, int(per_page or 100)))
    page = max(1, int(page or 1))
    q = (q or "").strip()
    status = (status or "").strip()
    platform = (platform or "").strip()
    min_views = int(min_views or 0)

    query = db.query(ViralMaterial)
    if platform:
        query = query.filter(ViralMaterial.platform == platform)
    if status:
        query = query.filter(ViralMaterial.status == status)
    if min_views > 0:
        query = query.filter(ViralMaterial.views >= min_views)
    if q:
        query = query.filter(ViralMaterial.url.ilike(f"%{q}%"))

    total = query.count()
    total_pages = max(1, int(math.ceil(total / per_page))) if total else 1
    page = min(page, total_pages)

    items = (
        query.order_by(ViralMaterial.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    accounts = {acc.id: acc.name for acc in db.query(Account).all()}
    # render uses viral_row.html expecting item + account_name
    return templates.TemplateResponse(
        "fragments/app_viral_table.html",
        {
            "request": request,
            "items": [{"item": it, "account_name": accounts.get(it.scraped_by_account_id, "Unknown")} for it in items],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
    )

@router.get("/queue/panel", response_class=HTMLResponse)
def queue_panel(request: Request, db: Session = Depends(get_db)):
    """Small dashboard panel: queue/backlog summary by status + viral NEW/FAILED."""
    from sqlalchemy import text
    from app.database.models import ViralMaterial

    rows = db.execute(text("SELECT status, COUNT(*) FROM jobs GROUP BY status")).fetchall()
    counts = {str(s): int(c) for s, c in rows}
    viral_new = db.query(ViralMaterial).filter(ViralMaterial.status == "NEW").count()
    viral_failed = db.query(ViralMaterial).filter(ViralMaterial.status == "FAILED").count()

    return templates.TemplateResponse(
        "fragments/queue_panel.html",
        {
            "request": request,
            "counts": counts,
            "viral_new": viral_new,
            "viral_failed": viral_failed,
        },
    )

@router.get("/tiktok-links", response_class=HTMLResponse)
def tiktok_links(request: Request, db: Session = Depends(get_db)):
    """UI riêng để theo dõi link TikTok (kênh đối thủ + video viral TikTok)."""
    return templates.TemplateResponse("pages/tiktok_links.html", _build_tiktok_links_context(request, db))


@router.get("/app/tiktok-links", response_class=HTMLResponse)
def app_tiktok_links(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): TikTok Links page (keeps /tiktok-links legacy)."""
    return templates.TemplateResponse("pages/app_tiktok_links.html", _build_tiktok_links_context(request, db))

@router.get("/r/{code}")
def redirect_tracking(code: str, db: Session = Depends(get_db)):
    """Redirect tracking link and increment click counter."""
    job = db.query(Job).filter(Job.tracking_code == code).first()
    if not job or not job.affiliate_url:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tracking link not found or no affiliate URL set.")
    job.click_count = (job.click_count or 0) + 1
    db.commit()
    return RedirectResponse(job.affiliate_url, status_code=302)

@router.get("/discovery/panel", response_class=HTMLResponse)
def get_discovery_panel(request: Request, db: Session = Depends(get_db)):
    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/{channel_id}/approve", response_class=HTMLResponse)
def approve_discovered_channel(channel_id: int, request: Request, target_page: str = Form(""), db: Session = Depends(get_db)):
    channel = db.query(DiscoveredChannel).filter(DiscoveredChannel.id == channel_id).first()
    if channel and channel.status == "NEW":
        channel.status = "APPROVED"
        account = channel.account
        if account:
            import json as _json
            urls = []
            if account.competitor_urls:
                try:
                    data = _json.loads(account.competitor_urls)
                    if isinstance(data, list):
                        urls = data
                except Exception:
                    pass
            exists = any(u.get("url") == channel.channel_url for u in urls if isinstance(u, dict))
            if not exists:
                urls.append({"url": channel.channel_url, "target_page": target_page if target_page else None})
                account.competitor_urls = _json.dumps(urls, ensure_ascii=False)
        db.commit()
    
    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/{channel_id}/reject", response_class=HTMLResponse)
def reject_discovered_channel(channel_id: int, request: Request, db: Session = Depends(get_db)):
    channel = db.query(DiscoveredChannel).filter(DiscoveredChannel.id == channel_id).first()
    if channel and channel.status == "NEW":
        channel.status = "REJECTED"
        db.commit()
    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/force-scan", response_class=HTMLResponse)
def force_discovery_scan(request: Request, db: Session = Depends(get_db)):
    """Manually trigger competitor discovery scan for all active accounts (bypasses 2-5AM schedule).
    Uses per-page niches when set, else account-level niche_topics."""
    import random
    import logging
    logger = logging.getLogger(__name__)

    from app.services.discovery_scraper import DiscoveryScraper

    accounts = db.query(Account).filter(Account.is_active == True).all()

    scraper = DiscoveryScraper()
    total_found = 0
    scan_log = []

    for acc in accounts:
        keywords = get_discovery_keywords(acc)
        if not keywords:
            continue

        selected = random.sample(keywords, min(2, len(keywords)))
        for kw in selected:
            try:
                found = scraper.discover_for_keyword(kw, acc.id, db)
                total_found += found
                scan_log.append(f"✅ '{acc.name}' / kw='{kw}': {found} kênh mới")
            except Exception as e:
                scan_log.append(f"❌ '{acc.name}' / kw='{kw}': lỗi {str(e)[:80]}")

    logger.info("[DISCOVERY] Force scan complete. %d new channels found.", total_found)

    channels = db.query(DiscoveredChannel).filter(DiscoveredChannel.status == "NEW").order_by(DiscoveredChannel.score.desc()).all()
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels, "scan_log": scan_log, "total_found": total_found}
    )

