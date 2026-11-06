"""Trình điều phối quét bài, phân tích và quản lý thử nghiệm A/B trên Threads.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from app.features.threads.growth.config import (
    ABVariant,
    GrowthLimits,
    TargetBot,
    load_limits,
)
from app.features.threads.growth.evaluator import GrowthEvaluator
from app.features.threads.growth.scanner import ScannedPost
from app.features.threads.growth.storage import GrowthStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PostingQuota:
    allowed: bool
    reason: str
    wait_sec: int
    posted_last_hour: int
    posted_last_day: int


class GrowthRunner:
    def __init__(
        self,
        storage: Optional[GrowthStorage] = None,
        limits: Optional[Callable[[], GrowthLimits]] = None,
    ):
        self.storage = storage or GrowthStorage()
        # Hàm đọc giới hạn (mặc định: cài đặt web) — gọi lại mỗi lần để đổi trên web là ăn ngay.
        self._limits = limits or load_limits

    @property
    def limits(self) -> GrowthLimits:
        return self._limits()

    def _next_variant_for(self, bot_type: TargetBot) -> ABVariant:
        """Chia đều A/B theo số bài đã lưu trong DB (bền qua các lần chạy CLI). Bằng nhau → A."""
        counts = self.storage.variant_counts(bot_type)
        return min(ABVariant, key=lambda v: (counts.get(v.value, 0), v.value))

    async def ingest_scanned_post(
        self,
        post: ScannedPost,
        forced_bot: Optional[TargetBot] = None,
        forced_variant: Optional[ABVariant] = None,
        auto_post_min: Optional[int] = None,
    ) -> Optional[int]:
        """Tiếp nhận bài viết đã quét, phân loại bot, gán biến thể A/B và sinh câu trả lời.

        ``auto_post_min``: điểm ≥ ngưỡng này → lưu thẳng ``approved`` (worker tự đăng); None = luôn chờ duyệt.
        Bài chỉ có câu mẫu (AI lỗi) vẫn chờ duyệt — không tự đăng câu mẫu lặp lại.
        """
        if self.storage.is_thread_scanned(post.thread_id):
            logger.debug("Thread %s already ingested. Skipping.", post.thread_id)
            return None

        # 1. Phân loại bot
        bot_type = forced_bot or GrowthEvaluator.classify_target_bot(post.content)
        if not bot_type:
            logger.debug("Thread %s does not match any bot target.", post.thread_id)
            return None

        # 2. Tính điểm liên quan
        relevance = GrowthEvaluator.calculate_relevance(post.content, bot_type)
        min_relevance = self.limits.min_relevance
        if relevance < min_relevance:
            logger.debug(
                "Thread %s relevance %s < %s. Skipping.", post.thread_id, relevance, min_relevance
            )
            return None

        # 3. Gán biến thể A/B
        variant = forced_variant or self._next_variant_for(bot_type)

        # 4. Sinh phản hồi AI theo góc độ A hoặc B
        suggested_reply, analysis = await GrowthEvaluator.generate_reply(
            content=post.content,
            bot_type=bot_type,
            variant=variant,
        )

        # 5. Lưu vào database
        auto = (
            auto_post_min is not None
            and relevance >= auto_post_min
            and not analysis.startswith("Fallback")
        )
        post_id = self.storage.save_post(
            thread_id=post.thread_id,
            post_url=post.post_url,
            author=post.author,
            content=post.content,
            target_bot=bot_type,
            variant=variant,
            relevance_score=relevance,
            ai_analysis=analysis,
            suggested_reply=suggested_reply,
            status="approved" if auto else "pending",
            auto_approved=auto,
            post_created_at=post.created_at.isoformat() if post.created_at else None,
            like_count=post.likes,
            reply_count=post.replies,
            author_followers=post.author_followers,
            reach=post.reach,
        )
        logger.info(
            "Ingested thread %s (ID=%s) for %s [Variant %s]%s",
            post.thread_id, post_id, bot_type.value, variant.value, " auto" if auto else "",
        )
        return post_id or None

    async def ingest_batch(self, posts: List[ScannedPost]) -> List[int]:
        ingested_ids: List[int] = []
        for p in posts:
            pid = await self.ingest_scanned_post(p)
            if pid:
                ingested_ids.append(pid)
        return ingested_ids

    async def switch_variant(self, post_id: int, new_variant: ABVariant) -> Optional[Dict[str, Any]]:
        """Đổi biến thể và sinh lại câu trả lời bằng AI (AI lỗi → câu mẫu của biến thể mới)."""
        post = self.storage.get_post_by_id(post_id)
        if not post:
            return None
        reply, analysis = await GrowthEvaluator.generate_reply(
            content=post["content"],
            bot_type=TargetBot(post["target_bot"]),
            variant=new_variant,
        )
        self.storage.switch_variant(post_id, new_variant, reply, ai_analysis=analysis)
        return self.storage.get_post_by_id(post_id)

    def approve_and_prepare(
        self, post_id: int, override_reply: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        post = self.storage.get_post_by_id(post_id)
        if not post:
            return None
        actual_reply = override_reply or post["suggested_reply"]
        self.storage.update_status(post_id, "approved", actual_reply=actual_reply)
        return self.storage.get_post_by_id(post_id)

    def reject(self, post_id: int, reason: str = "user_rejected") -> bool:
        return self.storage.update_status(post_id, "rejected", error_message=reason)

    def posting_quota(self, now: Optional[datetime] = None) -> PostingQuota:
        """Có được đăng reply tiếp theo ngay bây giờ không (theo giới hạn trên web).

        Bên đăng bài PHẢI gọi hàm này trước mỗi lần đăng; ``mark_posted`` chỉ ghi nhận sau khi đã đăng.
        """
        lim = self.limits
        now = now or datetime.now(timezone.utc)
        hour = self.storage.count_posted_since(now - timedelta(hours=1))
        day = self.storage.count_posted_since(now - timedelta(days=1))

        def deny(reason: str, wait: float) -> PostingQuota:
            return PostingQuota(False, reason, max(int(wait), 1), hour, day)

        if day >= lim.max_replies_per_day:
            return deny(f"đủ {lim.max_replies_per_day} reply / 24 giờ", 3600)
        if hour >= lim.max_replies_per_hour:
            return deny(f"đủ {lim.max_replies_per_hour} reply / giờ", 600)
        last = self.storage.last_posted_at()
        if last is not None:
            gap = (now - last).total_seconds()
            if gap < lim.min_delay_sec:
                return deny(f"mới đăng {int(gap)}s trước (tối thiểu {lim.min_delay_sec}s)", lim.min_delay_sec - gap)
        return PostingQuota(True, "", 0, hour, day)

    def next_delay_sec(self) -> int:
        """Thời gian chờ ngẫu nhiên giữa hai reply (giữa min và max trên web)."""
        lim = self.limits
        return random.randint(lim.min_delay_sec, max(lim.min_delay_sec, lim.max_delay_sec))

    def mark_posted(self, post_id: int, reply_url: Optional[str] = None) -> bool:
        return self.storage.update_status(post_id, "posted", reply_url=reply_url)

    def mark_failed(self, post_id: int, error: str) -> bool:
        return self.storage.update_status(post_id, "failed", error_message=error[:500])

    def get_ab_summary(self) -> Dict[str, Any]:
        return self.storage.get_ab_stats()
