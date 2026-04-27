import logging
from typing import Dict, Any, List
from sqlalchemy.orm import Session
from app.database.models import Job
from app.services.ai_runtime import pipeline
from app.services.content_orchestrator import ContentOrchestrator

logger = logging.getLogger(__name__)

class AIService:

    @staticmethod
    def generate_caption_simple(caption_context: str) -> Dict[str, Any]:
        prompt = "Xin hãy viết 1 viral caption."
        if caption_context:
            prompt = f"Gợi ý / Text nháp: {caption_context}\n{prompt}"

        payload, meta = pipeline.generate_caption(prompt)
        final_caption = payload.caption if payload else ""
        if payload and getattr(payload, "hashtags", None):
            final_caption += "\n\n" + " ".join(payload.hashtags)

        return {"caption": final_caption, "meta": meta}

    @staticmethod
    def analyze_media_for_job(db: Session, job_id: int, style: str = "general") -> Dict[str, Any]:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            raise ValueError(f"Không tìm thấy job #{job_id}.")
        if not job.media_path:
            raise ValueError("Job này không có media_path.")

        page_name = ""
        page_niches: List[str] = []
        if job.account:
            page_name = job.account.name or ""
            raw_niches = getattr(job.account, "niche_topics", "") or ""
            page_niches = [n.strip() for n in raw_niches.split(",") if n.strip()]

        orch = ContentOrchestrator()
        result = orch.generate_caption(
            video_path=job.media_path,
            style=style,
            context=job.caption or "",
            page_name=page_name,
            page_niches=page_niches,
        )

        return {
            "job_id": job_id,
            "caption": result.get("caption", ""),
            "hashtags": result.get("hashtags", []),
            "keywords": result.get("keywords", []),
            "affiliate_keyword": result.get("affiliate_keyword", ""),
        }
