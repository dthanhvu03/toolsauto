from sqlalchemy import Column, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import relationship

from app.database.models.base import Base, now_ts


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

    # AI Processing status
    status = Column(String, default="NEW", index=True)  # NEW, DOWNLOADED, DRAFTED, FAILED
    last_error = Column(String, nullable=True)

    @property
    def thumbnail_url(self) -> str:
        """Returns the relative path to the generated thumbnail collage, or empty string if not downloaded."""
        if self.status in ("NEW", "FAILED") or not self.url:
            return ""
        import hashlib
        fhash = hashlib.md5(self.url.encode()).hexdigest()
        return f"/thumbnails/{fhash}_collage.jpg"

    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)


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
