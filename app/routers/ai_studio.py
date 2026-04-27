from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.main_templates import templates
from app.utils.htmx import htmx_toast_response
from app.services.ai_studio_service import AIStudioService
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/app/ai-studio", response_class=HTMLResponse)
def app_ai_studio(request: Request, db: Session = Depends(get_db)):
    ctx = AIStudioService.get_studio_context(db)
    return templates.TemplateResponse("pages/app_ai_studio.html", {
        "request": request,
        **ctx
    })

@router.post("/app/ai-studio/save", response_class=HTMLResponse)
def ai_studio_save(
    request: Request,
    db: Session = Depends(get_db),
    key: str = Form(...),
    value: str = Form(""),
):
    updated_by = request.client.host if request.client else None
    try:
        AIStudioService.save_setting(db, key=key, value=value, updated_by=updated_by)
        return htmx_toast_response("Đã lưu cấu hình thành công!", "success", refresh_page=False)
    except Exception as e:
        return htmx_toast_response(f"Lỗi: {e}", "error", refresh_page=False)

@router.post("/app/ai-studio/test-run", response_class=HTMLResponse)
async def ai_studio_test_run(
    request: Request,
    db: Session = Depends(get_db),
    prompt_content: str = Form(""),
    niche: str = Form("general"),
):
    try:
        parsed, raw_result, errors = await AIStudioService.run_test(prompt_content, niche)
        
        if parsed:
            return templates.TemplateResponse("partials/test_run_success.html", {"request": request, "parsed": parsed})
        
        if errors:
            return templates.TemplateResponse("partials/test_run_failure.html", {
                "request": request, "errors": errors, "cleaned": raw_result
            }, headers={"HX-Trigger": json.dumps({"showMessage": {"message": "Dữ liệu AI trả về không đúng cấu trúc!", "type": "warning"}})})
        
        return templates.TemplateResponse("partials/test_run_raw.html", {
            "request": request, "result": raw_result
        }, headers={"HX-Trigger": json.dumps({"showMessage": {"message": "Đã nhận kết quả dạng raw text", "type": "info"}})})
            
    except Exception as e:
        toast_msg = "Gemini API đang quá tải!" if "503" in str(e) else "Lỗi hệ thống khi gọi AI!"
        return templates.TemplateResponse("partials/test_run_error.html", {
            "request": request, "error": str(e)
        }, headers={"HX-Trigger": json.dumps({"showMessage": {"message": toast_msg, "type": "error"}})})
