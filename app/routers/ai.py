from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
import logging
from app.database.core import get_db
from app.services.ai_service import AIService

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


@router.post("/generate-caption")
async def generate_caption(request: Request):
    try:
        form_data = await request.form()
        caption_context = form_data.get("caption", "")
        res = AIService.generate_caption_simple(caption_context)
        return JSONResponse(res)
    except Exception as e:
        logger.error("generate_caption error: %s", e)
        return JSONResponse({
            "caption": "",
            "meta": {
                "provider": "ERROR", "model": "N/A", "latency_ms": 0,
                "fail_reason": "request_failed", "circuit_state": "UNKNOWN",
                "is_fallback": True,
                "fail_trace": [{"layer": "FastAPI", "reason": str(e)}]
            }
        })


@router.post("/analyze-media")
async def analyze_media(request: Request, db: Session = Depends(get_db)):
    try:
        data = await request.json()
        job_id = data.get("job_id")
        style = data.get("style", "general")

        if not job_id:
            return JSONResponse({"error": "job_id là bắt buộc."}, status_code=400)

        res = AIService.analyze_media_for_job(db, job_id, style)
        return JSONResponse(res)

    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404 if "tìm thấy" in str(e) else 400)
    except Exception as e:
        logger.error("analyze_media error: %s", e)
        return JSONResponse({"error": str(e)}, status_code=500)
