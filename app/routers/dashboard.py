from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi import Form
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.database.models import Job, Account, DiscoveredChannel
from app.services.worker import WorkerService
from app.services.account import get_discovery_keywords
import app.config as config

# Gắn FastAPI app state or custom dependencies later if needed.
# Note: we need access to templates in routers. We'll import them from a shared location.
from app.main_templates import templates

router = APIRouter()

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

