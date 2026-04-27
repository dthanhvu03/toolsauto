from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional
import logging

logger = logging.getLogger(__name__)

from app.database.core import get_db

from app.services import insights_service

CACHE_TTL = 3600  # 1 hour
COMMENTARY_CACHE_TTL = 1800  # 30 min — AI calls are slow & expensive
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/insights", tags=["Insights"])

@router.get("/", response_class=HTMLResponse)
def view_insights_dashboard(request: Request, db: Session = Depends(get_db)):
    return insights_service.view_insights_dashboard(request, db)

@router.get("/api/growth")
def get_growth_metrics(
    page_url: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db)
):
    return insights_service.get_growth_metrics(page_url, platform, days, db)

@router.get("/api/top-posts")
def get_top_posts(
    page_url: Optional[str] = None,
    platform: Optional[str] = "facebook",
    days: int = 7,
    page: int = 1,
    limit: int = 15,
    sort_by: Optional[str] = "views",
    db: Session = Depends(get_db)
):
    return insights_service.get_top_posts(page_url, platform, days, page, limit, sort_by, db)

@router.get("/api/page-analysis")
def get_page_analysis(platform: str = None, db: Session = Depends(get_db)):
    return insights_service.get_page_analysis(platform, db)

@router.get("/api/platform-stats")
def get_platform_stats(
    page_url: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    return insights_service.get_platform_stats(page_url, days, db)

@router.get("/api/engagement-heatmap")
def get_engagement_heatmap(
    page_url: Optional[str] = None,
    platform: Optional[str] = "facebook",
    days: int = 7,
    db: Session = Depends(get_db),
):
    return insights_service.get_engagement_heatmap(page_url, platform, days, db)

@router.get("/api/secondary-metrics")
def get_secondary_metrics(
    page_url: Optional[str] = None,
    platform: Optional[str] = "facebook",
    days: int = 7,
    db: Session = Depends(get_db),
):
    return insights_service.get_secondary_metrics(page_url, platform, days, db)

@router.get("/api/ai-commentary")
def get_ai_commentary(
    page_url: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    return insights_service.get_ai_commentary(page_url, platform, days, db)

@router.get("/api/ai-roadmap")
def get_ai_roadmap(
    page_url: Optional[str] = None,
    platform: Optional[str] = None,
    days: int = 7,
    db: Session = Depends(get_db),
):
    return insights_service.get_ai_roadmap(page_url, platform, days, db)

@router.get("/api/status")
def get_data_status(db: Session = Depends(get_db)):
    return insights_service.get_data_status(db)

@router.post("/api/trigger-refresh")
def trigger_refresh():
    return insights_service.trigger_refresh()

@router.get("/api/market-benchmark")
def get_market_benchmark(
    platform: Optional[str] = "facebook",
    days: int = 7,
    db: Session = Depends(get_db),
):
    return insights_service.get_market_benchmark(platform, days, db)

@router.get("/api/competitor-top")
def get_competitor_top(
    days: int = 7,
    page: int = 1,
    limit: int = 20,
    sort_by: Optional[str] = "views",
    db: Session = Depends(get_db),
):
    return insights_service.get_competitor_top(days, page, limit, sort_by, db)

@router.get("/api/trending-topics")
def get_trending_topics(
    days: int = 7,
    limit: int = 25,
    db: Session = Depends(get_db),
):
    return insights_service.get_trending_topics(days, limit, db)

