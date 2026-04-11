from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.database.core import get_db
from app.main_templates import templates
from app.services import settings as runtime_settings
from app.utils.htmx import htmx_toast_response
import traceback
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/app/ai-studio", response_class=HTMLResponse)
def app_ai_studio(request: Request, db: Session = Depends(get_db)):
    """Render the AI Prompt Studio Playground"""
    
    base_personas = {
        "general": {"key": "ai.prompt.general", "label": "Tổng Hợp (General)", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'},
        "beauty": {"key": "ai.prompt.beauty", "label": "Mỹ Phẩm (Beauty)", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"></path></svg>'},
        "fashion": {"key": "ai.prompt.fashion", "label": "Thời Trang (Fashion)", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z"></path></svg>'},
        "tech": {"key": "ai.prompt.tech", "label": "Công Nghệ (Tech)", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 18h.01M8 21h8a2 2 0 002-2V5a2 2 0 00-2-2H8a2 2 0 00-2 2v14a2 2 0 002 2z"></path></svg>'},
        "kitchen": {"key": "ai.prompt.home", "label": "Gia Dụng (Home)", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"></path></svg>'},
        "funny": {"key": "ai.prompt.funny", "label": "Hài Hước (Funny)", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>'},
    }
    
    configs = {
        "visual_hook": {"key": "ai.prompt.visual_hook", "label": "Visual Hook Rules", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path></svg>'},
        "engagement": {"key": "ai.prompt.engagement_secrets", "label": "Engagement Secrets", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 18.657A8 8 0 016.343 7.343S7 9 7 9a8.01 8.01 0 011.657 1.657A8 8 0 0117.657 18.657zM12 4s-1 1-1 3.5S12 11 12 11s2 .5 2 2c0 2.5-3 5-3 5"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.5 12.5s-2 2-2 4"></path></svg>'},
        "fallback_cap": {"key": "ai.fallback_caption_pool", "label": "Fallback Captions", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path></svg>'},
        "fallback_hash": {"key": "ai.fallback_hashtag_pool", "label": "Fallback Hashtags", "icon": '<svg class="w-5 h-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z"></path></svg>'},
    }

    overrides = runtime_settings.get_overrides(db, use_cache=False)
    
    for k, info in base_personas.items():
        spec = runtime_settings.SETTINGS.get(info["key"])
        ov = overrides.get(info["key"])
        info["value"] = ov if ov is not None else spec.default_getter() if spec else ""
        
    for k, info in configs.items():
        spec = runtime_settings.SETTINGS.get(info["key"])
        ov = overrides.get(info["key"])
        info["value"] = ov if ov is not None else spec.default_getter() if spec else ""

    return templates.TemplateResponse("pages/app_ai_studio.html", {
        "request": request,
        "personas": base_personas,
        "configs": configs,
    })

@router.post("/app/ai-studio/save", response_class=HTMLResponse)
def ai_studio_save(
    request: Request,
    db: Session = Depends(get_db),
    key: str = Form(...),
    value: str = Form(""),
):
    """Save setting without redirecting so HTMX can update gracefully."""
    updated_by = request.client.host if request.client else None
    try:
        runtime_settings.upsert_setting(db, key=key, raw_value=value, updated_by=updated_by)
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
    """Mock endpoint that builds the mega-prompt and sends to Gemini."""
    from app.services.brain_factory import BrainFactory
    from app.services.gemini_api import GeminiAPIService
    
    try:
        mega_prompt = BrainFactory.build_caption_prompt(prompt_content, niche)
        api = GeminiAPIService()
        result = await api.ask_async(mega_prompt)
        
        cleaned = BrainFactory.clean_json_blocks(result)
        try:
            parsed = json.loads(cleaned)
            errors = []
            if not parsed.get('title'): errors.append("Thiếu caption (title)")
            if not parsed.get('hashtags'): errors.append("Thiếu hashtags")
            
            if errors:
                return templates.TemplateResponse("partials/test_run_failure.html", {
                    "request": request, "errors": errors, "cleaned": cleaned
                }, headers={"HX-Trigger": json.dumps({"showMessage": {"message": "Dữ liệu AI trả về không đúng cấu trúc!", "type": "warning"}})})
            
            return templates.TemplateResponse("partials/test_run_success.html", {"request": request, "parsed": parsed})
        except Exception:
            return templates.TemplateResponse("partials/test_run_raw.html", {
                "request": request, "result": result
            }, headers={"HX-Trigger": json.dumps({"showMessage": {"message": "Đã nhận kết quả dạng raw text", "type": "info"}})})
            
    except Exception as e:
        logger.exception("AI Studio Test Run failed")
        toast_msg = "Gemini API đang quá tải!" if "503" in str(e) else "Lỗi hệ thống khi gọi AI!"
        return templates.TemplateResponse("partials/test_run_error.html", {
            "request": request, "error": str(e)
        }, headers={"HX-Trigger": json.dumps({"showMessage": {"message": toast_msg, "type": "error"}})})
