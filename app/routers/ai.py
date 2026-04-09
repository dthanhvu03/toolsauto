from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse
import logging

from app.services.ai_runtime import pipeline

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)

@router.post("/generate-caption")
async def generate_caption(request: Request):
    """
    Generate an AI Caption based on context.
    We accept any form payload dynamically.
    """
    try:
        form_data = await request.form()
        caption_context = form_data.get("caption", "")
        
        prompt = "Xin hãy viết 1 viral caption."
        if caption_context:
            prompt = f"Gợi ý / Text nháp: {caption_context}\n{prompt}"
            
        payload, meta = pipeline.generate_caption(prompt)
        
        # If payload parsing succeeded, we use the cleaned caption
        # Else we fallback to whatever is available
        final_caption = payload.caption if payload else ""
        
        # If payload had hashtags, format them nicely
        if payload and getattr(payload, "hashtags", None):
            final_caption += "\n\n" + " ".join(payload.hashtags)
        
        return JSONResponse({
            "caption": final_caption,
            "meta": meta
        })
        
    except Exception as e:
        logger.error(f"Lỗi khi chạy AI pipeline: {e}")
        return JSONResponse({
            "caption": "",
            "meta": {
                "provider": "ERROR",
                "model": "N/A",
                "latency_ms": 0,
                "fail_reason": "request_failed",
                "circuit_state": "UNKNOWN",
                "is_fallback": True,
                "fail_trace": [{"layer": "FastAPI", "reason": str(e)}]
            }
        })
