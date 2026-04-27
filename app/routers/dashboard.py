from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from sqlalchemy.orm import Session
import time
from app.database.core import get_db
from app.services.account import AccountService
from app.services.log_query_facade import LogQueryFacade
from app.services.dashboard_service import DashboardService
from app.utils.htmx import htmx_toast_response
from app.main_templates import templates


router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)):
    """SaaS Beta (single UI): same as /app — legacy dashboard.html is retired."""
    return app_overview(request, db)

@router.get("/app", response_class=HTMLResponse)
def app_overview(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): overview page (no long tables)."""
    overview = DashboardService.get_overview_data(db)
    return templates.TemplateResponse(
        "pages/app_overview.html",
        {
            "request": request,
            **overview,
            "now": int(time.time()),
        }
    )


@router.get("/app/dashboard", response_class=HTMLResponse)
def app_overview_legacy(request: Request, db: Session = Depends(get_db)):
    """Backward-compatible alias for legacy dashboard path."""
    return app_overview(request, db)


@router.get("/app/overview/page-posting-stats", response_class=HTMLResponse)
def app_overview_page_posting_stats(request: Request, db: Session = Depends(get_db)):
    """HTMX fragment: show today's per-page posting usage (DONE) + remaining vs cap."""
    stats_data = DashboardService.get_page_posting_stats(db)
    return templates.TemplateResponse(
        "fragments/page_posting_stats.html",
        {"request": request, **stats_data},
    )


@router.get("/app/overview/page-reup-stats", response_class=HTMLResponse)
def app_overview_page_reup_stats(request: Request, db: Session = Depends(get_db)):
    """HTMX fragment: show today's per-page REUP intake usage + remaining vs cap."""
    stats_data = DashboardService.get_page_reup_stats(db)
    return templates.TemplateResponse(
        "fragments/page_reup_stats.html",
        {"request": request, **stats_data},
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


@router.get("/app/pages")
def app_pages(request: Request):
    """Legacy UI redirect: Target Pages CRUD moved to /app/accounts split view."""
    return RedirectResponse(url="/app/accounts")


@router.get("/app/logs", response_class=HTMLResponse)
def app_logs(request: Request):
    """SaaS UI: unified domain events log viewer."""
    return templates.TemplateResponse(
        "pages/app_logs.html",
        {"request": request},
    )


@router.get("/app/logs/tail")
def app_logs_tail(proc: str = "ai-worker", kind: str = "out", lines: int = 200, category: str = "user"):
    """Return last N lines for whitelisted pm2 log files."""
    return LogQueryFacade.get_system_tail(proc, kind, lines, category=category)


@router.get("/app/logs/stream")
def app_logs_stream(
    proc: str = "ai-worker",
    kind: str = "out",
    level: str = "",
    q: str = "",
    category: str = "user",
):
    """
    Server-Sent Events stream for realtime logs.
    Query:
      - proc: AI_Generator|FB_Publisher|Maintenance|Web_Dashboard|ALL
      - kind: out|error
      - level: INFO|WARN|ERROR|DEBUG (optional)
      - q: keyword contains filter (optional)
    """
    return LogQueryFacade.stream_system_logs(proc=proc, kind=kind, level=level, q=q, category=category)

@router.get("/app/logs/domain-events")
def app_logs_domain_events(
    request: Request,
    source: str = "",
    level: str = "",
    job_id: str = "",
    q: str = "",
    category: str = "user",
    page: int = 1,
    db: Session = Depends(get_db)
):
    """HTMX fragment returning normalized domain events from the database."""
    job_id_int = None
    if job_id and job_id.isdigit():
        job_id_int = int(job_id)

    category_norm = (category or "user").strip().lower()
    if category_norm not in {"user", "tech", "all"}:
        category_norm = "user"

    results, total, total_pages = LogQueryFacade.query_domain_events(
        db=db,
        source=source if source else None,
        level=level if level else None,
        job_id=job_id_int,
        q=q if q else None,
        page=page,
        per_page=50,
        category=category_norm,
    )

    return templates.TemplateResponse(
        "fragments/domain_events_table.html",
        {
            "request": request,
            "events": results,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "filters": {
                "source": source,
                "level": level,
                "job_id": job_id,
                "q": q,
                "category": category_norm,
            }
        }
    )




@router.get("/app/logs/ai-analytics", response_class=HTMLResponse)
def app_logs_ai_analytics(request: Request, db: Session = Depends(get_db)):
    """HTMX fragment: AI Analytics tab (Health Report card + Top Incidents table)."""
    groups = DashboardService.get_ai_analytics(db)
    return templates.TemplateResponse(
        "fragments/ai_analytics_tab.html",
        {"request": request, "groups": groups},
    )


@router.get("/app/logs/ai-report/live", response_class=HTMLResponse)
def app_logs_ai_report_live(request: Request, db: Session = Depends(get_db)):
    """HTMX fragment: generate a live AI health report from the last 24h of incidents."""
    import html as _html
    from datetime import datetime
    
    report_data = DashboardService.get_ai_report_data(db)
    groups = report_data["groups"]
    text = report_data["text"]
    meta = report_data["meta"]

    if not groups:
        return HTMLResponse(
            '<div class="text-sm text-gray-500 italic p-3">'
            'Không có incident nào trong 24h qua. Hệ thống đang ổn định.'
            '</div>'
        )

    if not (meta.get("ok", True) and text):
        reason = meta.get("fail_reason", "empty response")
        return HTMLResponse(
            f'<div class="text-sm text-red-600 p-3">'
            f'AI generation failed: {_html.escape(str(reason))}'
            f'</div>'
        )

    try:
        import markdown2
        body_html = markdown2.markdown(
            text, extras=["tables", "fenced-code-blocks", "break-on-newline"]
        )
    except Exception:
        body_html = "<pre class='whitespace-pre-wrap text-sm'>" + _html.escape(text) + "</pre>"

    fallback_banner = ""
    if meta.get("fallback_used"):
        primary = _html.escape(str(meta.get("primary_fail_reason") or "unknown"))
        fallback_banner = (
            '<div class="mb-3 px-3 py-2 rounded-md border border-yellow-300 bg-yellow-50 '
            'flex items-center gap-2 text-xs text-yellow-800">'
            '<span class="px-1.5 py-0.5 rounded bg-yellow-400 text-white font-bold uppercase '
            'tracking-wider text-[10px]">FALLBACK MODE</span>'
            f'<span>Báo cáo sinh từ <b>Native Gemini</b>; 9Router lỗi: <code>{primary}</code></span>'
            '</div>'
        )

    meta_line = (
        f'<div class="text-[10px] text-gray-400 mt-2">'
        f'groups_in_report={len(groups)} • provider={_html.escape(str(meta.get("provider") or "?"))}'
        f' • model={_html.escape(str(meta.get("model") or "?"))}'
        f' • fallback_used={bool(meta.get("fallback_used"))}'
        f' • generated_at={datetime.now().strftime("%Y-%m-%d %H:%M:%S")}'
        f'</div>'
    )
    return HTMLResponse(
        f'{fallback_banner}<div class="prose prose-sm max-w-none ai-report-body">{body_html}</div>{meta_line}'
    )


@router.post("/app/logs/incident/{signature}/ack", response_class=HTMLResponse)
def app_logs_incident_ack(
    signature: str, request: Request, db: Session = Depends(get_db)
):
    """Mark an incident group as acknowledged. Returns the updated row HTML for HTMX swap."""
    group = DashboardService.acknowledge_incident(db, signature)
    if not group:
        return HTMLResponse(
            '<tr><td colspan="7" class="px-3 py-2 text-xs text-red-600">'
            'Incident group not found (đã bị xoá?)'
            '</td></tr>',
            status_code=404,
        )

    return templates.TemplateResponse(
        "fragments/incident_group_row.html",
        {"request": request, "g": group},
    )


@router.get("/app/control-plane", response_class=HTMLResponse)
def app_control_plane(request: Request, db: Session = Depends(get_db)):
    """SaaS UI: Admin Control Plane Hub."""
    return templates.TemplateResponse(
        "pages/app_control_plane.html",
        {
            "request": request,
        }
    )


@router.get("/app/settings", response_class=HTMLResponse)
def app_settings(request: Request, db: Session = Depends(get_db)):
    ctx = DashboardService.get_settings_context(db, request.query_params)
    return templates.TemplateResponse(
        "pages/app_settings.html",
        {"request": request, **ctx},
    )


@router.post("/app/settings/save", response_class=HTMLResponse)
def app_settings_save(
    request: Request,
    db: Session = Depends(get_db),
    key: str = Form(...),
    value: str = Form(""),
):
    updated_by = request.client.host if request.client else None
    try:
        DashboardService.save_setting(db, key=key, value=value, updated_by=updated_by)
    except ValueError:
        return JSONResponse({"success": False, "error": "Không thể lưu: key hoặc giá trị không hợp lệ."}, status_code=400)
    
    import json as _json
    headers = {"HX-Trigger": _json.dumps({"showMessage": {"msg": "Đã lưu cài đặt thành công.", "type": "success"}})}
    return JSONResponse({"success": True}, headers=headers)


@router.post("/app/settings/reset", response_class=HTMLResponse)
def app_settings_reset(
    request: Request,
    db: Session = Depends(get_db),
    key: str = Form(...),
):
    updated_by = request.client.host if request.client else None
    try:
        DashboardService.reset_setting(db, key=key, updated_by=updated_by)
    except ValueError:
        return htmx_toast_response("Không thể đặt lại.", "error", refresh_page=False)
    return htmx_toast_response("Đã đặt lại về mặc định.", "success", refresh_page=False)


@router.post("/app/settings/bulk-save", response_class=HTMLResponse)
async def app_settings_bulk_save(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    updated_by = request.client.host if request.client else None
    results = DashboardService.bulk_save_settings(db, dict(form), updated_by)
    return htmx_toast_response(f"Đã lưu {results['changed']} thay đổi; đặt lại {results['reset']} mục về mặc định.", "success", refresh_page=False)

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
    table_data = DashboardService.get_viral_materials(
        db, page=page, per_page=per_page, q=q, status=status, platform=platform, min_views=min_views
    )
    return templates.TemplateResponse(
        "fragments/app_viral_table.html",
        {"request": request, **table_data},
    )

@router.get("/queue/panel", response_class=HTMLResponse)
def queue_panel(request: Request, db: Session = Depends(get_db)):
    """Small dashboard panel: queue/backlog summary by status + viral NEW/FAILED."""
    stats = DashboardService.get_queue_stats(db)
    return templates.TemplateResponse(
        "fragments/queue_panel.html",
        {"request": request, **stats},
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
    affiliate_url = DashboardService.track_redirect_click(db, code)
    if not affiliate_url:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Tracking link not found or no affiliate URL set.")
    return RedirectResponse(affiliate_url, status_code=302)

@router.get("/discovery/panel", response_class=HTMLResponse)
def get_discovery_panel(request: Request, db: Session = Depends(get_db)):
    channels = DashboardService.get_discovery_channels(db)
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/{channel_id}/approve", response_class=HTMLResponse)
def approve_discovered_channel(channel_id: int, request: Request, target_page: str = Form(""), db: Session = Depends(get_db)):
    channels = DashboardService.approve_discovery(db, channel_id, target_page)
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/{channel_id}/reject", response_class=HTMLResponse)
def reject_discovered_channel(channel_id: int, request: Request, db: Session = Depends(get_db)):
    channels = DashboardService.reject_discovery(db, channel_id)
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels}
    )

@router.post("/discovery/force-scan", response_class=HTMLResponse)
def force_discovery_scan(request: Request, db: Session = Depends(get_db)):
    """Manually trigger competitor discovery scan."""
    channels, scan_log, total_found = DashboardService.run_force_discovery(db)
    return templates.TemplateResponse(
        "fragments/discovery_panel.html",
        {"request": request, "channels": channels, "scan_log": scan_log, "total_found": total_found}
    )

@router.get("/app/overview/chart-data")
def app_overview_chart_data(db: Session = Depends(get_db)):
    """JSON endpoint for ApexCharts performance data."""
    return DashboardService.get_chart_data(db)
