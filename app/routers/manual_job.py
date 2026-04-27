from fastapi import APIRouter, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
import logging
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.main_templates import templates
from app.services.affiliate_service import AffiliateService
from app.services.job import JobService
from app.config import CONTENT_DIR

router = APIRouter(prefix="/jobs/manual", tags=["manual-jobs"])
logger = logging.getLogger(__name__)

MANUAL_DIR = str(CONTENT_DIR / "manual")

@router.get("/form", response_class=HTMLResponse)
def manual_job_form(request: Request, db: Session = Depends(get_db)):
    from app.services.account import AccountService
    accounts = AccountService.get_active_accounts(db)
    pages_by_acc = []
    for acc in accounts:
        for pg in (acc.managed_pages_list or []):
            pages_by_acc.append({
                "account_id": acc.id,
                "account_name": acc.name,
                "page_url": pg.get("url", ""),
                "page_name": pg.get("name", pg.get("url", "")),
            })
    return templates.TemplateResponse("fragments/manual_job_form.html", {
        "request": request,
        "pages": pages_by_acc,
    })

@router.post("/create", response_class=HTMLResponse)
async def manual_job_create(
    request: Request,
    account_id: int = Form(...),
    target_page: str = Form(...),
    caption: str = Form(""),
    media: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    caption_text = (caption or "").strip()
    if caption_text:
        comp_data = AffiliateService.compliance_check(caption_text)
        if comp_data.get("status") == "VIOLATION":
            violations = ", ".join([v["evidence"] for v in comp_data.get("violations", [])])
            msg = f"❌ Không thể tạo Job: Nội dung vi phạm chính sách Facebook ({violations})"
            return HTMLResponse(f'<div class="p-3 text-sm rounded bg-rose-50 text-rose-800 border border-rose-200 font-medium">{msg}</div>')

    try:
        job = JobService.create_manual_job_with_file(db, account_id, target_page, caption_text, media)
        msg = f"✅ Job #{job.id} đã được thêm vào Queue với độ ưu tiên tối đa!"
    except Exception as e:
        logger.error(f"Manual job create error: {e}")
        msg = f"❌ Lỗi tạo Job: {e}"

    return HTMLResponse(
        f'<div class="p-3 text-sm rounded bg-emerald-50 text-emerald-800 border border-emerald-200 font-medium">{msg}</div>'
        f'<script>if(window.refreshJobs) window.refreshJobs(1); setTimeout(() => document.getElementById("manualJobDialog").close(), 2000);</script>'
    )
