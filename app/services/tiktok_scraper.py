"""
TikTokScraper — Headless TikTok channel scraper using yt-dlp metadata.

Không cần browser, không cần login. Dùng `yt-dlp --flat-playlist --dump-json`
để quét kênh TikTok đối thủ và lấy danh sách video + view count.

Usage:
    scraper = TikTokScraper()
    videos = scraper.scrape_channel("https://tiktok.com/@username", max_videos=10)
    # => [{"url": "...", "title": "...", "view_count": 12345}, ...]
"""
import json
import logging
import subprocess
import time

from app.services.yt_dlp_path import yt_dlp_binary

logger = logging.getLogger(__name__)

# Rate limit tracker persisted to disk (survives worker restart)
_RATE_LIMIT_FILE = "/tmp/tiktok_rate_limits.json"
RATE_LIMIT_BACKOFF_HOURS = 3


def _load_rate_limits() -> dict[str, float]:
    """Load rate limit state from disk."""
    try:
        with open(_RATE_LIMIT_FILE, "r") as f:
            data = json.load(f)
            # Cleanup expired entries
            now = time.time()
            return {k: v for k, v in data.items() if v > now}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_rate_limits(tracker: dict[str, float]):
    """Persist rate limit state to disk."""
    try:
        with open(_RATE_LIMIT_FILE, "w") as f:
            json.dump(tracker, f)
    except Exception:
        pass


class TikTokScraper:
    """Quét kênh TikTok đối thủ bằng yt-dlp metadata (headless, không browser)."""

    def scrape_channel(
        self,
        channel_url: str,
        max_videos: int = 10,
        min_views: int = 10000,
    ) -> list[dict]:
        """
        Quét kênh TikTok, trả về danh sách video viral.

        Args:
            channel_url: URL kênh TikTok (e.g. https://tiktok.com/@username)
            max_videos: Số video tối đa quét metadata (giới hạn request)
            min_views: Ngưỡng view tối thiểu để coi là "viral"

        Returns:
            List of dicts: {"url": str, "title": str, "view_count": int}
        """
        # Check rate limit (persisted to disk)
        now = time.time()
        tracker = _load_rate_limits()
        next_allowed = tracker.get(channel_url, 0)
        if now < next_allowed:
            remaining_min = int((next_allowed - now) / 60)
            logger.info(
                "[TIKTOK] Channel '%s' đang bị rate limit. Retry sau %d phút.",
                channel_url, remaining_min
            )
            return []

        cmd = [
            yt_dlp_binary(),
            "--flat-playlist",
            "--dump-json",
            "--playlist-end", str(max_videos),
            "--no-warnings",
            channel_url,
        ]

        logger.info("[TIKTOK] Scraping channel: %s (max=%d videos)", channel_url, max_videos)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            logger.error("[TIKTOK] yt-dlp timeout for channel: %s", channel_url)
            return []

        # Check rate limit từ stderr
        stderr = result.stderr or ""
        if result.returncode != 0:
            if "429" in stderr or "rate limit" in stderr.lower() or "too many" in stderr.lower():
                backoff_until = now + (RATE_LIMIT_BACKOFF_HOURS * 3600)
                tracker[channel_url] = backoff_until
                _save_rate_limits(tracker)
                logger.warning(
                    "[TIKTOK] Rate limited on '%s'. Backing off %d hours.",
                    channel_url, RATE_LIMIT_BACKOFF_HOURS
                )
            else:
                logger.error("[TIKTOK] yt-dlp error for '%s': %s", channel_url, stderr[:200])
            return []

        # Parse JSON lines (mỗi dòng = 1 video)
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                view_count = data.get("view_count")
                url = data.get("url") or data.get("webpage_url") or data.get("original_url")
                title = data.get("title", "")

                if not url:
                    continue

                # Đảm bảo URL đầy đủ
                if not url.startswith("http"):
                    url = f"https://www.tiktok.com/@{data.get('uploader_id', 'unknown')}/video/{data.get('id', '')}"

                entry = {
                    "url": url,
                    "title": title[:200] if title else "",
                    "view_count": int(view_count) if view_count is not None else 0,
                }

                # Nếu view_count có data → filter theo ngưỡng
                # Nếu view_count null/0 → vẫn lấy (fallback cho trường hợp TikTok không trả view)
                if view_count is not None and view_count < min_views:
                    continue

                videos.append(entry)

            except (json.JSONDecodeError, ValueError, TypeError) as e:
                logger.debug("[TIKTOK] Skip malformed line: %s", str(e)[:100])
                continue

        logger.info(
            "[TIKTOK] Channel '%s': found %d/%d videos above %d views.",
            channel_url, len(videos), max_videos, min_views
        )
        return videos
