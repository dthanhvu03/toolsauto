"""
DiscoveryScraper — Automated TikTok competitor channel discovery via hashtag search.

Uses yt-dlp headless (no browser) to:
1. Search TikTok by hashtag/keyword → get top videos
2. Extract unique channel usernames from results
3. Analyze each channel (avg views, post frequency) using existing TikTokScraper
4. Score and save promising channels to discovered_channels table

Score formula: score = avg_views * post_frequency_per_week / 1000
Only channels with score >= SCORE_THRESHOLD are saved.
"""
import json
import logging
import subprocess
import time
from urllib.parse import quote

from app.services.yt_dlp_path import yt_dlp_binary
from app.constants import ViralStatus


logger = logging.getLogger(__name__)

SCORE_THRESHOLD = 50
ANALYSIS_VIDEO_COUNT = 10


class DiscoveryScraper:

    def search_hashtag(self, keyword: str, max_results: int = 20) -> list[dict]:
        """Search TikTok by hashtag, return list of videos with uploader info.

        Uses yt-dlp --flat-playlist on /tag/{keyword} endpoint.
        """
        tag = keyword.strip().replace(" ", "").lower()
        url = f"https://www.tiktok.com/tag/{quote(tag)}"

        cmd = [
            yt_dlp_binary(),
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(max_results),
            "--no-warnings",
            url,
        ]

        logger.info("[DISCOVERY] Searching hashtag '%s' → %s (max %d)", keyword, url, max_results)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        except subprocess.TimeoutExpired:
            logger.error("[DISCOVERY] yt-dlp timeout for hashtag: %s", keyword)
            return []

        if result.returncode != 0:
            stderr = result.stderr or ""
            if "429" in stderr or "rate limit" in stderr.lower():
                logger.warning("[DISCOVERY] Rate limited on hashtag '%s'", keyword)
            else:
                logger.error("[DISCOVERY] yt-dlp error for hashtag '%s': %s", keyword, stderr[:200])
            return []

        videos = []
        for line in (result.stdout or "").strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                uploader_id = data.get("uploader_id") or data.get("channel_id") or ""
                uploader = data.get("uploader") or data.get("channel") or uploader_id
                view_count = data.get("view_count") or 0

                if not uploader_id:
                    continue

                channel_url = f"https://www.tiktok.com/@{uploader_id}"
                videos.append({
                    "channel_url": channel_url,
                    "channel_name": uploader,
                    "uploader_id": uploader_id,
                    "video_url": data.get("url") or data.get("webpage_url") or "",
                    "view_count": int(view_count) if view_count else 0,
                })
            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.debug("[DISCOVERY] Skip malformed line: %s", str(e)[:100])
                continue

        logger.info("[DISCOVERY] Hashtag '%s': found %d video results", keyword, len(videos))
        return videos

    def extract_unique_channels(self, videos: list[dict]) -> list[dict]:
        """Deduplicate videos by channel, keep best view_count as sample."""
        channels: dict[str, dict] = {}
        for v in videos:
            url = v["channel_url"]
            if url not in channels or v["view_count"] > channels[url].get("best_view", 0):
                channels[url] = {
                    "channel_url": url,
                    "channel_name": v["channel_name"],
                    "uploader_id": v["uploader_id"],
                    "best_view": v["view_count"],
                }
        return list(channels.values())

    def analyze_channel(self, channel_url: str, max_videos: int = ANALYSIS_VIDEO_COUNT) -> dict | None:
        """Analyze a TikTok channel: avg views, post frequency, video count.

        Returns dict with stats or None if channel can't be analyzed.
        """
        from app.services.tiktok_scraper import TikTokScraper

        scraper = TikTokScraper()
        videos = scraper.scrape_channel(channel_url, max_videos=max_videos, min_views=0)

        if not videos:
            return None

        view_counts = [v.get("view_count", 0) for v in videos]
        avg_views = sum(view_counts) // len(view_counts) if view_counts else 0
        video_count = len(videos)

        # Estimate post frequency (videos per week) based on sample size
        # yt-dlp returns most recent videos; assume they span ~2-4 weeks
        estimated_weeks = max(1, video_count / 3)
        post_frequency = round(video_count / estimated_weeks, 2)

        score = round(avg_views * post_frequency / 1000, 2)

        return {
            "avg_views": avg_views,
            "video_count": video_count,
            "post_frequency": post_frequency,
            "score": score,
        }

    def discover_for_keyword(self, keyword: str, account_id: int, db) -> int:
        """Full pipeline: search hashtag → extract channels → analyze → save to DB.

        Returns number of new channels saved.
        """
        from app.database.models import DiscoveredChannel

        videos = self.search_hashtag(keyword, max_results=20)
        if not videos:
            return 0

        channels = self.extract_unique_channels(videos)
        logger.info("[DISCOVERY] Keyword '%s': %d unique channels to analyze", keyword, len(channels))

        saved = 0
        for ch in channels:
            # Skip if already discovered for this account
            existing = db.query(DiscoveredChannel).filter(
                DiscoveredChannel.channel_url == ch["channel_url"],
                DiscoveredChannel.account_id == account_id,
            ).first()
            if existing:
                continue

            stats = self.analyze_channel(ch["channel_url"])
            if not stats:
                logger.debug("[DISCOVERY] Could not analyze channel %s, skipping", ch["channel_url"])
                continue

            if stats["score"] < SCORE_THRESHOLD:
                logger.debug("[DISCOVERY] Channel %s score %.1f < %d, skipping",
                             ch["channel_url"], stats["score"], SCORE_THRESHOLD)
                continue

            record = DiscoveredChannel(
                account_id=account_id,
                channel_url=ch["channel_url"],
                channel_name=ch["channel_name"],
                keyword_used=keyword,
                avg_views=stats["avg_views"],
                video_count=stats["video_count"],
                post_frequency=stats["post_frequency"],
                score=stats["score"],
                status=ViralStatus.NEW,
            )
            db.add(record)
            saved += 1
            logger.info("[DISCOVERY] Saved channel '%s' (score=%.1f) for account %d",
                        ch["channel_name"], stats["score"], account_id)

        if saved:
            db.commit()

        return saved
