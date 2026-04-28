import json
import hashlib
import logging
import os
import re
import time

import requests

import app.config as config
from app.database.core import SessionLocal
from app.database.models import Account, Job, NewsArticle
from app.services.ai_runtime import pipeline
from app.services.content.topic_key import compute_topic_key
from app.services.content_orchestrator import ContentOrchestrator
from app.services.platform import settings as runtime_settings

logger = logging.getLogger("app.services.threads_news")

NEWS_JOB_PREFIX = "threads_news_v2_"
RECENT_JOB_STATUSES = ("PENDING", "RUNNING", "DONE")


class ThreadsNewsService:
    def __init__(self):
        self.orchestrator = ContentOrchestrator()

    @staticmethod
    def _extract_article_id(dedupe_key):
        if not dedupe_key or not str(dedupe_key).startswith(NEWS_JOB_PREFIX):
            return None
        article_id = str(dedupe_key)[len(NEWS_JOB_PREFIX):]
        return int(article_id) if article_id.isdigit() else None

    @staticmethod
    def _get_account_category(account_id, category_map):
        if not isinstance(category_map, dict):
            return None
        category = category_map.get(str(account_id))
        if category is None:
            category = category_map.get(account_id)
        if not category:
            return None
        return str(category).strip()

    def _find_recent_topic_duplicate(self, db, topic_key, cutoff_ts):
        if not topic_key:
            return None

        recent_jobs = (
            db.query(Job)
            .filter(
                Job.platform == "threads",
                Job.job_type == "post",
                Job.status.in_(RECENT_JOB_STATUSES),
                Job.created_at >= cutoff_ts,
                Job.dedupe_key.like(f"{NEWS_JOB_PREFIX}%"),
            )
            .order_by(Job.created_at.desc(), Job.id.desc())
            .all()
        )
        if not recent_jobs:
            return None

        article_ids = []
        for job in recent_jobs:
            article_id = self._extract_article_id(job.dedupe_key)
            if article_id is not None:
                article_ids.append(article_id)

        if not article_ids:
            return None

        article_topics = {
            row.id: row.topic_key
            for row in db.query(NewsArticle.id, NewsArticle.topic_key)
            .filter(NewsArticle.id.in_(article_ids))
            .all()
        }
        for job in recent_jobs:
            article_id = self._extract_article_id(job.dedupe_key)
            if article_id is None:
                continue
            if article_topics.get(article_id) == topic_key:
                return job
        return None

    def _download_image(self, url):
        """Tải ảnh từ URL về `storage/media/threads/`."""
        try:
            if not url:
                return None

            media_dir = os.path.join(str(config.STORAGE_DIR), "media", "threads")
            os.makedirs(media_dir, exist_ok=True)

            url_hash = hashlib.md5(url.encode()).hexdigest()
            ext = url.split(".")[-1].split("?")[0]
            if len(ext) > 4 or not ext:
                ext = "jpg"

            filename = f"news_{url_hash}.{ext}"
            filepath = os.path.join(media_dir, filename)

            if os.path.exists(filepath):
                return filepath

            response = requests.get(url, timeout=15, stream=True)
            if response.status_code == 200:
                with open(filepath, "wb") as file_obj:
                    for chunk in response.iter_content(1024):
                        file_obj.write(chunk)
                return filepath

            logger.warning(f"Failed to download image from {url}: Status {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Error downloading image: {e}")
            return None

    def process_news_to_threads(self):
        """Chuyển tin tức mới thành bài đăng Threads."""
        db = SessionLocal()
        try:
            now_ts = int(time.time())

            auto_mode = runtime_settings.get_bool("THREADS_AUTO_MODE", default=False, db=db)
            interval_min = runtime_settings.get_int("THREADS_POST_INTERVAL_MIN", default=180, db=db)
            max_chars_per_segment = runtime_settings.get_int(
                "THREADS_MAX_CHARS_PER_SEGMENT",
                default=450,
                db=db,
            )
            max_caption_length = runtime_settings.get_int(
                "THREADS_MAX_CAPTION_LENGTH",
                default=500,
                db=db,
            )
            max_article_age_hours = runtime_settings.get_int(
                "THREADS_MAX_ARTICLE_AGE_HOURS",
                default=6,
                db=db,
            )
            topic_dedup_hours = runtime_settings.get_int(
                "THREADS_TOPIC_DEDUP_HOURS",
                default=24,
                db=db,
            )
            account_category_map = runtime_settings.get_json(
                "THREADS_ACCOUNT_CATEGORY_MAP",
                default={},
                db=db,
            )

            last_job = (
                db.query(Job)
                .filter(
                    Job.platform == "threads",
                    Job.job_type == "post",
                    Job.created_at >= now_ts - (interval_min * 60),
                )
                .first()
            )
            if last_job:
                logger.info(f"Threads cooldown active. Skipping. (Last job: {last_job.id})")
                return

            account = (
                db.query(Account)
                .filter(Account.platform.like("%threads%"), Account.is_active == True)
                .first()
            )
            if not account:
                logger.error("No active Threads account found in DB.")
                return

            account_category = self._get_account_category(account.id, account_category_map)
            article_query = db.query(NewsArticle).filter(
                NewsArticle.status == "NEW",
                NewsArticle.published_at.isnot(None),
                NewsArticle.published_at >= now_ts - (max_article_age_hours * 3600),
            )
            if account_category:
                article_query = article_query.filter(NewsArticle.category.ilike(account_category))

            article = article_query.order_by(NewsArticle.published_at.desc(), NewsArticle.id.desc()).first()
            if not article:
                if account_category:
                    logger.info(
                        "No new %s articles for Threads account %s within last %sh.",
                        account_category,
                        account.id,
                        max_article_age_hours,
                    )
                else:
                    logger.info(
                        "No new articles to post to Threads within last %sh.",
                        max_article_age_hours,
                    )
                return

            if not article.topic_key:
                article.topic_key = compute_topic_key(article.title)
                db.flush()

            duplicate_job = self._find_recent_topic_duplicate(
                db,
                article.topic_key,
                now_ts - (topic_dedup_hours * 3600),
            )
            if duplicate_job:
                article.status = "SKIPPED"
                db.commit()
                logger.info(
                    "Skipping article %s due to topic dedup. topic_key=%s existing_job=%s",
                    article.id,
                    article.topic_key,
                    duplicate_job.id,
                )
                return

            logger.info(f"Processing article '{article.title}' for Threads...")

            segments = []
            job_status = "PENDING" if auto_mode else "DRAFT"
            try:
                prompt_template = runtime_settings.get_str("THREADS_AI_PROMPT", default="", db=db)
                if not prompt_template:
                    prompt_template = (
                        "Bạn là copywriter viết bài Threads tiếng Việt. Viết lại tin tức dưới đây thành "
                        "MỘT bài đăng Threads duy nhất, hấp dẫn và tự nhiên.\n\n"
                        "QUY TẮC BẮT BUỘC:\n"
                        "1. Cấu trúc: Hook hấp dẫn (có thể dùng emoji) + tóm tắt 2-3 ý chính + câu hỏi/CTA gợi tương tác.\n"
                        "2. Độ dài caption TỐI ĐA {max_chars} ký tự - KHÔNG bao gồm link.\n"
                        "3. TUYỆT ĐỐI KHÔNG viết bất kỳ link, URL, placeholder dạng `[Link nguồn ...]`, "
                        "`[xem tại ...]`, hay câu kiểu \"Xem chi tiết tại\", \"Đọc thêm tại\". Hệ thống sẽ tự động "
                        "thêm dòng nguồn + URL vào cuối bài, bạn KHÔNG cần làm.\n"
                        "4. KHÔNG nhắc tên báo nguồn ({source_name}) trong caption - hệ thống tự xử lý.\n"
                        "5. Văn phong tự nhiên, gần gũi như người thật viết, không sến. Tránh hashtag dài.\n\n"
                        "DỮ LIỆU:\n"
                        "Tiêu đề gốc: {title}\n"
                        "Tóm tắt gốc: {summary}\n\n"
                        'TRẢ VỀ JSON ĐÚNG ĐỊNH DẠNG: {{"caption": "<bài viết hoàn chỉnh, không có link/source>", '
                        '"reasoning": "<1 câu giải thích chiến lược>"}}'
                    )

                prompt = prompt_template.format(
                    title=article.title,
                    summary=article.summary or "",
                    source_name=article.source_name or "",
                    max_chars=max_chars_per_segment,
                )

                ai_result, meta = pipeline.generate_text(prompt)
                if ai_result:
                    try:
                        start_obj = ai_result.find("{")
                        end_obj = ai_result.rfind("}") + 1
                        start_list = ai_result.find("[")
                        end_list = ai_result.rfind("]") + 1

                        if start_obj != -1 and (start_list == -1 or start_obj < start_list):
                            segments = [json.loads(ai_result[start_obj:end_obj])]
                        elif start_list != -1:
                            list_obj = json.loads(ai_result[start_list:end_list])
                            if list_obj:
                                segments = [list_obj[0]]
                        else:
                            logger.warning(f"No JSON markers found in AI result. Raw: {ai_result[:100]}")
                    except Exception as json_error:
                        logger.warning(f"JSON parse failed for threads: {json_error}")

                if not segments:
                    segments = [{"caption": f"NÓNG: {article.title}\n\n{(article.summary or '')[:300]}...", "reasoning": "fallback"}]
            except Exception as e:
                logger.error(f"AI Generation failed: {e}")
                segments = [{"caption": f"NÓNG: {article.title}\n\n{(article.summary or '')[:300]}...", "reasoning": "error_fallback"}]

            media_path = None
            if article.image_url:
                media_path = self._download_image(article.image_url)

            if segments:
                seg = segments[0]
                caption = re.sub(r"<[^>]*>", "", seg.get("caption", ""))
                source_footer = f"\n\n(Nguồn: {article.source_name})\n{article.source_url}"

                if len(caption) + len(source_footer) > max_caption_length:
                    allowed_caption_len = max_caption_length - len(source_footer) - 5
                    if allowed_caption_len > 0:
                        caption = caption[:allowed_caption_len].strip() + "..."

                final_caption = f"{caption}{source_footer}"

                new_job = Job(
                    account_id=account.id,
                    platform="threads",
                    job_type="post",
                    status=job_status,
                    caption=final_caption,
                    media_path=media_path,
                    parent_job_id=None,
                    ai_reasoning=seg.get("reasoning", "single_post_v3"),
                    created_at=now_ts,
                    dedupe_key=f"{NEWS_JOB_PREFIX}{article.id}",
                )
                db.add(new_job)
                db.flush()
                logger.info(f"Created single Threads job {new_job.id} (Status: {job_status})")
            else:
                logger.warning(f"No content generated for article {article.id}. Skipping.")

            article.status = "DRAFTED" if job_status == "DRAFT" else "POSTED"

            db.commit()
            logger.info(f"Finished processing article {article.id}.")
        except Exception as e:
            logger.error(f"Error in process_news_to_threads: {e}")
            db.rollback()
        finally:
            db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    service = ThreadsNewsService()
    service.process_news_to_threads()
