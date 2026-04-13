from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse
import logging

from sqlalchemy.orm import Session
from app.database.core import get_db
from app.services.ai_runtime import pipeline

router = APIRouter(prefix="/ai", tags=["ai"])
logger = logging.getLogger(__name__)


@router.post("/generate-caption")
async def generate_caption(request: Request):
    """Generate caption from text context only (text-only AI pipeline)."""
    try:
        form_data = await request.form()
        caption_context = form_data.get("caption", "")

        prompt = "Xin hãy viết 1 viral caption."
        if caption_context:
            prompt = f"Gợi ý / Text nháp: {caption_context}\n{prompt}"

        payload, meta = pipeline.generate_caption(prompt)
        final_caption = payload.caption if payload else ""
        if payload and getattr(payload, "hashtags", None):
            final_caption += "\n\n" + " ".join(payload.hashtags)

        return JSONResponse({"caption": final_caption, "meta": meta})

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
    """
    Generate caption from a job's media file using ContentOrchestrator
    (multimodal: video keyframes + transcript → Gemini → caption + hashtags).

    Accepts JSON: { "job_id": int, "style": "general|sales|affiliate" }
    """
    try:
        data = await request.json()
        job_id = data.get("job_id")
        style = data.get("style", "general")

        if not job_id:
            return JSONResponse({"error": "job_id là bắt buộc."}, status_code=400)

        from app.database.models import Job
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            return JSONResponse({"error": f"Không tìm thấy job #{job_id}."}, status_code=404)

        if not job.media_path:
            return JSONResponse({"error": "Job này không có media_path."}, status_code=400)

        # Gather optional context from account
        page_name = ""
        page_niches: list = []
        if job.account:
            page_name = job.account.name or ""
            raw_niches = getattr(job.account, "niche_topics", "") or ""
            page_niches = [n.strip() for n in raw_niches.split(",") if n.strip()]

        from app.services.content_orchestrator import ContentOrchestrator
        orch = ContentOrchestrator()
        result = orch.generate_caption(
            video_path=job.media_path,
            style=style,
            context=job.caption or "",
            page_name=page_name,
            page_niches=page_niches,
        )

        return JSONResponse({
            "job_id": job_id,
            "caption": result.get("caption", ""),
            "hashtags": result.get("hashtags", []),
            "keywords": result.get("keywords", []),
            "affiliate_keyword": result.get("affiliate_keyword", ""),
        })

    except Exception as e:
        logger.error("analyze_media job_id=%s error: %s", data.get("job_id") if "data" in dir() else "?", e)
        return JSONResponse({"error": str(e)}, status_code=500)
