from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
import time
import datetime
from app.database.core import get_db
from app.database.models import Job, Account, DiscoveredChannel
from app.services.worker import WorkerService
from app.services.account import AccountService, get_discovery_keywords
from app.services.log_service import LogService
import app.config as config
from app.services import settings as runtime_settings

# Gắn FastAPI app state or custom dependencies later if needed.
# Note: we need access to templates in routers. We'll import them from a shared location.
from app.main_templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """SaaS Beta (single UI): same as /app — legacy dashboard.html is retired."""
    return app_overview(request, db)

@router.get("/app", response_class=HTMLResponse)
def app_overview(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): overview page (no long tables)."""
    accounts = db.query(Account).all()
    state = WorkerService.get_or_create_state(db)
    return templates.TemplateResponse(
        "pages/app_overview.html",
        {
            "request": request,
            "accounts": accounts,
            "state": state,
            "now": int(time.time()),
        }
    )


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

    reup_dir = str(config.REUP_DIR).rstrip("/")
    like_reup = f"{reup_dir}/%"
    active_statuses = ["AWAITING_STYLE", "AI_PROCESSING", "DRAFT", "PENDING", "RUNNING"]

    # Build page url -> name index from accounts.managed_pages_list
    page_name_index: dict[str, str] = {}
    try:
        accounts = db.query(Account).all()
        for acc in accounts:
            for p in (acc.managed_pages_list or []):
                p_url = AccountService.normalize_page_url(p.get("url"))
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
        norm = AccountService.normalize_page_url(page_url)
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
    """SaaS UI: Accounts page (Now using Split View by default)."""
    accounts = AccountService.list_accounts(db)
    first_account = accounts[0] if accounts else None
    return templates.TemplateResponse(
        "pages/app_accounts_split.html", 
        {"request": request, "accounts": accounts, "first_account": first_account, "now": int(time.time())}
    )


@router.get("/app/pages", response_class=HTMLResponse)
def app_pages(request: Request):
    """SaaS UI: Target Pages CRUD editor."""
    return templates.TemplateResponse("pages/app_pages.html", {"request": request})


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
            "procs": ["ALL", *list(LogService.PM2_LOG_MAP.keys())],
        },
    )


@router.get("/app/logs/tail")
def app_logs_tail(proc: str = "ai-worker", kind: str = "out", lines: int = 200):
    """Return last N lines for whitelisted pm2 log files."""
    return LogService.plain_tail_response(proc, kind, lines)


@router.get("/app/logs/stream")
def app_logs_stream(
    proc: str = "ai-worker",
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
    return LogService.sse_log_stream(proc=proc, kind=kind, level=level, q=q)


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
            "description": spec.description,
            "default": default_val,
            "override": ov,
            "has_override": key in overrides,
            "min": spec.min,
            "max": spec.max,
            "choices": spec.choices or [],
            "enum_labels": spec.enum_labels or {},
            "unit": spec.unit,
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
    ctx = AccountService.build_tiktok_links_context_data(db, request.query_params)
    return templates.TemplateResponse("pages/tiktok_links.html", {"request": request, **ctx})


@router.get("/app/tiktok-links", response_class=HTMLResponse)
def app_tiktok_links(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): TikTok Links page (keeps /tiktok-links legacy)."""
    ctx = AccountService.build_tiktok_links_context_data(db, request.query_params)
    return templates.TemplateResponse("pages/app_tiktok_links.html", {"request": request, **ctx})

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
            AccountService.append_competitor_url_if_missing(
                account,
                channel.channel_url,
                target_page if target_page else None,
            )
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

