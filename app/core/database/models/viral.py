import json

from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database.models.base import Base, now_ts


def _parse_target_pages(raw: str | None, legacy: str | None) -> list[str]:
    """
    ADR-020: đọc danh sách Page theo thứ tự ưu tiên ``target_pages`` → ``[target_page]`` → ``[]``.
    Dùng chung cho ViralSource và ViralMaterial (giống ``Account.target_pages_list``).
    """
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                pages = [str(u).strip() for u in data if str(u or "").strip()]
                if pages:
                    return pages
        except Exception:
            pass
    legacy = (legacy or "").strip()
    return [legacy] if legacy else []


def _dump_target_pages(pages: list[str] | None) -> tuple[str | None, str | None]:
    """Chuẩn hoá list Page → ``(json_hoặc_None, page_đầu_hoặc_None)``: strip, bỏ rỗng, bỏ trùng, giữ thứ tự."""
    cleaned: list[str] = []
    for page in pages or []:
        page = str(page or "").strip()
        if page and page not in cleaned:
            cleaned.append(page)
    if not cleaned:
        return None, None
    return json.dumps(cleaned, ensure_ascii=False), cleaned[0]


class ViralMaterial(Base):
    """
    Bảng lưu trữ thông tin các Video/Post Viral quét được từ Mạng xã hội
    thông qua quá trình tương tác dạo.
    """
    __tablename__ = "viral_materials"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, default="facebook", index=True)
    url = Column(String, unique=True, index=True)
    title = Column(String, nullable=True)
    views = Column(Integer, default=0, index=True)
    scraped_by_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    target_page = Column(String, nullable=True)  # Used for manual /reup targeting specific pages
    # ADR-020: JSON list URL Page — chép từ nguồn lúc quét; NULL = đường cũ (1 Page hoặc round-robin)
    target_pages = Column(Text, nullable=True)

    # AI Processing status
    status = Column(String, default="NEW", index=True)  # NEW, PROCESSING, REUP, DRAFTED, FAILED, BOOST_PENDING
    last_error = Column(String, nullable=True)
    process_tries = Column(Integer, default=0)  # Intake attempts (download/reup); cap retry

    # ADR-021: caption AI viết thẳng cho material READY (không cần account, không cần Job).
    ai_caption = Column(Text, nullable=True)
    ai_hashtags = Column(Text, nullable=True)  # JSON list, ví dụ ["#viral", "#xuhuong"]
    ai_caption_at = Column(Integer, nullable=True)  # epoch giây — lần chạy AI gần nhất (kể cả lần lỗi)
    ai_caption_error = Column(Text, nullable=True)  # lý do lần chạy gần nhất thất bại; NULL = lần cuối OK

    @property
    def ai_hashtags_list(self) -> list[str]:
        """ADR-021: đọc ``ai_hashtags`` → list[str]. JSON hỏng / không phải list ⇒ ``[]``."""
        raw = self.ai_hashtags
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [str(h).strip() for h in data if str(h or "").strip()]

    @property
    def target_pages_list(self) -> list[str]:
        """ADR-020: Page đích của material — ``target_pages`` → ``[target_page]`` → ``[]``."""
        return _parse_target_pages(self.target_pages, self.target_page)

    @target_pages_list.setter
    def target_pages_list(self, pages: list[str] | None):
        self.target_pages, self.target_page = _dump_target_pages(pages)

    @property
    def thumbnail_url(self) -> str:
        """Returns the relative path to the generated thumbnail collage, or empty string if not downloaded."""
        if self.status in ("NEW", "FAILED", "PROCESSING") or not self.url:
            return ""
        import hashlib
        fhash = hashlib.md5(self.url.encode()).hexdigest()
        return f"/thumbnails/{fhash}_collage.jpg"

    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)


class ViralSource(Base):
    """
    Nguồn quét tự động (ADR-019) — kênh TikTok / YouTube Shorts, ĐỘC LẬP với account.
    ``min_views`` / ``max_videos`` null = dùng setting ``viral.min_views`` /
    ``viral.max_videos_per_channel``. ``last_scanned_at`` là epoch giây (như ``created_at``).
    """
    __tablename__ = "viral_sources"

    id = Column(Integer, primary_key=True, index=True)
    platform = Column(String, nullable=False)  # tiktok | youtube
    url = Column(String, unique=True, index=True, nullable=False)  # URL kênh đã chuẩn hoá
    handle = Column(String, nullable=True)
    min_views = Column(Integer, nullable=True)
    max_videos = Column(Integer, nullable=True)
    target_page = Column(String, nullable=True)  # legacy — 1 Page; giữ để tương thích ngược
    # ADR-020: JSON list URL Page — mỗi video nhân bản ra TẤT CẢ Page ở đây
    target_pages = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True, nullable=False, index=True)
    last_scanned_at = Column(Integer, nullable=True)
    last_found = Column(Integer, default=0)
    last_error = Column(String, nullable=True)

    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)

    @property
    def target_pages_list(self) -> list[str]:
        """ADR-020: ``target_pages`` → ``[target_page]`` → ``[]``."""
        return _parse_target_pages(self.target_pages, self.target_page)

    @target_pages_list.setter
    def target_pages_list(self, pages: list[str] | None):
        self.target_pages, self.target_page = _dump_target_pages(pages)


class DiscoveredChannel(Base):
    """Kênh TikTok đối thủ phát hiện tự động qua hashtag search."""
    __tablename__ = "discovered_channels"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    channel_url = Column(String, nullable=False)
    channel_name = Column(String, nullable=True)
    keyword_used = Column(String, nullable=True)
    follower_count = Column(Integer, default=0)
    video_count = Column(Integer, default=0)
    avg_views = Column(Integer, default=0)
    post_frequency = Column(Float, default=0.0)  # videos per week
    score = Column(Float, default=0.0, index=True)  # avg_views * post_frequency / 1000
    status = Column(String, default="NEW", index=True)  # NEW, APPROVED, IGNORED

    discovered_at = Column(Integer, default=now_ts)
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)

    account = relationship("Account")


class CompetitorReel(Base):
    """
    Reel đối thủ được thu thập tự động từ GQL suggested-reels stream.
    Dedup theo (reel_url, scrape_date).
    """
    __tablename__ = "competitor_reels"

    id = Column(Integer, primary_key=True, index=True)
    reel_url = Column(String, nullable=False, index=True)
    scrape_date = Column(String, nullable=False, index=True)  # YYYY-MM-DD
    page_url = Column(String, nullable=True, index=True)

    views = Column(Integer, default=0, index=True)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)
    caption = Column(String, nullable=True)

    recorded_at = Column(Integer, default=now_ts, index=True)

    __table_args__ = (
        Index('idx_competitor_dedup', 'reel_url', 'scrape_date', unique=True),
    )


class PageInsight(Base):
    """
    Theo dõi tăng trưởng của Page theo thời gian (Time-series data).
    Data này dùng để vẽ biểu đồ và bảng xếp hạng trên Dashboard Insights.
    """
    __tablename__ = "page_insights"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True, nullable=True)
    platform = Column(String, default="facebook", index=True)
    page_url = Column(String, index=True, nullable=False)
    page_name = Column(String, nullable=True)

    post_url = Column(String, index=True, nullable=False)
    caption = Column(String, nullable=True)
    published_date = Column(String, nullable=True)

    views = Column(Integer, default=0, index=True)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    shares = Column(Integer, default=0)

    recorded_at = Column(Integer, default=now_ts, index=True)  # Thời điểm cào data


class AffiliateLink(Base):
    """
    Kho Link Affiliate cho tính năng "Máy Bơm Affiliate" (Auto-Injector).
    Khi AI nhận diện được keyword trùng khớp trong video, bot sẽ tự bốc url & comment_template
    để auto comment vào post.
    """
    __tablename__ = "affiliate_links"

    id = Column(Integer, primary_key=True, index=True)
    keyword = Column(String, unique=True, index=True, nullable=False)  # e.g. "áo thun", "giày sneaker"
    url = Column(String, nullable=False)  # e.g. "https://shope.ee/..."
    comment_template = Column(String, nullable=True)  # e.g. "Đang sale mua ở đây nè: [LINK]"
    commission_rate = Column(Float, nullable=True)  # e.g. 15.5 cho 15.5%
    ai_status = Column(String, nullable=True, index=True)  # None, PENDING, PROCESSING, DONE, FAILED
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)
