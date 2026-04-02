from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional
import datetime

from app.database.core import get_db
from app.database import models

router = APIRouter(prefix="/insights", tags=["Insights"])
templates = Jinja2Templates(directory="app/templates")

@router.get("/api/platform-stats/")
@router.get("/api/platform-stats")
def get_platform_stats(page_url: Optional[str] = None, db: Session = Depends(get_db)):
    """Get view and post distribution per platform."""
    from sqlalchemy import text
    sql = """
        SELECT platform, SUM(views) as total_views, COUNT(DISTINCT post_url) as post_count
        FROM page_insights
        WHERE (:page_url IS NULL OR page_url = :page_url)
        GROUP BY platform
    """
    results = db.execute(text(sql), {"page_url": page_url}).fetchall()
    data = [{"platform": r.platform, "views": r.total_views or 0, "posts": r.post_count} for r in results]
    return {"status": "success", "data": data}

@router.get("/api/engagement-heatmap/")
@router.get("/api/engagement-heatmap")
def get_engagement_heatmap(page_url: Optional[str] = None, platform: Optional[str] = None, db: Session = Depends(get_db)):
    """Get interaction density (likes + comments + shares) by Day of Week (0-6) and Hour (0-23)."""
    from sqlalchemy import text
    sql = """
        SELECT 
            CAST(strftime('%w', datetime(recorded_at, 'unixepoch')) AS INTEGER) as dow,
            CAST(strftime('%H', datetime(recorded_at, 'unixepoch')) AS INTEGER) as hour,
            SUM(COALESCE(likes, 0) + COALESCE(comments, 0) + COALESCE(shares, 0)) as total_interactions
        FROM page_insights
        WHERE (:page_url IS NULL OR page_url = :page_url)
          AND (:platform IS NULL OR platform = :platform)
        GROUP BY dow, hour
    """
    results = db.execute(text(sql), {"page_url": page_url, "platform": platform}).fetchall()
    
    # Initialize 7x24 grid with zeros
    grid = [[0 for _ in range(24)] for _ in range(7)]
    for r in results:
        grid[r.dow][r.hour] = int(r.total_interactions or 0)
        
    return {"status": "success", "data": grid}

@router.get("/api/secondary-metrics/")
@router.get("/api/secondary-metrics")
def get_secondary_metrics(page_url: Optional[str] = None, platform: Optional[str] = None, db: Session = Depends(get_db)):
    """Calculate secondary performance indicators."""
    from sqlalchemy import text
    # Calculate Avg Views per Post and Total Shares
    sql = """
        SELECT 
            SUM(views) as total_views,
            COUNT(DISTINCT post_url) as total_posts,
            SUM(shares) as total_shares,
            SUM(likes) as total_likes
        FROM page_insights
        WHERE (:page_url IS NULL OR page_url = :page_url)
          AND (:platform IS NULL OR platform = :platform)
    """
    r = db.execute(text(sql), {"page_url": page_url, "platform": platform}).fetchone()
    
    total_views = r.total_views or 0
    total_posts = r.total_posts or 1
    total_shares = r.total_shares or 0
    total_likes = r.total_likes or 0
    
    return {
        "status": "success", 
        "data": {
            "avg_views": round(total_views / total_posts, 1),
            "total_shares": total_shares,
            "engagement_rate": round((total_likes + total_shares) / total_views * 100, 2) if total_views > 0 else 0,
            "posts_count": total_posts
        }
    }

@router.get("/", response_class=HTMLResponse)
def view_insights_dashboard(request: Request, db: Session = Depends(get_db)):
    """Render the main insights dashboard HTML page."""
    # Get all unique pages that have insights
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

@router.get("/api/growth")
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
    
    now = int(datetime.datetime.now().timestamp())
    cutoff = now - (days * 86400)
    time_format = "%Y-%m-%d %H:00" if days <= 2 else "%Y-%m-%d"
    
    # We use a subquery to find the latest (max) view count per post_url in each group
    # This prevents counting the same post multiple times if scraped twice in the same hour.
    sql = f"""
    WITH LatestPerGroup AS (
        SELECT 
            strftime('{time_format}', datetime(recorded_at, 'unixepoch')) as time_label,
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
            "likes": r.total_likes or 0
        })
        
    return {"status": "success", "data": data}

@router.get("/api/top-posts")
def get_top_posts(
    page_url: Optional[str] = None,
    platform: Optional[str] = "facebook",
    limit: int = 15,
    db: Session = Depends(get_db)
):
    """
    Get high-performing posts with advanced decision metrics.
    Calculates Engagement Rate and 24h Velocity using window functions.
    """
    from sqlalchemy import text
    
    # We use a raw SQL query with window functions for efficiency in SQLite 3.25+
    # 1. Get the latest TWO snapshots for each post_url
    # 2. Calculate the difference (Velocity) between them
    sql = """
    WITH RankedInsights AS (
        SELECT 
            post_url, page_name, platform, views, likes, comments, caption, recorded_at,
            ROW_NUMBER() OVER (PARTITION BY post_url ORDER BY recorded_at DESC) as rn
        FROM page_insights
        WHERE (:platform IS NULL OR platform = :platform)
          AND (:page_url IS NULL OR page_url = :page_url)
    )
    SELECT 
        l1.post_url, l1.page_name, l1.platform, l1.views, l1.likes, l1.comments, l1.caption,
        (l1.views - COALESCE(l2.views, 0)) as velocity,
        CASE WHEN l1.views > 0 THEN (CAST(l1.likes AS FLOAT) / l1.views) * 100 ELSE 0 END as eng_rate
    FROM RankedInsights l1
    LEFT JOIN RankedInsights l2 ON l1.post_url = l2.post_url AND l2.rn = 2
    WHERE l1.rn = 1
    ORDER BY l1.views DESC
    LIMIT :limit
    """
    
    params = {
        "platform": platform,
        "page_url": page_url,
        "limit": limit
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
            "caption": r.caption or "",
            "velocity": r.velocity or 0,
            "engagement_rate": round(r.eng_rate or 0, 2)
        })
        
    return {"status": "success", "data": data}

@router.get("/api/page-analysis")
def get_page_analysis(platform: str = None, db: Session = Depends(get_db)):
    """
    Strategic Analysis: Categorize pages based on growth momentum and engagement.
    Uses the centralized PageStrategicService with platform filtering.
    """
    from app.services.strategic import PageStrategicService
    analysis = PageStrategicService.get_page_analysis(db, platform=platform)
    return {"status": "success", "data": analysis}

@router.get("/api/platform-stats")
def get_platform_stats(page_url: Optional[str] = None, db: Session = Depends(get_db)):
    from sqlalchemy import text
    sql = """
    SELECT platform, SUM(views) as total_views 
    FROM page_insights 
    WHERE (:page_url IS NULL OR page_url = :page_url)
    GROUP BY platform
    """
    params = {"page_url": page_url}
    results = db.execute(text(sql), params).fetchall()
    data = [{"platform": r[0] or "unknown", "views": r[1] or 0} for r in results]
    return {"status": "success", "data": data}

@router.get("/api/engagement-heatmap")
def get_engagement_heatmap(page_url: Optional[str] = None, platform: Optional[str] = "facebook", db: Session = Depends(get_db)):
    from sqlalchemy import text
    # strftime('%w'...) returns 0-6 where 0 is Sunday.
    sql = """
    SELECT 
        CAST(strftime('%w', datetime(recorded_at, 'unixepoch', 'localtime')) AS INTEGER) as dow,
        CAST(strftime('%H', datetime(recorded_at, 'unixepoch', 'localtime')) AS INTEGER) as hour,
        SUM(likes + comments) as interactions
    FROM page_insights
    WHERE (:platform IS NULL OR platform = :platform)
      AND (:page_url IS NULL OR page_url = :page_url)
    GROUP BY dow, hour
    """
    params = {"platform": platform, "page_url": page_url}
    results = db.execute(text(sql), params).fetchall()
    
    # Initialize 7x24 grid with zeros (0=Sun, 1=Mon... 6=Sat)
    # JS expects order: 1, 2, 3, 4, 5, 6, 0
    heatmap = [[0 for _ in range(24)] for _ in range(7)]
    for r in results:
        dow, hour, interactions = r[0], r[1], r[2]
        if dow is not None and hour is not None:
            heatmap[dow][hour] = interactions or 0
            
    return {"status": "success", "data": heatmap}

@router.get("/api/secondary-metrics")
def get_secondary_metrics(page_url: Optional[str] = None, platform: Optional[str] = "facebook", db: Session = Depends(get_db)):
    from sqlalchemy import text
    sql = """
    SELECT 
        AVG(views) as avg_views, 
        SUM(shares) as total_shares, 
        CASE WHEN SUM(views) > 0 THEN SUM(likes)*100.0/SUM(views) ELSE 0 END as eng_rate,
        COUNT(DISTINCT post_url) as active_posts
    FROM page_insights
    WHERE (:platform IS NULL OR platform = :platform)
      AND (:page_url IS NULL OR page_url = :page_url)
    """
    params = {"platform": platform, "page_url": page_url}
    result = db.execute(text(sql), params).fetchone()
    
    data = {
        "avg_views": round(result[0] or 0, 1) if result else 0,
        "total_shares": result[1] or 0 if result else 0,
        "engagement_rate": round(result[2] or 0, 2) if result else 0,
        "posts_count": result[3] or 0 if result else 0
    }
    return {"status": "success", "data": data}
