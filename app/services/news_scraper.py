import requests
import xml.etree.ElementTree as ET
import time
import logging
from typing import List, Dict
from app.database.core import SessionLocal
from app.database.models import NewsArticle

logger = logging.getLogger("app.services.news_scraper")

RSS_SOURCES = [
    {"name": "VnExpress", "url": "https://vnexpress.net/rss/tin-moi-nhat.rss", "category": "General"},
    {"name": "VnExpress", "url": "https://vnexpress.net/rss/the-gioi.rss", "category": "World"},
    {"name": "VnExpress", "url": "https://vnexpress.net/rss/thoi-su.rss", "category": "Current Affairs"},
    {"name": "Tuổi Trẻ", "url": "https://tuoitre.vn/rss/tin-moi-nhat.rss", "category": "General"},
]

class NewsScraper:
    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
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
                
                # Simple extraction of image from description if needed (CDATAs often have <img>)
                image_url = ""
                clean_summary = description
                if description and "<img" in description:
                    try:
                        import re
                        match = re.search(r'src="([^"]+)"', description)
                        if match:
                            image_url = match.group(1)
                        
                        # Strip all HTML tags for the clean summary
                        clean_summary = re.sub(r'<[^>]*>', '', description).strip()
                    except:
                        pass
                else:
                    # Even if no img, still strip tags just in case
                    import re
                    clean_summary = re.sub(r'<[^>]*>', '', description).strip()
                
                items.append({
                    "title": title.strip(),
                    "link": link.strip(),
                    "summary": clean_summary,
                    "pub_date": pub_date,
                    "image_url": image_url
                })
            return items

        except Exception as e:
            logger.error(f"Error fetching RSS {url}: {e}")
            return []

    def scrape_all(self):
        """Scrape all sources and save to DB."""
        db = SessionLocal()
        new_count = 0
        try:
            for source in RSS_SOURCES:
                logger.info(f"Scraping {source['name']} - {source['category']}...")
                items = self.fetch_rss(source['url'])
                
                for item in items:
                    try:
                        # Check if exists (using sub-session or just checking)
                        exists = db.query(NewsArticle).filter(NewsArticle.source_url == item['link']).first()
                        if exists:
                            continue
                        
                        # Convert pub_date to unix ts if possible
                        pub_ts = int(time.time())
                        try:
                            from email.utils import parsedate_to_datetime
                            dt = parsedate_to_datetime(item['pub_date'])
                            pub_ts = int(dt.timestamp())
                        except:
                            pass
                            
                        article = NewsArticle(
                            source_url=item['link'],
                            source_name=source['name'],
                            title=item['title'],
                            summary=item['summary'],
                            category=source['category'],
                            image_url=item['image_url'],
                            published_at=pub_ts,
                            status="NEW"
                        )
                        db.add(article)
                        db.commit() # Commit per article
                        new_count += 1
                    except Exception as e:
                        db.rollback()
                        if "unique constraint" not in str(e).lower():
                            logger.error(f"Error adding article {item['link']}: {e}")
            
            logger.info(f"Finished scraping. Added {new_count} new articles.")
        except Exception as e:
            logger.error(f"Error in scrape_all: {e}")
        finally:
            db.close()
        return new_count


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scraper = NewsScraper()
    scraper.scrape_all()
