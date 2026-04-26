import logging
import time
import os
import requests
from sqlalchemy import or_
from app.database.core import SessionLocal
from app.database.models import NewsArticle, Job, Account, RuntimeSetting
from app.services.content_orchestrator import ContentOrchestrator
import app.config as config

logger = logging.getLogger("app.services.threads_news")

class ThreadsNewsService:
    def __init__(self):
        self.orchestrator = ContentOrchestrator()

    def get_setting(self, db, key, default):
        s = db.query(RuntimeSetting).filter(RuntimeSetting.key == key).first()
        if not s:
            return default
        val = s.value.lower()
        if s.type == "bool":
            return val == "true"
        if s.type == "int":
            return int(val)
        return s.value

    def _download_image(self, url):
        """Tải ảnh từ URL về storage/media/threads/."""
        try:
            if not url:
                return None
            
            # Ensure dir exists
            media_dir = os.path.join(str(config.STORAGE_DIR), "media", "threads")
            os.makedirs(media_dir, exist_ok=True)
            
            # Create filename from hash of URL
            import hashlib
            h = hashlib.md5(url.encode()).hexdigest()
            ext = url.split(".")[-1].split("?")[0]
            if len(ext) > 4 or not ext:
                ext = "jpg"
            
            filename = f"news_{h}.{ext}"
            filepath = os.path.join(media_dir, filename)
            
            if os.path.exists(filepath):
                return filepath
            
            response = requests.get(url, timeout=15, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return filepath
            else:
                logger.warning(f"Failed to download image from {url}: Status {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    def process_news_to_threads(self):
        """Chuyển tin tức mới thành bài đăng Threads."""
        db = SessionLocal()
        try:
            # 1. Check settings
            auto_mode = self.get_setting(db, "THREADS_AUTO_MODE", False)
            interval_min = self.get_setting(db, "THREADS_POST_INTERVAL_MIN", 180)
            max_chars_per_segment = self.get_setting(db, "THREADS_MAX_CHARS_PER_SEGMENT", 450)
            max_caption_length = self.get_setting(db, "THREADS_MAX_CAPTION_LENGTH", 500)
            
            # 2. Check cooldown
            last_job = db.query(Job).filter(
                Job.platform == "threads",
                Job.job_type == "post",
                Job.created_at >= int(time.time()) - (interval_min * 60)
            ).first()
            if last_job:
                logger.info(f"Threads cooldown active. Skipping. (Last job: {last_job.id})")
                return

            # 3. Pick a NEW article
            article = db.query(NewsArticle).filter(
                NewsArticle.status == "NEW"
            ).order_by(NewsArticle.published_at.desc()).first()
            
            if not article:
                logger.info("No new articles to post to Threads.")
                return

            # 4. Find connected Threads account
            account = db.query(Account).filter(Account.platform.like("%threads%"), Account.is_active == True).first()
            if not account:
                logger.error("No active Threads account found in DB.")
                return

            logger.info(f"Processing article '{article.title}' for Threads...")

            # 5. Generate AI Content (Threading support)
            try:
                from app.services.gemini_api import GeminiAPIService
                gemini = GeminiAPIService()
                
                # Load prompt template from settings
                prompt_template = self.get_setting(db, "THREADS_AI_PROMPT", None)
                if not prompt_template:
                    # Fallback default prompt
                    prompt_template = (
                        "Viết lại tin tức này thành bài đăng Threads thu hút.\n"
                        "Chia thành 2-4 bài, mỗi bài dưới {max_chars} ký tự.\n"
                        "Tiêu đề: {title}\nTóm tắt: {summary}\nNguồn: {source_name}\n"
                        'TRẢ VỀ JSON LIST: [{{"caption": "...", "reasoning": "..."}}]'
                    )
                
                prompt = prompt_template.format(
                    title=article.title,
                    summary=article.summary or "",
                    source_name=article.source_name or "",
                    max_chars=max_chars_per_segment,
                )
                
                ai_result = gemini.ask(prompt)
                segments = []
                if ai_result:
                    # Parse JSON list
                    try:
                        import json
                        # Find [ and ] to extract JSON if there's markdown fluff
                        start = ai_result.find("[")
                        end = ai_result.rfind("]") + 1
                        if start != -1 and end != -1:
                            segments = json.loads(ai_result[start:end])
                        else:
                            # Fallback: maybe it returned a single object?
                            start_obj = ai_result.find("{")
                            end_obj = ai_result.rfind("}") + 1
                            if start_obj != -1 and end_obj != -1:
                                obj = json.loads(ai_result[start_obj:end_obj])
                                segments = [obj]
                    except Exception as je:
                        logger.warning(f"JSON parse failed for threading: {je}. Using raw fallback.")
                
                if not segments:
                    # Fallback to simple single post
                    segments = [{"caption": f"NÓNG: {article.title}\n\n{article.summary[:300]}...", "reasoning": "fallback"}]

            except Exception as e:
                logger.error(f"AI Generation failed: {e}")
                segments = [{"caption": f"NÓNG: {article.title}\n\n{article.summary[:300]}...", "reasoning": "error_fallback"}]

            # 5b. Download Image (Chỉ cho bài đầu tiên)
            media_path = None
            if article.image_url:
                media_path = self._download_image(article.image_url)

            # 6. Create Jobs (Threading)
            last_job_id = None
            job_status = "PENDING" if auto_mode else "DRAFT"
            
            for i, seg in enumerate(segments):
                caption = seg.get("caption", "")
                # Final cleanup
                import re
                caption = re.sub(r'<[^>]*>', '', caption)
                
                # Append source link to the LAST segment or first if single
                if i == len(segments) - 1:
                    caption += f"\n\n(Nguồn: {article.source_name})\n{article.source_url}"
                
                if len(caption) > max_caption_length:
                    caption = caption[:max_caption_length - 3] + "..."

                new_job = Job(
                    account_id=account.id,
                    platform="threads",
                    job_type="post",
                    status=job_status,
                    caption=caption,
                    media_path=media_path if i == 0 else None, # Chỉ ảnh cho bài đầu
                    parent_job_id=last_job_id,
                    ai_reasoning=seg.get("reasoning", ""),
                    created_at=int(time.time()),
                    dedupe_key=f"threads_news_{article.id}_{i}"
                )
                db.add(new_job)
                db.flush() # Lấy ID cho bài sau
                last_job_id = new_job.id
                
                logger.info(f"Created Threads job {new_job.id} (Part {i+1}, Status: {job_status})")
            
            # 7. Update article status
            article.status = "DRAFTED" if job_status == "DRAFT" else "POSTED"
            
            db.commit()
            logger.info(f"Finished processing article {article.id} into {len(segments)} segments.")

            
        except Exception as e:
            logger.error(f"Error in process_news_to_threads: {e}")
            db.rollback()
        finally:
            db.close()

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO)
    service = ThreadsNewsService()
    service.process_news_to_threads()
