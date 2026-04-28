import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.services.ai_runtime as ai_runtime
from app.database.models.accounts import Account
from app.database.models.jobs import Job
from app.database.models.settings import RuntimeSetting
from app.database.models.threads import NewsArticle
from app.services.content import threads_news as threads_news_module
from app.services.content.news_scraper import NewsScraper, RSS_SOURCES
from app.services.content.topic_key import compute_topic_key
from app.services.platform import settings as runtime_settings


@pytest.fixture
def isolated_session_factory(monkeypatch, tmp_path):
    db_path = tmp_path / "plan033.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    Account.__table__.create(engine)
    Job.__table__.create(engine)
    RuntimeSetting.__table__.create(engine)
    NewsArticle.__table__.create(engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    class DummyOrchestrator:
        pass

    monkeypatch.setattr(threads_news_module, "SessionLocal", session_factory)
    monkeypatch.setattr(threads_news_module, "ContentOrchestrator", DummyOrchestrator)
    monkeypatch.setattr(
        ai_runtime.pipeline,
        "generate_text",
        lambda prompt: ('{"caption": "Ban tin the gioi", "reasoning": "pytest"}', {"ok": True}),
    )
    runtime_settings._cache_ts = 0.0
    runtime_settings._cache_values = {}

    try:
        yield session_factory
    finally:
        runtime_settings._cache_ts = 0.0
        runtime_settings._cache_values = {}
        engine.dispose()


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Trump ký lệnh áp thuế thép Canada", "Tổng thống Trump áp thuế thép Canada"),
        ("Israel mở chiến dịch không kích Tehran", "Tehran bị Israel không kích trong chiến dịch"),
        ("Động đất mạnh rung chuyển Tokyo Nhật Bản", "Tokyo rung chuyển vì động đất mạnh ở Nhật Bản"),
        ("Apple bị EU phạt vì độc quyền App Store", "EU phạt Apple vụ độc quyền trên App Store"),
    ],
)
def test_compute_topic_key_same_event_pairs_match(left, right):
    assert compute_topic_key(left) == compute_topic_key(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Trump áp thuế thép Canada", "EU duyệt gói hỗ trợ Ukraine"),
        ("Động đất ở Tokyo", "Bầu cử sớm tại Hàn Quốc"),
        ("Israel không kích Tehran", "Giá dầu giảm sau họp OPEC"),
        ("Apple bị EU phạt", "NASA thử động cơ tên lửa mới"),
    ],
)
def test_compute_topic_key_different_event_pairs_diverge(left, right):
    assert compute_topic_key(left) != compute_topic_key(right)


def test_scrape_all_runs_once_and_saves_topic_key(monkeypatch, isolated_session_factory):
    from app.services.content import news_scraper as news_scraper_module

    monkeypatch.setattr(news_scraper_module, "SessionLocal", isolated_session_factory)

    def fake_fetch(self, url):
        slug = url.replace("https://", "").replace("/", "-")
        return [
            {
                "title": f"Tin nong {slug}",
                "link": f"https://example.test/{slug}",
                "summary": "Tom tat ngan",
                "pub_date": "Mon, 28 Apr 2026 10:00:00 GMT",
                "image_url": "",
            }
        ]

    monkeypatch.setattr(NewsScraper, "fetch_rss", fake_fetch)

    scraper = NewsScraper()
    inserted_count = scraper.scrape_all()

    session = isolated_session_factory()
    try:
        articles = session.query(NewsArticle).order_by(NewsArticle.id.asc()).all()
        assert len(RSS_SOURCES) == 9
        assert inserted_count == 9
        assert len(articles) == 9
        assert all(article.topic_key and len(article.topic_key) == 16 for article in articles)
    finally:
        session.close()


def test_process_news_to_threads_skips_articles_older_than_max_age_hours(isolated_session_factory):
    now_ts = int(time.time())
    session = isolated_session_factory()
    try:
        session.add(Account(id=1, name="threads-world", platform="threads", is_active=True))
        old_article = NewsArticle(
            source_url="https://example.test/old-world",
            source_name="Test Source",
            title="Tin the gioi cu",
            summary="Tin da qua 8 gio",
            category="World",
            topic_key=compute_topic_key("Tin the gioi cu"),
            published_at=now_ts - (8 * 3600),
            status="NEW",
        )
        fresh_article = NewsArticle(
            source_url="https://example.test/fresh-world",
            source_name="Test Source",
            title="Tin the gioi moi",
            summary="Tin con moi",
            category="World",
            topic_key=compute_topic_key("Tin the gioi moi"),
            published_at=now_ts - 300,
            status="NEW",
        )
        session.add_all([old_article, fresh_article])
        session.commit()

        service = threads_news_module.ThreadsNewsService()
        service.process_news_to_threads()

        session.refresh(old_article)
        session.refresh(fresh_article)
        jobs = session.query(Job).order_by(Job.id.asc()).all()

        assert len(jobs) == 1
        assert jobs[0].dedupe_key == f"threads_news_v2_{fresh_article.id}"
        assert old_article.status == "NEW"
        assert fresh_article.status == "DRAFTED"
    finally:
        session.close()


def test_process_news_to_threads_marks_duplicate_topic_as_skipped(isolated_session_factory):
    now_ts = int(time.time())
    topic_key = compute_topic_key("Trump ap thue thep Canada")
    session = isolated_session_factory()
    try:
        session.add(Account(id=1, name="threads-world", platform="threads", is_active=True))
        original_article = NewsArticle(
            source_url="https://example.test/original-world",
            source_name="Test Source",
            title="Trump áp thuế thép Canada",
            summary="Tin goc",
            category="World",
            topic_key=topic_key,
            published_at=now_ts - (5 * 3600),
            status="POSTED",
        )
        duplicate_article = NewsArticle(
            source_url="https://example.test/duplicate-world",
            source_name="Test Source",
            title="Tổng thống Trump áp thuế thép Canada",
            summary="Tin trung chu de",
            category="World",
            topic_key=topic_key,
            published_at=now_ts - 120,
            status="NEW",
        )
        session.add_all([original_article, duplicate_article])
        session.commit()
        session.add(
            Job(
                account_id=1,
                platform="threads",
                job_type="post",
                status="DONE",
                caption="existing job",
                dedupe_key=f"threads_news_v2_{original_article.id}",
                created_at=now_ts - (5 * 3600),
            )
        )
        session.commit()

        service = threads_news_module.ThreadsNewsService()
        service.process_news_to_threads()

        session.refresh(duplicate_article)
        jobs = session.query(Job).order_by(Job.id.asc()).all()

        assert len(jobs) == 1
        assert duplicate_article.status == "SKIPPED"
    finally:
        session.close()


def test_process_news_to_threads_applies_account_category_map(isolated_session_factory):
    now_ts = int(time.time())
    session = isolated_session_factory()
    try:
        session.add(Account(id=1, name="threads-world", platform="threads", is_active=True))
        session.add(
            RuntimeSetting(
                key="THREADS_ACCOUNT_CATEGORY_MAP",
                value='{"1": "world"}',
                type="text",
            )
        )
        non_world_article = NewsArticle(
            source_url="https://example.test/current-affairs",
            source_name="Test Source",
            title="Tin thoi su nong",
            summary="Tin current affairs",
            category="Current Affairs",
            topic_key=compute_topic_key("Tin thoi su nong"),
            published_at=now_ts - 60,
            status="NEW",
        )
        world_article = NewsArticle(
            source_url="https://example.test/world",
            source_name="Test Source",
            title="Tin the gioi duoc chon",
            summary="Tin world",
            category="world",
            topic_key=compute_topic_key("Tin the gioi duoc chon"),
            published_at=now_ts - 120,
            status="NEW",
        )
        session.add_all([non_world_article, world_article])
        session.commit()
        runtime_settings._cache_ts = 0.0
        runtime_settings._cache_values = {}

        service = threads_news_module.ThreadsNewsService()
        service.process_news_to_threads()

        session.refresh(non_world_article)
        session.refresh(world_article)
        jobs = session.query(Job).order_by(Job.id.asc()).all()

        assert len(jobs) == 1
        assert jobs[0].dedupe_key == f"threads_news_v2_{world_article.id}"
        assert non_world_article.status == "NEW"
        assert world_article.status == "DRAFTED"
    finally:
        session.close()
