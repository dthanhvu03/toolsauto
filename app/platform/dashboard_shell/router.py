from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from pathlib import Path
from sqlalchemy.orm import Session
from app.core.database.core import get_db
from app.core.observability.log_query_facade import LogQueryFacade
from app.platform.dashboard_service import DashboardService
from app.utils.htmx import htmx_toast_response
from app.main_templates import templates
import app.config as config


router = APIRouter()

_SPA_INDEX = config.BASE_DIR / "app" / "static" / "admin" / "index.html"
# Legacy path from Settings-only deploy
_SETTINGS_UI_INDEX = config.BASE_DIR / "app" / "static" / "settings-ui" / "index.html"


def _spa_index() -> Path | None:
    if _SPA_INDEX.is_file():
        return _SPA_INDEX
    if _SETTINGS_UI_INDEX.is_file():
        return _SETTINGS_UI_INDEX
    return None


def _serve_spa() -> FileResponse | None:
    idx = _spa_index()
    if not idx:
        return None
    return FileResponse(idx, media_type="text/html", headers={"Cache-Control": "no-cache"})


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    """Cùng trang với /app."""
    return app_overview(request)

@router.get("/app", response_class=HTMLResponse)
def app_overview(request: Request):
    """Giao diện duy nhất là SPA React (PLAN-108). Bản build nằm trong git — thiếu là deploy hỏng."""
    return _serve_spa() or _spa_missing()


def _spa_missing() -> HTMLResponse:
    return HTMLResponse(
        "<p>Giao diện chưa được build. Chạy <code>npm run build:admin</code> ở thư mục gốc.</p>",
        status_code=503,
    )


@router.get("/app/go/{rest:path}", response_class=HTMLResponse)
def app_spa_go(rest: str, request: Request):
    """React Router bridge pages — always serve SPA shell."""
    return _serve_spa() or _spa_missing()


@router.get("/app/dashboard", response_class=HTMLResponse)
def app_overview_legacy(request: Request):
    """Backward-compatible alias for legacy dashboard path."""
    return app_overview(request)


@router.get("/app/jobs", response_class=HTMLResponse)
def app_jobs(request: Request, db: Session = Depends(get_db), platform: str | None = None):
    """SaaS UI: Jobs page. ?platform=threads locks silo (hide cross-MXH chips)."""
    raw = (platform or request.query_params.get("platform") or "").strip().lower()
    allowed = {"facebook", "threads", "instagram", "tiktok"}
    locked = raw if raw in allowed else None
    labels = {
        "facebook": "Facebook",
        "threads": "Threads",
        "instagram": "Instagram",
        "tiktok": "TikTok",
    }
    return templates.TemplateResponse(
        "pages/app_jobs.html",
        {
            "request": request,
            "jobs_platform": locked or "all",
            "jobs_silo_locked": bool(locked),
            "jobs_platform_label": labels.get(locked or "", ""),
        },
    )

@router.get("/app/viral", response_class=HTMLResponse)
def app_viral(request: Request, db: Session = Depends(get_db)):
    """SaaS UI (beta): Viral page wrapper."""
    return templates.TemplateResponse("pages/app_viral.html", {"request": request})

@router.get("/app/viral/sources", response_class=HTMLResponse)
def app_viral_sources(request: Request):
    """SaaS UI: trang "Nguồn video" — kênh TikTok/YouTube tự quét (ADR-025).

    Trước đây là khối <details> gấp/mở trong /app/viral; tách ra trang riêng vì mục sidebar
    trỏ vào khối gấp thì trạng thái hiện/ẩn phụ thuộc localStorage từng máy.

    Chỉ dựng vỏ trang — KHÔNG nhận `db`: dữ liệu nguồn do fragment htmx `GET /viral/sources`
    (`app/features/viral_intake/router.py:list_sources`) nạp sau khi trang tải xong. Hai
    đường dẫn chỉ khác nhau tiền tố `/app`; sửa nhầm file là bẫy có thật.
    """
    return templates.TemplateResponse("pages/app_viral_sources.html", {"request": request})

@router.get("/app/logs", response_class=HTMLResponse)
def app_logs(request: Request):
    """SaaS UI: unified domain events log viewer."""
    return templates.TemplateResponse(
        "pages/app_logs.html",
        {"request": request},
    )


@router.get("/app/logs/tail")
def app_logs_tail(proc: str = "ALL", kind: str = "out", lines: int = 200, category: str = "user"):
    """Return last N lines for whitelisted pm2 log files."""
    return LogQueryFacade.get_system_tail(proc, kind, lines, category=category)


@router.get("/app/logs/stream")
def app_logs_stream(
    proc: str = "ALL",
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


@router.get("/app/settings", response_class=HTMLResponse)
def app_settings(request: Request, db: Session = Depends(get_db)):
    """React Settings (SPA) when built; else classic Jinja."""
    spa = _serve_spa()
    if spa is not None:
        return spa
    ctx = DashboardService.get_settings_context(db, request.query_params)
    return templates.TemplateResponse(
        "pages/app_settings.html",
        {
            "request": request,
            **ctx,
            "message": ctx.get("message")
            or "React admin chưa build. Chạy: npm run build:settings",
        },
    )


@router.get("/app/settings/classic", response_class=HTMLResponse)
def app_settings_classic(request: Request, db: Session = Depends(get_db)):
    """Legacy Jinja settings form (HTMX bulk-save)."""
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
