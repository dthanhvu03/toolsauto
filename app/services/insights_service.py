from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import Optional
import datetime
import time as _time
import subprocess
import sys
import os
import logging

logger = logging.getLogger(__name__)

from app.database.core import get_db
from app.database import models
from app.main_templates import templates
from app import config

router = APIRouter(prefix="/insights", tags=["Insights"])

# ---------------------------------------------------------------------------
# Simple TTL cache (Phase P2)
# ---------------------------------------------------------------------------
_cache: dict = {}
CACHE_TTL = 3600  # 1 hour

def _get_cached(key: str):
    if key in _cache:
        data, ts = _cache[key]
        if _time.time() - ts < CACHE_TTL:
            return data
    return None

def _set_cached(key: str, data):
    _cache[key] = (data, _time.time())

def _validate_days(days: int) -> int:
    """Ensure days is one of the allowed values."""
    return days if days in (7, 30, 90) else 7


# ── Page route (HTML) ─────────────────────────────────────────────────────
def view_insights_dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the main insights dashboard HTML page."""
    pages = db.query(models.PageInsight.page_url, models.PageInsight.page_name).distinct().all()
    page_options = [{"url": p.page_url, "name": p.page_name or p.page_url} for p in pages]

    return templates.TemplateResponse(
        "pages/insights.html",
        {
            "request": request,
            "pages": page_options,
            "title": "Page Insights Dashboard"
        }
    )


# ── /api/growth ───────────────────────────────────────────────────────────
def get_growth_metrics(
    page_url: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db)
):
    """
    Get hourly/daily view growth for a specific page or all pages.
    Aggregates only the LATEST view count per unique post within each group.
    """
    from sqlalchemy import text

    days = _validate_days(days)
    now = int(datetime.datetime.now().timestamp())
    cutoff = now - (days * 86400)
    time_format = "YYYY-MM-DD HH24:00" if days == 7 else "YYYY-MM-DD"

    sql = f"""
    WITH LatestPerGroup AS (
        SELECT
            TO_CHAR(TO_TIMESTAMP(recorded_at), '{time_format}') as time_label,
            post_url,
            platform,
            page_url,
            MAX(views) as latest_views,
            MAX(likes) as latest_likes
        FROM page_insights
        WHERE recorded_at >= :cutoff
        GROUP BY time_label, post_url
    )
    SELECT
        time_label,
        SUM(latest_views) as total_views,
        SUM(latest_likes) as total_likes
    FROM LatestPerGroup
    WHERE 1=1
    """

    if page_url:
        sql += " AND page_url = :page_url"
    if platform:
        sql += " AND platform = :platform"

    sql += " GROUP BY time_label ORDER BY time_label"

    params = {"cutoff": cutoff, "page_url": page_url, "platform": platform}
    results = db.execute(text(sql), params).fetchall()

    data = []
    for r in results:
        data.append({
            "date": r.time_label,
            "views": r.total_views or 0,
            "likes": r.total_likes or 0,
        })

    return {"status": "success", "data": data}


# ── /api/top-posts (with pagination) ─────────────────────────────────────
def get_top_posts(
    page_url: Optional[str] = None,
    platform: Optional[str] = "facebook",
    days: int = 7,
    page: int = 1,
    limit: int = 15,
    sort_by: Optional[str] = "views",
    db: Session = Depends(get_db)
):
    """
    Get high-performing posts with advanced decision metrics.
    Calculates Engagement Rate and 24h Velocity using window functions.
    Supports pagination via page/limit params.
    """
    from sqlalchemy import text

    days = _validate_days(days)
    if page < 1:
        page = 1
    if limit < 1 or limit > 100:
        limit = 15
    offset = (page - 1) * limit

    # Whitelist sort columns to prevent SQL injection
    _sort_map = {"views": "l1.views", "likes": "l1.likes", "comments": "l1.comments",
                 "shares": "l1.shares", "date": "l1.published_date", "eng_rate": "eng_rate"}
    order_col = _sort_map.get(sort_by or "views", "l1.views")

    now = int(datetime.datetime.now().timestamp())
    cutoff = now - (days * 86400)

    # --- count total ---
    count_sql = """
    WITH RankedInsights AS (
        SELECT
            post_url,
            REPLACE(REPLACE(RTRIM(LOWER(post_url), '/'), 'web.facebook.com', 'www.facebook.com'), '/reels/', '/reel/') as canonical_url,
            ROW_NUMBER() OVER (PARTITION BY 
                REPLACE(REPLACE(RTRIM(LOWER(post_url), '/'), 'web.facebook.com', 'www.facebook.com'), '/reels/', '/reel/')
                ORDER BY recorded_at DESC
            ) as rn
        FROM page_insights
        WHERE recorded_at >= :cutoff
          AND (:platform IS NULL OR platform = :platform)
          AND (:page_url IS NULL OR page_url = :page_url)
    )
    SELECT COUNT(*) as cnt FROM RankedInsights WHERE rn = 1
    """
    total = db.execute(
        text(count_sql),
        {"cutoff": cutoff, "platform": platform, "page_url": page_url},
    ).scalar() or 0

    # --- paginated data ---
    sql = f"""
    WITH RankedInsights AS (
        SELECT
            post_url, page_name, platform, views, likes, comments, shares, caption,
            published_date, recorded_at,
            ROW_NUMBER() OVER (PARTITION BY 
                REPLACE(REPLACE(RTRIM(LOWER(post_url), '/'), 'web.facebook.com', 'www.facebook.com'), '/reels/', '/reel/')
                ORDER BY recorded_at DESC
            ) as rn
        FROM page_insights
        WHERE recorded_at >= :cutoff
          AND (:platform IS NULL OR platform = :platform)
          AND (:page_url IS NULL OR page_url = :page_url)
    )
    SELECT
        l1.post_url, l1.page_name, l1.platform, l1.views, l1.likes, l1.comments, l1.shares,
        l1.caption, l1.published_date,
        (l1.views - COALESCE(l2.views, 0)) as velocity,
        CASE WHEN l1.views > 0 THEN (CAST(l1.likes AS FLOAT) / l1.views) * 100 ELSE 0 END as eng_rate
    FROM RankedInsights l1
    LEFT JOIN RankedInsights l2 ON 
        REPLACE(REPLACE(RTRIM(LOWER(l1.post_url), '/'), 'web.facebook.com', 'www.facebook.com'), '/reels/', '/reel/') = 
        REPLACE(REPLACE(RTRIM(LOWER(l2.post_url), '/'), 'web.facebook.com', 'www.facebook.com'), '/reels/', '/reel/')
        AND l2.rn = 2
    WHERE l1.rn = 1
    ORDER BY {order_col} DESC NULLS LAST
    LIMIT :limit OFFSET :offset
    """

    params = {
        "cutoff": cutoff,
        "platform": platform,
        "page_url": page_url,
        "limit": limit,
        "offset": offset,
    }

    results = db.execute(text(sql), params).fetchall()

    data = []
    for r in results:
        data.append({
            "post_url": r.post_url,
            "page_name": r.page_name,
            "platform": r.platform,
            "views": r.views or 0,
            "likes": r.likes or 0,
            "comments": r.comments or 0,
            "shares": r.shares or 0,
            "caption": r.caption or "",
            "published_date": r.published_date or "",
            "velocity": r.velocity or 0,
            "engagement_rate": round(r.eng_rate or 0, 2),
        })

    total_pages = max(1, (total + limit - 1) // limit)
    return {
        "status": "success",
        "data": data,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


# ── /api/page-analysis ───────────────────────────────────────────────────
def get_page_analysis(platform: str = None, db: Session = Depends(get_db)):
    """
    Strategic Analysis: Categorize pages based on growth momentum and engagement.
    Uses the centralized PageStrategicService with platform filtering.
    """
    from app.services.strategic import PageStrategicService
    analysis = PageStrategicService.get_page_analysis(db, platform=platform)
    return {"status": "success", "data": analysis}


# ── /api/platform-stats  (merged, cached) ────────────────────────────────
def get_platform_stats(
    page_url: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    """Get view and post distribution per platform (cached 1 h)."""
    from sqlalchemy import text

    days = _validate_days(days)
    cache_key = f"platform_stats_{days}_{page_url or 'all'}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    now = int(datetime.datetime.now().timestamp())
    cutoff = now - (days * 86400)

    sql = """
        SELECT platform,
               SUM(views) as total_views,
               COUNT(DISTINCT post_url) as post_count
        FROM page_insights
        WHERE recorded_at >= :cutoff
          AND (:page_url IS NULL OR page_url = :page_url)
        GROUP BY platform
    """
    results = db.execute(text(sql), {"page_url": page_url, "cutoff": cutoff}).fetchall()
    data = [
        {"platform": r.platform or "unknown", "views": r.total_views or 0, "posts": r.post_count}
        for r in results
    ]
    result = {"status": "success", "data": data}
    _set_cached(cache_key, result)
    return result


# ── /api/engagement-heatmap  (merged, cached) ────────────────────────────
def get_engagement_heatmap(
    page_url: Optional[str] = None,
    platform: Optional[str] = "facebook",
    days: int = 7,
    db: Session = Depends(get_db),
):
    """Get interaction density by Day-of-Week × Hour (cached 1 h)."""
    from sqlalchemy import text

    days = _validate_days(days)
    cache_key = f"heatmap_{days}_{platform or 'all'}_{page_url or 'all'}"
    cached = _get_cached(cache_key)
    if cached:
        return cached

    now = int(datetime.datetime.now().timestamp())
    cutoff = now - (days * 86400)

    # Merged: COALESCE from version-A for NULL safety,
    #         'localtime' from version-B for correct timezone,
    #         dow/hour NULL guard from version-B.
    sql = """
    SELECT
        CAST(EXTRACT(DOW FROM TO_TIMESTAMP(recorded_at)) AS INTEGER) as dow,
        CAST(EXTRACT(HOUR FROM TO_TIMESTAMP(recorded_at)) AS INTEGER) as hour,
        SUM(COALESCE(likes, 0) + COALESCE(comments, 0) + COALESCE(shares, 0)) as total_interactions
    FROM page_insights
    WHERE recorded_at >= :cutoff
      AND (:platform IS NULL OR platform = :platform)
      AND (:page_url IS NULL OR page_url = :page_url)
    GROUP BY dow, hour
    """
    results = db.execute(
        text(sql), {"cutoff": cutoff, "platform": platform, "page_url": page_url}
    ).fetchall()

    grid = [[0 for _ in range(24)] for _ in range(7)]
    for r in results:
        dow, hour, interactions = r[0], r[1], r[2]
        if dow is not None and hour is not None:
            grid[dow][hour] = int(interactions or 0)

    result = {"status": "success", "data": grid}
    _set_cached(cache_key, result)
    return result


# ── /api/secondary-metrics  (merged) ─────────────────────────────────────
def get_secondary_metrics(
    page_url: Optional[str] = None,
    platform: Optional[str] = "facebook",
    days: int = 7,
    db: Session = Depends(get_db),
):
    """Secondary performance KPIs — avg views, shares, engagement rate."""
    from sqlalchemy import text

    days = _validate_days(days)
    now = int(datetime.datetime.now().timestamp())
    cutoff = now - (days * 86400)

    # Merged: SQL-side engagement calc from version-B,
    #         safe AVG + explicit NULL handling from version-A.
    sql = """
    SELECT
        AVG(views)              as avg_views,
        SUM(shares)             as total_shares,
        CASE WHEN SUM(views) > 0
             THEN SUM(COALESCE(likes,0)) * 100.0 / SUM(views)
             ELSE 0 END         as eng_rate,
        COUNT(DISTINCT post_url) as active_posts
    FROM page_insights
    WHERE recorded_at >= :cutoff
      AND (:platform IS NULL OR platform = :platform)
      AND (:page_url IS NULL OR page_url = :page_url)
    """
    params = {"cutoff": cutoff, "platform": platform, "page_url": page_url}
    result = db.execute(text(sql), params).fetchone()

    data = {
        "avg_views": round(result[0] or 0, 1) if result else 0,
        "total_shares": result[1] or 0 if result else 0,
        "engagement_rate": round(result[2] or 0, 2) if result else 0,
        "posts_count": result[3] or 0 if result else 0,
    }
    return {"status": "success", "data": data}


# ── /api/ai-commentary  (9router powered strategic analysis) ─────────────
COMMENTARY_CACHE_TTL = 1800  # 30 min — AI calls are slow & expensive

def get_ai_commentary(
    page_url: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    """
    Generate real-time AI strategic commentary using 9router.
    Feeds actual DB metrics into the LLM and returns plain-text analysis.
    Cached 30 min per (page_url, platform, days) combination.
    """
    from sqlalchemy import text as _text
    from app.services.ai_runtime import pipeline

    days = _validate_days(days)
    cache_key = f"ai_commentary_{days}_{platform or 'all'}_{page_url or 'all'}"
    cached = _get_cached(cache_key)
    if cached:
        return {**cached, "cached": True}

    now = int(_time.time())
    cutoff = now - (days * 86400)
    params_base = {"cutoff": cutoff, "platform": platform, "page_url": page_url}

    # Top pages by total views
    top_pages = db.execute(_text("""
        WITH ranked AS (
            SELECT page_name, page_url, post_url, platform,
                   MAX(views) as views, MAX(likes) as likes
            FROM page_insights
            WHERE recorded_at >= :cutoff
              AND (:platform IS NULL OR platform = :platform)
              AND (:page_url IS NULL OR page_url = :page_url)
            GROUP BY page_url, post_url
        )
        SELECT page_name, page_url, SUM(views) as total_views,
               SUM(likes) as total_likes, COUNT(DISTINCT post_url) as post_count
        FROM ranked
        GROUP BY page_url
        ORDER BY total_views DESC LIMIT 5
    """), params_base).fetchall()

    # Best performing single post
    top_post = db.execute(_text("""
        SELECT page_name, caption, MAX(views) as views
        FROM page_insights
        WHERE recorded_at >= :cutoff
          AND (:platform IS NULL OR platform = :platform)
          AND (:page_url IS NULL OR page_url = :page_url)
        GROUP BY post_url ORDER BY views DESC LIMIT 1
    """), params_base).fetchone()

    # Aggregate metrics
    agg = db.execute(_text("""
        SELECT AVG(views) as avg_views,
               CASE WHEN SUM(views) > 0
                    THEN SUM(COALESCE(likes,0)) * 100.0 / SUM(views) ELSE 0 END as eng_rate,
               COUNT(DISTINCT post_url) as active_posts,
               COUNT(DISTINCT platform) as platform_count
        FROM page_insights
        WHERE recorded_at >= :cutoff
          AND (:platform IS NULL OR platform = :platform)
          AND (:page_url IS NULL OR page_url = :page_url)
    """), params_base).fetchone()

    # Build data context
    avg_views = round(agg[0] or 0) if agg else 0
    eng_rate = round(agg[1] or 0, 2) if agg else 0
    active_posts = agg[2] or 0 if agg else 0

    pages_lines = "\n".join(
        f"  • {r[0] or r[1]}: {r[2]:,} views, {r[3]:,} likes, {r[4]} bài"
        for r in top_pages
    ) if top_pages else "  Chưa có dữ liệu."

    top_post_line = ""
    if top_post:
        cap = (top_post[1] or "")[:80] or "(không có caption)"
        top_post_line = f"{top_post[0]} — {top_post[2]:,} views — \"{cap}\""

    platform_ctx = platform.upper() if platform else "tất cả nền tảng"

    prompt = f"""Bạn là chuyên gia phân tích social media. Viết 1 đoạn nhận xét chiến lược (2-3 câu, tiếng Việt, tự nhiên, không dùng bullet point, không JSON):

Dữ liệu thực tế {days} ngày — {platform_ctx}:
{pages_lines}
Bài tốt nhất: {top_post_line or 'Chưa có'}
Avg views/bài: {avg_views:,} | Engagement rate: {eng_rate}% | Tổng bài tracking: {active_posts}

Nhận xét chiến lược ngắn gọn (plain text):"""

    text, meta = pipeline.generate_text(prompt)

    if not text:
        fallback = (
            f"Đang theo dõi {active_posts} bài trên {platform_ctx}. "
            f"Avg {avg_views:,} views/bài, engagement rate {eng_rate}%. "
            f"9router chưa phản hồi — vui lòng kiểm tra kết nối."
        )
        return {
            "status": "fallback",
            "commentary": fallback,
            "model": meta.get("fail_reason", "N/A"),
            "cached": False,
        }

    result = {
        "status": "success",
        "commentary": text.strip(),
        "model": meta.get("model", "N/A"),
        "latency_ms": meta.get("latency_ms", 0),
        "cached": False,
    }
    _set_cached(cache_key, result)
    return result


# ── /api/ai-roadmap  (9router powered strategic roadmap) ─────────────────
def get_ai_roadmap(
    page_url: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    """
    Generate a 4-step strategic growth roadmap using 9router.
    Builds context from real DB metrics, asks the LLM to return structured JSON.
    Cached 30 min per (page_url, platform, days) combination.
    """
    import json
    import re as _re
    from sqlalchemy import text as _text
    from app.services.ai_runtime import pipeline

    days = _validate_days(days)
    cache_key = f"ai_roadmap_{days}_{platform or 'all'}_{page_url or 'all'}"
    cached = _get_cached(cache_key)
    if cached:
        return {**cached, "cached": True}

    now = int(_time.time())
    cutoff = now - (days * 86400)
    params_base = {"cutoff": cutoff, "platform": platform, "page_url": page_url}

    # Top pages by views
    top_pages = db.execute(_text("""
        WITH ranked AS (
            SELECT page_name, post_url,
                   MAX(views) as views, MAX(likes) as likes
            FROM page_insights
            WHERE recorded_at >= :cutoff
              AND (:platform IS NULL OR platform = :platform)
              AND (:page_url IS NULL OR page_url = :page_url)
            GROUP BY page_url, post_url
        )
        SELECT page_name, SUM(views) as total_views,
               SUM(likes) as total_likes, COUNT(DISTINCT post_url) as post_count
        FROM ranked GROUP BY page_name ORDER BY total_views DESC LIMIT 5
    """), params_base).fetchall()

    # Aggregate metrics
    agg = db.execute(_text("""
        SELECT AVG(views) as avg_views,
               CASE WHEN SUM(views) > 0
                    THEN SUM(COALESCE(likes,0)) * 100.0 / SUM(views) ELSE 0 END as eng_rate,
               COUNT(DISTINCT post_url) as active_posts
        FROM page_insights
        WHERE recorded_at >= :cutoff
          AND (:platform IS NULL OR platform = :platform)
          AND (:page_url IS NULL OR page_url = :page_url)
    """), params_base).fetchone()

    avg_views = round(agg[0] or 0) if agg else 0
    eng_rate = round(agg[1] or 0, 2) if agg else 0
    active_posts = agg[2] or 0 if agg else 0
    platform_ctx = platform.upper() if platform else "tất cả nền tảng"

    pages_lines = "\n".join(
        f"  • {r[0]}: {r[1]:,} views, {r[2]:,} likes, {r[3]} bài"
        for r in top_pages
    ) if top_pages else "  Chưa có dữ liệu."

    prompt = f"""Bạn là chiến lược gia social media. Dựa vào dữ liệu thực tế dưới đây, tạo ra 4 bước roadmap chiến lược CỤ THỂ cho các trang này.

Dữ liệu {days} ngày — {platform_ctx}:
{pages_lines}
Avg views/bài: {avg_views:,} | Engagement rate: {eng_rate}% | Tổng bài tracking: {active_posts}

Trả về JSON array (chỉ JSON thuần, không có markdown, không có text khác):
[
  {{"step": "01", "category": "Retention", "title": "...", "description": "...(1 câu cụ thể dựa vào data)", "theme": "indigo"}},
  {{"step": "02", "category": "Scale", "title": "...", "description": "...", "theme": "emerald"}},
  {{"step": "03", "category": "Monetize", "title": "...", "description": "...", "theme": "purple"}},
  {{"step": "04", "category": "Automate", "title": "...", "description": "...", "theme": "orange"}}
]"""

    text, meta = pipeline.generate_text(prompt)

    steps = None
    if text:
        try:
            json_match = _re.search(r'\[.*?\]', text, _re.DOTALL)
            if json_match:
                steps = json.loads(json_match.group(0))
        except Exception:
            pass

    if not steps:
        # Fallback: generic steps built from real metrics
        steps = [
            {"step": "01", "category": "Retention", "title": "Tối ưu 3 giây đầu",
             "description": f"Cải thiện hook cho {active_posts} bài đang tracking để tăng retention rate.", "theme": "indigo"},
            {"step": "02", "category": "Scale", "title": "Nhân bản nội dung thành công",
             "description": f"Clone các mẫu nội dung đạt engagement rate cao nhất trên {platform_ctx}.", "theme": "emerald"},
            {"step": "03", "category": "Monetize", "title": "Kích hoạt affiliate",
             "description": f"Tích hợp affiliate cho bài có views > avg {avg_views:,} trên {platform_ctx}.", "theme": "purple"},
            {"step": "04", "category": "Automate", "title": "Lên lịch theo heatmap",
             "description": "Đặt lịch đăng theo Peak Engagement Windows để tối ưu organic reach.", "theme": "orange"},
        ]
        meta["fail_reason"] = meta.get("fail_reason", "parse_failed")

    result = {
        "status": "success",
        "steps": steps,
        "model": meta.get("model", "N/A"),
        "latency_ms": meta.get("latency_ms", 0),
        "is_fallback": not bool(text),
        "cached": False,
    }
    _set_cached(cache_key, result)
    return result


# ── /api/status  (data freshness) ────────────────────────────────────────
def get_data_status(db: Session = Depends(get_db)):
    """Return data freshness info: last scraped timestamp + total record count."""
    from sqlalchemy import text as _text

    row = db.execute(_text(
        "SELECT MAX(recorded_at) as last_ts, COUNT(*) as total FROM page_insights"
    )).fetchone()

    last_ts = row[0] if row else None
    total = row[1] if row else 0
    now = int(_time.time())

    if last_ts:
        age_sec = now - last_ts
        age_h = age_sec // 3600
        age_m = (age_sec % 3600) // 60
        if age_h >= 1:
            age_label = f"{age_h}h {age_m}m ago"
        else:
            age_label = f"{age_m}m ago"
        last_updated_iso = datetime.datetime.fromtimestamp(last_ts).strftime("%Y-%m-%d %H:%M")
    else:
        age_label = "never"
        last_updated_iso = None

    return {
        "status": "success",
        "last_updated": last_updated_iso,
        "age_label": age_label,
        "total_records": total,
        "stale": (last_ts is None) or ((now - last_ts) > 43200),  # >12h = stale
    }


# ── /api/trigger-refresh  (manual scrape trigger) ────────────────────────
_refresh_running: bool = False

def trigger_refresh():
    """Kick off the insights scraper immediately (non-blocking subprocess)."""
    global _refresh_running
    if _refresh_running:
        return JSONResponse({"status": "already_running", "message": "Scraper đang chạy, vui lòng đợi."}, status_code=429)

    scraper_path = str(config.BASE_DIR / "scripts" / "archive" / "scrape_insights.py")

    if not os.path.exists(scraper_path):
        return JSONResponse({"status": "error", "message": f"Scraper không tìm thấy: {scraper_path}"}, status_code=500)

    try:
        _refresh_running = True
        proc = subprocess.Popen(
            [sys.executable, scraper_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("Insights scraper triggered manually (pid=%s)", proc.pid)
        # Reset flag after 30 min max (safety valve)
        def _reset():
            import time as _t
            _t.sleep(1800)
            global _refresh_running
            _refresh_running = False
        import threading
        threading.Thread(target=_reset, daemon=True).start()
        return {"status": "success", "message": "Scraper đã được kích hoạt, dữ liệu sẽ cập nhật sau vài phút.", "pid": proc.pid}
    except Exception as e:
        _refresh_running = False
        logger.error("Failed to trigger scraper: %s", e)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)


# ── /api/market-benchmark  (our pages vs competitor reels) ───────────────
def get_market_benchmark(
    platform: Optional[str] = "facebook",
    days: int = 7,
    db: Session = Depends(get_db),
):
    """
    Compare our tracked pages' avg metrics vs the FB-suggested competitor reels
    harvested automatically by the scraper (GQL[5] stream).
    """
    from sqlalchemy import text

    days = _validate_days(days)
    now = int(_time.time())
    cutoff = now - (days * 86400)

    our = db.execute(text("""
        SELECT AVG(views), AVG(likes), AVG(comments), AVG(shares),
               COUNT(DISTINCT post_url), MAX(views)
        FROM page_insights
        WHERE recorded_at >= :cutoff
          AND (:platform IS NULL OR platform = :platform)
    """), {"cutoff": cutoff, "platform": platform}).fetchone()

    mkt = db.execute(text("""
        SELECT AVG(views), AVG(likes), AVG(comments), AVG(shares),
               COUNT(DISTINCT reel_url), MAX(views)
        FROM competitor_reels
        WHERE scraped_at >= :cutoff
    """), {"cutoff": cutoff}).fetchone()

    def _s(row, idx, default=0):
        v = row[idx] if row else None
        return round(v or default, 1)

    our_avg   = _s(our, 0)
    mkt_avg   = _s(mkt, 0)
    gap_ratio = round(mkt_avg / max(our_avg, 1), 1)

    return {
        "status": "success",
        "days": days,
        "our": {
            "avg_views":    our_avg,
            "avg_likes":    _s(our, 1),
            "avg_comments": _s(our, 2),
            "avg_shares":   _s(our, 3),
            "post_count":   int(our[4] or 0) if our else 0,
            "max_views":    int(our[5] or 0) if our else 0,
        },
        "market": {
            "avg_views":    mkt_avg,
            "avg_likes":    _s(mkt, 1),
            "avg_comments": _s(mkt, 2),
            "avg_shares":   _s(mkt, 3),
            "reel_count":   int(mkt[4] or 0) if mkt else 0,
            "max_views":    int(mkt[5] or 0) if mkt else 0,
        },
        "gap_ratio":          gap_ratio,
        "has_competitor_data": (int(mkt[4] or 0) if mkt else 0) > 0,
    }


# ── /api/competitor-top  (top competitor reels by metric) ────────────────
def get_competitor_top(
    days: int = 7,
    page: int = 1,
    limit: int = 20,
    sort_by: Optional[str] = "views",
    db: Session = Depends(get_db),
):
    """Top competitor reels sorted by views/likes/date — paginated."""
    from sqlalchemy import text

    days = _validate_days(days)
    _sort_map = {"views": "max_views", "likes": "max_likes",
                 "comments": "max_comments", "date": "published_date"}
    order_col = _sort_map.get(sort_by or "views", "max_views")

    if page < 1: page = 1
    if limit < 1 or limit > 100: limit = 20
    offset = (page - 1) * limit

    now = int(_time.time())
    cutoff = now - (days * 86400)

    total = db.execute(text(
        "SELECT COUNT(DISTINCT reel_url) FROM competitor_reels WHERE scraped_at >= :cutoff"
    ), {"cutoff": cutoff}).scalar() or 0

    rows = db.execute(text(f"""
        SELECT reel_url, page_name, page_url, platform,
               MAX(views)    as max_views,
               MAX(likes)    as max_likes,
               MAX(comments) as max_comments,
               MAX(shares)   as max_shares,
               caption, published_date
        FROM competitor_reels
        WHERE scraped_at >= :cutoff
        GROUP BY reel_url
        ORDER BY {order_col} DESC NULLS LAST
        LIMIT :limit OFFSET :offset
    """), {"cutoff": cutoff, "limit": limit, "offset": offset}).fetchall()

    data = [{
        "reel_url":       r[0],
        "page_name":      r[1] or "",
        "page_url":       r[2] or "",
        "platform":       r[3] or "facebook",
        "views":          int(r[4] or 0),
        "likes":          int(r[5] or 0),
        "comments":       int(r[6] or 0),
        "shares":         int(r[7] or 0),
        "caption":        r[8] or "",
        "published_date": r[9] or "",
    } for r in rows]

    return {
        "status":      "success",
        "data":        data,
        "total":       total,
        "page":        page,
        "total_pages": max(1, (total + limit - 1) // limit),
        "has_data":    total > 0,
    }


# ── /api/trending-topics  (keyword frequency from competitor captions) ────
def get_trending_topics(
    days: int = 7,
    limit: int = 25,
    db: Session = Depends(get_db),
):
    """
    Word frequency across competitor reel captions — reveals trending themes
    FB's algorithm is pushing in our niche.
    """
    import re as _re
    from sqlalchemy import text

    days = _validate_days(days)
    now = int(_time.time())
    cutoff = now - (days * 86400)

    rows = db.execute(text("""
        SELECT caption, views FROM competitor_reels
        WHERE scraped_at >= :cutoff
          AND caption IS NOT NULL AND caption != ''
        ORDER BY views DESC
        LIMIT 500
    """), {"cutoff": cutoff}).fetchall()

    STOPWORDS = {
        # Vietnamese
        'là','và','của','trong','cho','với','có','được','này','những','các','như',
        'đã','hay','thì','mà','khi','từ','về','ra','vào','lên','lại','cũng','đến',
        'để','theo','bởi','qua','vì','vậy','nếu','đây','thế','một','không','rất',
        'còn','mình','bạn','tôi','anh','chị','em','ở','nè','nha','ơi','nhé','luôn',
        'quá','nào','cái','ai','gì','sao','rồi','thôi','hơn','nhất','bao','vẫn',
        'tới','sau','trước','đó','kia','đây','đâu','đều','lắm','được','bị','hết',
        # English
        'the','a','an','is','are','was','be','to','of','in','on','at','for','with',
        'this','that','it','i','you','we','they','my','your','our','their','and',
        'or','but','so','if','as','by','from','up','out','how','what','when',
        'where','who','all','just','do','dont','can','get','has','have',
    }

    freq: dict = {}
    for (cap, views) in rows:
        if not cap:
            continue
        weight = max(1, min(int(views or 1) // 1000, 10))  # views boost, capped at 10×
        words = _re.findall(r'[a-zA-ZÀ-ỹ\u00C0-\u024F\u1E00-\u1EFF]{3,}', cap.lower())
        for w in words:
            if w not in STOPWORDS:
                freq[w] = freq.get(w, 0) + weight

    if limit < 1 or limit > 100:
        limit = 25
    topics = sorted(freq.items(), key=lambda x: -x[1])[:limit]

    return {
        "status":                  "success",
        "topics":                  [{"word": w, "count": c} for w, c in topics],
        "total_captions_analyzed": len(rows),
        "days":                    days,
    }
