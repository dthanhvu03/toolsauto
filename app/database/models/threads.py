from sqlalchemy import Column, ForeignKey, Index, Integer, String, Text

from app.database.models.base import Base, now_ts


class NewsArticle(Base):
    """
    Luu tru tin tuc cao duoc tu RSS/Web de AI xu ly dang Threads/Facebook.
    """

    __tablename__ = "news_articles"

    id = Column(Integer, primary_key=True, index=True)
    source_url = Column(String, unique=True, index=True, nullable=False)
    source_name = Column(String, nullable=True)  # e.g. "VnExpress"
    title = Column(String, nullable=False)
    summary = Column(Text, nullable=True)
    content = Column(Text, nullable=True)
    image_url = Column(String, nullable=True)
    category = Column(String, nullable=True, index=True)
    topic_key = Column(String, nullable=True, index=True)
    published_at = Column(Integer, nullable=True, index=True)  # Unix TS from RSS

    # Processing status
    status = Column(String, default="NEW", index=True)  # NEW, DRAFTED, POSTED, SKIPPED
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, default=now_ts, onupdate=now_ts)


class ThreadsInteraction(Base):
    """
    Theo doi cac luot tuong tac (reply) tren Threads de tranh tra loi lap lai.
    """

    __tablename__ = "threads_interactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), index=True)
    thread_id = Column(String, index=True)  # ID cua bai viet/binh luan goc
    username = Column(String)  # Nguoi minh tuong tac cung
    content = Column(Text)  # Noi dung minh da reply
    status = Column(String, default="DONE")  # DONE, FAILED

    created_at = Column(Integer, default=now_ts)

    __table_args__ = (
        Index("idx_threads_interaction_dedup", "account_id", "thread_id", unique=True),
    )
