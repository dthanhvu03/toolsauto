from typing import List, Optional, Tuple
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
import json
import time
import logging
from app.core.database.core import get_db
from app.core.account import AccountService
from app.core.page_utils import PageUtils
from app.main_templates import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/accounts", tags=["accounts"])


def _filter_accounts_list(accounts: List, q: str = "", platform: str = ""):
    q = (q or "").strip().lower()
    pf = (platform or "").strip().lower()
    if pf and pf != "all":
        accounts = [a for a in accounts if (getattr(a, "platform", "") or "").lower() == pf]
    if q:
        filtered = []
        for a in accounts:
            if q in (a.name or "").lower() or q in (a.platform or "").lower():
                filtered.append(a)
        accounts = filtered
    return accounts


def _platform_filter_label(platform: str) -> str:
    labels = {
        "facebook": "Facebook",
        "instagram": "Instagram",
        "threads": "Threads",
        "tiktok": "TikTok",
    }
    pf = (platform or "").strip().lower()
    if not pf or pf == "all":
        return ""
    return labels.get(pf, pf.capitalize())


def _render_accounts_list_html(request: Request, accounts: List, highlight_id: int | None = None, platform: str = "") -> str:
    now = int(time.time())
    if not accounts:
        label = _platform_filter_label(platform)
        if label:
            return (
                f'<div class="p-[var(--space-8)] text-center text-cave-xs text-[var(--color-ash)] leading-relaxed">'
                f'Không có tài khoản <strong class="text-[var(--color-mist)]">{label}</strong> trong hang.'
                f'<button type="button" class="block mx-auto mt-3 text-[var(--color-torch)] font-bold uppercase tracking-wider text-[10px]" '
                f'onclick="window.resetAccountPlatformFilter && window.resetAccountPlatformFilter()">Xem tất cả</button>'
                f"</div>"
            )
        return (
            '<div class="p-[var(--space-8)] text-center text-cave-xs text-[var(--color-ash)]">'
            "Chưa có hang nào — thêm profile ở cột trái."
            "</div>"
        )
    html_content = ""
    for account in accounts:
        html_content += templates.get_template("fragments/account_list_item.html").render(
            {
                "request": request,
                "account": account,
                "now": now,
                "highlight_id": highlight_id,
            }
        )
    return html_content


def _wants_account_details(request: Request, account_id: int) -> bool:
    """Split View HTMX targets #account-{id}; grid cards use account_row."""
    target = (request.headers.get("hx-target") or "").strip()
    if target == f"#account-{account_id}":
        return True
    current = request.headers.get("hx-current-url") or ""
    return "/app/accounts" in current


def _account_ui_response(
    request: Request,
    account,
    *,
    toast: Optional[Tuple[str, str]] = None,
    **extra,
) -> HTMLResponse:
    now = int(time.time())
    if account and account.login_error and not extra.get("cookie_import_error"):
        from app.core.observability.log_normalizer import LogNormalizer
        account.login_error = LogNormalizer._translate_message(account.login_error)
    ctx = {"request": request, "account": account, "now": now, **extra}
    headers = {}
    if toast:
        msg, toast_type = toast
        headers["HX-Trigger"] = json.dumps({"showMessage": {"msg": msg, "type": toast_type}})
    fragment = (
        "fragments/account_details.html"
        if account and _wants_account_details(request, account.id)
        else "fragments/account_row.html"
    )
    return templates.TemplateResponse(fragment, ctx, headers=headers)

def get_accounts_table(request: Request, q: str = "", db: Session = Depends(get_db)):
    accounts = AccountService.list_accounts(db)
    q = (q or "").strip().lower()
    if q:
        filtered = []
        for a in accounts:
            hay = " ".join([
                str(getattr(a, "name", "") or ""),
                str(getattr(a, "platform", "") or ""),
                str(getattr(a, "target_page", "") or ""),
                str(getattr(a, "target_pages", "") or ""),
                str(getattr(a, "niche_topics", "") or ""),
                str(getattr(a, "page_niches", "") or ""),
                str(getattr(a, "competitor_urls", "") or ""),
            ]).lower()
            if q in hay:
                filtered.append(a)
        accounts = filtered
    
    now = int(time.time())
    html_content = ""
    for account in accounts:
        if account.login_error:
            from app.core.observability.log_normalizer import LogNormalizer
            account.login_error = LogNormalizer._translate_message(account.login_error)
        html_content += templates.get_template("fragments/account_row.html").render(
            {"request": request, "account": account, "now": now}
        )
    return HTMLResponse(content=html_content)

@router.post("/create", response_class=HTMLResponse)
def create_account(
    request: Request,
    name: str = Form(...),
    platform: str = Form("facebook"),
    daily_limit: int = Form(3),
    cooldown_seconds: int = Form(1800),
    ui: str = Form("grid"),
    db: Session = Depends(get_db),
):
    created_id: int | None = None
    platform_norm = (platform or "facebook").strip().lower()
    if platform_norm not in ("facebook", "instagram"):
        platform_norm = "facebook"
    name_clean = (name or "").strip()
    if not name_clean:
        logger.warning("create_account rejected: empty name")
    else:
        try:
            new_acc = AccountService.create_account(
                db,
                platform=platform_norm,
                name=name_clean,
                daily_limit=daily_limit,
                cooldown_seconds=cooldown_seconds,
            )
            created_id = new_acc.id
        except Exception as e:
            logger.error("Failed to create account name=%s platform=%s: %s", name, platform, e)

    if (ui or "").strip().lower() == "split":
        accounts = AccountService.list_accounts(db)
        created_account = AccountService.get_account(db, created_id) if created_id else None
        return templates.TemplateResponse(
            "fragments/accounts_split_after_create.html",
            {
                "request": request,
                "accounts": accounts,
                "created_account": created_account,
                "highlight_id": created_id,
                "now": int(time.time()),
            },
        )

    accounts = AccountService.list_accounts(db)
    return templates.TemplateResponse(
        "fragments/accounts_table.html",
        {"request": request, "accounts": accounts, "now": int(time.time())},
    )

@router.post("/{account_id}/import-cookies", response_class=HTMLResponse)
def import_account_cookies(
    account_id: int,
    request: Request,
    cookies_json: str = Form(...),
    db: Session = Depends(get_db),
):
    cookie_import_ok = None
    cookie_import_error = None
    try:
        AccountService.import_cookies_from_json(db, account_id, cookies_json)
        cookie_import_ok = "Đã import cookie và cập nhật session."
    except ValueError as e:
        cookie_import_error = str(e)
    except Exception as e:
        logger.error("import_account_cookies account_id=%s: %s", account_id, e)
        cookie_import_error = f"Lỗi import: {e}"

    account = AccountService.get_account(db, account_id)
    if not account:
        return HTMLResponse(status_code=404)
    toast = None
    if cookie_import_ok:
        toast = (cookie_import_ok, "success")
    elif cookie_import_error:
        toast = (cookie_import_error, "error")
    return _account_ui_response(
        request,
        account,
        toast=toast,
        cookie_import_ok=cookie_import_ok,
        cookie_import_error=cookie_import_error,
    )


@router.post("/{account_id}/start-login", response_class=HTMLResponse)
def start_account_login(account_id: int, request: Request, db: Session = Depends(get_db)):
    error_msg = None
    try:
        account = AccountService.start_login(db, account_id)
    except ValueError as e:
        logger.warning(f"start_account_login blocked: {e}")
        account = AccountService.get_account(db, account_id)
        error_msg = str(e)
    except Exception as e:
        logger.error(f"start_account_login error: {e}")
        account = AccountService.get_account(db, account_id)
        error_msg = "Có lỗi hệ thống xảy ra"
        
    return _account_ui_response(request, account, start_login_error=error_msg)

@router.post("/{account_id}/confirm-login", response_class=HTMLResponse)
def confirm_account_login(account_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        account = AccountService.confirm_login(db, account_id)
    except Exception as e:
        logger.error(f"confirm_account_login error: {e}")
        account = AccountService.get_account(db, account_id)
        
    return _account_ui_response(request, account)

@router.post("/{account_id}/validate-session", response_class=HTMLResponse)
def validate_account_session(account_id: int, request: Request, db: Session = Depends(get_db)):
    toast = None
    try:
        account = AccountService.validate_session(db, account_id)
        if not account:
            return HTMLResponse(status_code=404)
        status = (account.login_status or "").upper()
        if status == "ACTIVE":
            toast = ("Session còn hợp lệ — ACTIVE.", "success")
        elif status == "INVALID":
            toast = (
                account.login_error or "Session hết hạn / chưa đăng nhập — cần import cookie hoặc đăng nhập lại.",
                "error",
            )
        elif account.login_error:
            toast = (account.login_error, "warning")
        else:
            toast = (f"Đã kiểm tra — trạng thái: {account.login_status or 'UNKNOWN'}.", "info")
    except Exception as e:
        logger.error("validate_account_session error: %s", e)
        account = AccountService.get_account(db, account_id)
        toast = (f"Kiểm tra session lỗi: {e}", "error")

    return _account_ui_response(request, account, toast=toast)

@router.post("/{account_id}/toggle", response_class=HTMLResponse)
def toggle_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        account = AccountService.toggle_account(db, account_id)
    except ValueError as e:
        logger.warning("toggle_account account_id=%s: %s", account_id, e)
        account = AccountService.get_account(db, account_id)
    except Exception as e:
        logger.error("toggle_account error: %s", e)
        account = AccountService.get_account(db, account_id)
        
    return _account_ui_response(request, account)

@router.post("/{account_id}/update-limits", response_class=HTMLResponse)
def update_account_limits(
    account_id: int, 
    request: Request, 
    daily_limit: int = Form(...),
    cooldown_seconds: int = Form(...),
    niche_topics: str = Form(""),
    sleep_start_time: str = Form(""),
    sleep_end_time: str = Form(""),
    competitor_urls: str = Form(""),
    target_pages: List[str] = Form(None),
    page_niches: str = Form(""),
    update_distribution: str = Form(""),
    db: Session = Depends(get_db)
):
    try:
        account = AccountService.update_limits(
            db, account_id, daily_limit, cooldown_seconds,
            niche_topics=niche_topics,
            sleep_start_time=sleep_start_time,
            sleep_end_time=sleep_end_time,
            competitor_urls=competitor_urls,
            target_pages=target_pages or [],
            page_niches=page_niches or "",
            update_distribution=(update_distribution or "").strip() in ("1", "true", "on", "yes"),
        )
    except Exception as e:
        logger.warning("update_limits account_id=%s: %s", account_id, e)
        account = AccountService.get_account(db, account_id)
        
    return _account_ui_response(request, account)

@router.post("/{account_id}/reset-failures", response_class=HTMLResponse)
def reset_account_failures(account_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        account = AccountService.reset_failures(db, account_id)
    except Exception as e:
        logger.warning("reset_failures account_id=%s: %s", account_id, e)
        account = AccountService.get_account(db, account_id)
        
    return _account_ui_response(request, account)

@router.post("/{account_id}/rename", response_class=HTMLResponse)
def rename_account(
    account_id: int, 
    request: Request, 
    name: str = Form(...), 
    db: Session = Depends(get_db)
):
    try:
        account = AccountService.rename_account(db, account_id, name)
    except Exception:
        account = AccountService.get_account(db, account_id)

    return _account_ui_response(request, account)

@router.post("/{account_id}/delete", response_class=HTMLResponse)
def delete_account(account_id: int, request: Request, db: Session = Depends(get_db)):
    try:
        AccountService.delete_account(db, account_id)
        return HTMLResponse("")
    except Exception:
        account = AccountService.get_account(db, account_id)
        return _account_ui_response(request, account)

@router.get("/", response_class=HTMLResponse)
def get_accounts_page(request: Request, db: Session = Depends(get_db)):
    accounts = AccountService.list_accounts(db)
    first_account = accounts[0] if accounts else None
    return templates.TemplateResponse(
        "pages/app_accounts_split.html", 
        {"request": request, "accounts": accounts, "first_account": first_account, "now": int(time.time())}
    )

@router.get("/split", response_class=HTMLResponse)
def get_accounts_split_view_alias(request: Request, db: Session = Depends(get_db)):
    return get_accounts_page(request, db)

@router.get("/list", response_class=HTMLResponse)
def get_accounts_list(request: Request, q: str = "", platform: str = "", db: Session = Depends(get_db)):
    accounts = AccountService.list_accounts(db)
    accounts = _filter_accounts_list(accounts, q=q, platform=platform)
    return HTMLResponse(content=_render_accounts_list_html(request, accounts, platform=platform))

@router.get("/{account_id}/details", response_class=HTMLResponse)
def get_account_details_view(account_id: int, request: Request, db: Session = Depends(get_db)):
    account = AccountService.get_account(db, account_id)
    if not account:
        return HTMLResponse(status_code=404)
    if account.login_error:
        from app.core.observability.log_normalizer import LogNormalizer
        account.login_error = LogNormalizer._translate_message(account.login_error)
    return templates.TemplateResponse(
        "fragments/account_details.html", 
        {"request": request, "account": account, "now": int(time.time())}
    )

@router.get("/{account_id}/pages-tab", response_class=HTMLResponse)
def get_account_pages_tab(
    account_id: int, 
    request: Request, 
    q: str = "", 
    filter: str = "all", 
    db: Session = Depends(get_db)
):
    account = AccountService.get_account(db, account_id)
    if not account:
        return HTMLResponse(status_code=404)
        
    pages_list = PageUtils.build_page_view_models(account, q=q, filter_str=filter)
    managed_n = len(account.managed_pages_list or [])
    on_n = len(account.target_pages_list or [])
    
    return templates.TemplateResponse(
        "fragments/account_pages_tab.html", 
        {
            "request": request,
            "account": account,
            "pages": pages_list,
            "now": int(time.time()),
            "is_account_scoped": True,
            "filter": filter or "all",
            "q": q or "",
            "on_count": on_n,
            "managed_count": managed_n,
        }
    )


@router.post("/{account_id}/apply-global-niches", response_class=HTMLResponse)
def apply_global_niches(account_id: int, request: Request, db: Session = Depends(get_db)):
    toast = None
    try:
        account, n = AccountService.apply_global_niches_to_empty_pages(db, account_id)
        toast = (
            f"Đã copy Global Categories vào {n} page thiếu niche." if n else "Mọi page đã có niche — không đổi.",
            "success",
        )
    except ValueError as e:
        account = AccountService.get_account(db, account_id)
        toast = (str(e), "error")
    except Exception as e:
        logger.error("apply_global_niches account_id=%s: %s", account_id, e)
        account = AccountService.get_account(db, account_id)
        toast = (f"Lỗi: {e}", "error")

    if not account:
        return HTMLResponse(status_code=404)
    # Reload pages tab fragment with toast on account shell
    return _account_ui_response(request, account, toast=toast)

@router.get("/{account_id}/pages", response_class=HTMLResponse)
def get_account_pages(account_id: int, request: Request, db: Session = Depends(get_db)):
    account = AccountService.get_account(db, account_id)
    html_content = '<option value="" selected>Cá nhân / Mặc định</option>'
    
    if account and account.managed_pages_list:
        html_content += '<optgroup label="Managed Pages">'
        for page in account.managed_pages_list:
            name = page.get("name", "Unknown Page")
            url = page.get("url", "")
            html_content += f'<option value="{url}">{name}</option>'
        html_content += '</optgroup>'
        
    return HTMLResponse(content=html_content)

@router.post("/{account_id}/sync-pages", response_class=HTMLResponse)
def sync_account_pages(account_id: int, request: Request, db: Session = Depends(get_db)):
    account = AccountService.get_account(db, account_id)
    if not account:
        return HTMLResponse(status_code=404)

    toast = None
    try:
        AccountService.trigger_page_sync(db, account_id)
        toast = (
            "Đã chạy Sync Managed Pages nền — đợi 20–60s rồi F5 hoặc mở lại account để thấy danh sách page.",
            "success",
        )
    except ValueError as e:
        toast = (str(e), "error")
    except Exception as e:
        logger.error("sync_account_pages account_id=%s: %s", account_id, e)
        toast = (f"Không chạy được sync: {e}", "error")

    account = AccountService.get_account(db, account_id)
    return _account_ui_response(request, account, toast=toast, sync_started=True)
