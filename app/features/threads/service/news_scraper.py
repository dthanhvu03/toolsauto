from email.utils import parsedate_to_datetime
import logging
import re
import time
from collections import Counter
from typing import Dict, List
import xml.etree.ElementTree as ET

import requests

from app.core.database.core import SessionLocal
from app.core.database.models import NewsArticle
from app.features.threads.service.article_scorer import compute_score
from app.features.threads.service.topic_key import compute_topic_key
from app.services import settings as runtime_settings

logger = logging.getLogger("app.services.news_scraper")

RSS_SOURCES = [
    {"name": "VnExpress", "url": "https://vnexpress.net/rss/tin-moi-nhat.rss", "category": "General"},
    {"name": "VnExpress", "url": "https://vnexpress.net/rss/the-gioi.rss", "category": "World"},
    {"name": "VnExpress", "url": "https://vnexpress.net/rss/thoi-su.rss", "category": "Current Affairs"},
    {"name": "Tuổi Trẻ", "url": "https://tuoitre.vn/rss/tin-moi-nhat.rss", "category": "General"},
    {"name": "Tuổi Trẻ", "url": "https://tuoitre.vn/rss/the-gioi.rss", "category": "World"},
    {"name": "Thanh Niên", "url": "https://thanhnien.vn/rss/the-gioi.rss", "category": "World"},
    {"name": "Dân Trí", "url": "https://dantri.com.vn/rss/the-gioi.rss", "category": "World"},
    {"name": "Vietnamnet", "url": "https://vietnamnet.vn/rss/the-gioi.rss", "category": "World"},
    {"name": "24h", "url": "https://cdn.24h.com.vn/upload/rss/thegioi.rss", "category": "World"},
]


class NewsScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }

    def fetch_rss(self, url: str) -> List[Dict]:
        """Fetch and parse RSS feed."""
        try:
            response = requests.get(url, headers=self.headers, timeout=20)
            response.raise_for_status()

            root = ET.fromstring(response.content)
            items = []
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                link = item.find("link").text if item.find("link") is not None else ""
                description = item.find("description").text if item.find("description") is not None else ""
                pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""

                image_url = ""
                clean_summary = description
                if description and "<img" in description:
                    try:
                        match = re.search(r'src="([^"]+)"', description)
                        if match:
                            image_url = match.group(1)
                        clean_summary = re.sub(r"<[^>]*>", "", description).strip()
                    except Exception:
                        pass
                else:
                    clean_summary = re.sub(r"<[^>]*>", "", description).strip()

                items.append(
                    {
                        "title": title.strip(),
                        "link": link.strip(),
                        "summary": clean_summary,
                        "pub_date": pub_date,
                        "image_url": image_url,
                    }
                )
            return items
        except Exception as e:
            logger.error(f"Error fetching RSS {url}: {e}")
            return []

    def scrape_all(self):
        """Scrape all sources and save to DB."""
        db = SessionLocal()
        new_count = 0
        try:
            source_weights = runtime_settings.get_json(
                "THREADS_SOURCE_WEIGHTS", default={}, db=db
            ) or {}

            for source in RSS_SOURCES:
                logger.info(f"Scraping {source['name']} - {source['category']}...")
                items = self.fetch_rss(source["url"])

                for item in items:
                    try:
                        exists = (
                            db.query(NewsArticle)
                            .filter(NewsArticle.source_url == item["link"])
                            .first()
                        )
                        if exists:
                            continue

                        pub_ts = int(time.time())
                        try:
                            dt = parsedate_to_datetime(item["pub_date"])
                            pub_ts = int(dt.timestamp())
                        except Exception:
                            pass

                        article = NewsArticle(
                            source_url=item["link"],
                            source_name=source["name"],
                            title=item["title"],
                            summary=item["summary"],
                            category=source["category"],
                            topic_key=compute_topic_key(item["title"]),
                            image_url=item["image_url"],
                            published_at=pub_ts,
                            status="NEW",
                        )
                        db.add(article)
                        db.commit()
                        new_count += 1
                    except Exception as e:
                        db.rollback()
                        if "unique constraint" not in str(e).lower():
                            logger.error(f"Error adding article {item['link']}: {e}")

            # PLAN-034 — recompute engagement_score for all NEW articles within
            # the active window (24h) so topic-competition counts reflect any
            # batch we just added.
            self._rescore_recent_articles(db, source_weights)

            logger.info(f"Finished scraping. Added {new_count} new articles.")
        except Exception as e:
            logger.error(f"Error in scrape_all: {e}")
        finally:
            db.close()
        return new_count

    def _rescore_recent_articles(self, db, source_weights: dict) -> None:
        """Compute engagement_score for NEW articles published within the last 24h."""
        now_ts = int(time.time())
        window_start = now_ts - 24 * 3600
        articles = (
            db.query(NewsArticle)
            .filter(
                NewsArticle.status == "NEW",
                NewsArticle.published_at.isnot(None),
                NewsArticle.published_at >= window_start,
            )
            .all()
        )
        if not articles:
            return

        topic_counts = Counter(a.topic_key for a in articles if a.topic_key)
        for article in articles:
            try:
                article.engagement_score = compute_score(
                    article,
                    all_topic_counts=topic_counts,
                    source_weights=source_weights,
                    now_ts=now_ts,
                )
            except Exception as exc:
                logger.warning("Failed to score article %s: %s", article.id, exc)
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Failed to persist engagement_score batch: %s", exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = NewsScraper()
    scraper.scrape_all()
