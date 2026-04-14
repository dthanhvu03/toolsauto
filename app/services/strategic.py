import logging
import time
import json
from sqlalchemy import text, or_
from sqlalchemy.orm import Session
from app.database.models import PageInsight, ViralMaterial, Account, Job
from app.services.notifier_service import NotifierService
from app.constants import ViralStatus


logger = logging.getLogger(__name__)


class PageStrategicService:
    """
    Strategic Analysis & Autonomous Boosting Service.
    Identifies high-growth 'exploding' FB pages and automatically pushes
    niche-matched content with context-aware AI captions.
    """
    _cache = {}
    _cache_ts = {}  # timestamp per platform key
    CACHE_TTL = 900  # 15 minutes

    @staticmethod
    def get_page_analysis(db: Session, platform: str = None):
        """
        Categorize pages based on growth momentum and engagement.
        Now includes AI-powered advice via 9Router with batching and caching.
        """
        cache_key = platform or "all"
        now_ts = int(time.time())
        
        # 1. Check Service Layer Cache
        if cache_key in PageStrategicService._cache:
            if now_ts - PageStrategicService._cache_ts.get(cache_key, 0) < PageStrategicService.CACHE_TTL:
                logger.debug(f"[STRATEGIC] Cache hit for {cache_key}")
                return PageStrategicService._cache[cache_key]

        # 2. Calculate Base Metrics from DB
        platform_filter = f"WHERE platform = '{platform}'" if platform else ""
        
        sql = f"""
        WITH PageSnapshots AS (
            SELECT 
                page_url, page_name, platform, account_id,
                SUM(views) as total_views,
                AVG(CASE WHEN views > 0 THEN (CAST(likes AS FLOAT) / views) * 100 ELSE 0 END) as avg_eng_rate,
                recorded_at,
                ROW_NUMBER() OVER(PARTITION BY page_url ORDER BY recorded_at DESC) as rn
            FROM (
                SELECT page_url, page_name, platform, account_id, post_url, MAX(views) as views, MAX(likes) as likes, recorded_at
                FROM page_insights
                {platform_filter}
                GROUP BY page_url, post_url, (recorded_at / 3600)
            )
            GROUP BY page_url, recorded_at
        )
        SELECT 
            curr.page_url, curr.page_name, curr.platform, curr.account_id,
            curr.total_views as current_views,
            curr.avg_eng_rate,
            COALESCE(prev.total_views, 0) as prev_views,
            (curr.total_views - COALESCE(prev.total_views, 0)) as growth_abs,
            CASE WHEN COALESCE(prev.total_views, 0) > 0 
                 THEN ((CAST(curr.total_views AS FLOAT) - prev.total_views) / prev.total_views) * 100 
                 ELSE 0 END as growth_pct
        FROM PageSnapshots curr
        LEFT JOIN PageSnapshots prev ON curr.page_url = prev.page_url AND prev.rn = 2
        WHERE curr.rn = 1
        ORDER BY growth_abs DESC
        """
        
        results = db.execute(text(sql)).fetchall()
        
        analysis = []
        batch_data = []

        for r in results:
            # Default hardcoded categorization (Fallback / Context)
            status = "STEADY"
            hardcoded_advice = "Duy trì tần suất đăng bài hiện tại."
            priority = 3
            color = "amber"
            
            # EXPLODING: Growth > 10% OR Abs Growth > 500 views in ~2h
            if r.growth_pct > 10 or r.growth_abs > 500:
                status = "EXPLODING 🔥"
                hardcoded_advice = "Tiềm năng viral cao! Hãy reup thêm 3-5 video cùng chủ đề ngay."
                priority = 1
                color = "green"
            elif r.growth_pct < 1 and r.growth_abs < 50:
                status = "STAGNANT ⚠️"
                hardcoded_advice = "Nội dung đang bão hòa. Hãy đổi Niche hoặc test chủ đề mới."
                priority = 4
                color = "rose"
            elif r.avg_eng_rate > 5:
                status = "HIGH ENGAGEMENT 💎"
                hardcoded_advice = "Khán giả cực kỳ thích content này. Tập trung vào chất lượng hơn số lượng."
                priority = 2
                color = "cyan"

            item = {
                "page_name": r.page_name,
                "page_url": r.page_url,
                "platform": r.platform,
                "account_id": r.account_id,
                "views": r.current_views,
                "growth_abs": r.growth_abs,
                "growth_pct": round(r.growth_pct, 1),
                "eng_rate": round(r.avg_eng_rate, 2),
                "status": status,
                "advice": hardcoded_advice,  # Initial advice is hardcoded fallback
                "priority": priority,
                "color": color
            }
            analysis.append(item)
            
            batch_data.append({
                "name": r.page_name,
                "views": f"{r.current_views:,}",
                "growth": f"+{round(r.growth_pct, 1)}%",
                "engagement": f"{round(r.avg_eng_rate, 2)}%",
                "status": status
            })

        # 3. AI Batch AI Analysis (9Router)
        if analysis:
            try:
                from app.services.ai_runtime import pipeline
                if pipeline.enabled:
                    data_str = "\n".join([f"- {d['name']}: {d['views']} views, {d['growth']} growth, {d['engagement']} eng, status: {d['status']}" for d in batch_data])
                    
                    prompt = f"""Bạn là chuyên gia phân tích chiến lược Social Media. 
Dựa vào dữ liệu metrics bên dưới của các trang, hãy đưa ra đúng 1 câu nhận xét/khuyên ngắn gọn (actionable advice) cho TỪNG trang.

Yêu cầu:
- Trả về kết quả theo định dạng: [Tên trang]: [Lời khuyên]
- Mỗi trang 1 dòng.
- Lời khuyên cực ngắn gọn (dưới 20 từ), tập trung vào hành động cụ thể để tăng trưởng.

Dữ liệu:
{data_str}

Kết quả:"""
                    
                    ai_text, meta = pipeline.generate_text(prompt)
                    
                    if ai_text and meta.get("ok"):
                        print(f"[STRATEGIC] Raw AI Response for {len(batch_data)} pages:\n{ai_text}")
                        ai_map = {}
                        for line in ai_text.strip().split("\n"):
                            line = line.strip()
                            if ":" in line:
                                parts = line.split(":", 1)
                                name_part = parts[0].strip().lstrip("0123456789. -*#").lower()
                                msg = parts[1].strip()
                                if name_part:
                                    ai_map[name_part] = msg
                        
                        print(f"[STRATEGIC] Parsed AI Map keys: {list(ai_map.keys())}")
                        
                        if ai_map:
                            match_count = 0
                            for item in analysis:
                                p_name = item["page_name"].lower().strip()
                                for ai_name, ai_msg in ai_map.items():
                                    if ai_name in p_name or p_name in ai_name:
                                        item["advice"] = ai_msg
                                        item["is_ai"] = True
                                        match_count += 1
                                        break
                            print(f"[STRATEGIC] Successfully matched AI advice for {match_count}/{len(analysis)} pages.")
                            
                            # Update Cache only on SUCCESS - to persist AI advice
                            PageStrategicService._cache[cache_key] = analysis
                            PageStrategicService._cache_ts[cache_key] = now_ts
                        else:
                            print("[STRATEGIC] AI response parsing failed to find any valid matches.")
                    else:
                        print(f"[STRATEGIC] AI call unsuccessful: {meta.get('fail_reason', 'no text')}")
                        # If AI fails, we DON'T update the cache if there is already a valid AI cache
                        if cache_key not in PageStrategicService._cache:
                             PageStrategicService._cache[cache_key] = analysis
                             PageStrategicService._cache_ts[cache_key] = now_ts
            except Exception as e:
                print(f"[STRATEGIC] AI Batch Error: {e}")
                logger.error("Strategic AI Error", exc_info=True)
                if cache_key not in PageStrategicService._cache:
                    PageStrategicService._cache[cache_key] = analysis
                    PageStrategicService._cache_ts[cache_key] = now_ts

        return PageStrategicService._cache.get(cache_key, analysis)

    @staticmethod
    def _lookup_page_niches(db: Session, account_id: int, page_url: str) -> list[str]:
        """Lookup niche keywords for a specific page from Account.page_niches."""
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account:
            return []
        pn_map = account.page_niches_map or {}
        for p_url, niches in pn_map.items():
            if page_url in p_url or p_url in page_url:
                return niches if isinstance(niches, list) else []
        return []

    @staticmethod
    def _find_niche_material(db: Session, platform: str, niches: list[str]) -> ViralMaterial | None:
        """Find a NEW ViralMaterial whose title matches any of the niche keywords."""
        if not niches:
            return None
        filters = [ViralMaterial.title.ilike(f"%{kw}%") for kw in niches]
        return db.query(ViralMaterial).filter(
            ViralMaterial.platform == platform,
            ViralMaterial.status == ViralStatus.NEW,
            ViralMaterial.title.isnot(None),
            or_(*filters)
        ).order_by(ViralMaterial.views.desc()).first()

    @staticmethod
    def _get_top_posts_summary(db: Session, page_url: str, limit: int = 3) -> str:
        """Get a short summary of top-performing posts for context injection."""
        top_posts = db.query(PageInsight).filter(
            PageInsight.page_url == page_url,
            PageInsight.caption.isnot(None),
            PageInsight.caption != ""
        ).order_by(PageInsight.views.desc()).limit(limit).all()

        if not top_posts:
            return ""
        
        parts = []
        for tp in top_posts:
            cap_preview = (tp.caption or "")[:60].replace('"', "'")
            parts.append(f'"{cap_preview}..." ({tp.views:,} views)')
        return "; ".join(parts)

    @staticmethod
    def run_auto_boost(db: Session):
        """
        Scan FB pages only. If any page is EXPLODING, autonomously trigger
        a niche-matched reup job with top-post context for AI caption.
        """
        logger.info("[STRATEGIC] Running autonomous FB growth scan...")
        # ── FB-only: không boost TikTok pages ──
        pages = PageStrategicService.get_page_analysis(db, platform="facebook")
        exploding_pages = [p for p in pages if "EXPLODING" in p["status"]]
        
        if not exploding_pages:
            logger.info("[STRATEGIC] No exploding FB pages detected.")
            return

        boosted_count = 0
        for p in exploding_pages:
            # 1. Check cooldown (Session Binge Window: giảm xuống 1h để mớm liên tục video cùng niche)
            last_boost = db.query(ViralMaterial).filter(
                ViralMaterial.target_page == p["page_url"],
                ViralMaterial.status == ViralStatus.REUP,
                ViralMaterial.created_at >= int(time.time()) - 3600  # 1h (Session Binge Window)
            ).first()
            if last_boost:
                logger.debug("[STRATEGIC] Page '%s' still in 1h Binge Window cooldown, skipping.", p["page_name"])
                continue

            # 2. Lookup page niches for smart material matching
            page_niches = PageStrategicService._lookup_page_niches(
                db, p["account_id"], p["page_url"]
            )

            # 3. Find best candidate: niche-match first, fallback to highest views
            material = None
            niche_matched = False
            if page_niches:
                material = PageStrategicService._find_niche_material(
                    db, p["platform"], page_niches
                )
                if material:
                    niche_matched = True
                    logger.info("[STRATEGIC] Niche-matched material #%s for page '%s' (niches: %s)",
                                material.id, p["page_name"], page_niches)

            if not material:
                material = db.query(ViralMaterial).filter(
                    ViralMaterial.platform == p["platform"],
                    ViralMaterial.status == ViralStatus.NEW
                ).order_by(ViralMaterial.views.desc()).first()

            if not material:
                logger.info("[STRATEGIC] No NEW material available for page '%s'.", p["page_name"])
                continue

            logger.info("[STRATEGIC] 🚀 AUTO-BOOSTING page '%s' (%s) with material #%s %s",
                        p["page_name"], p["page_url"], material.id, material.url)

            # 4. Build BOOST_CONTEXT for AI caption generation
            top_posts_summary = PageStrategicService._get_top_posts_summary(db, p["page_url"])
            niches_str = ",".join(page_niches) if page_niches else "general"
            
            boost_context = (
                f"Page đang EXPLODING (+{p['growth_pct']}%), "
                f"niche={niches_str}"
            )
            if top_posts_summary:
                boost_context += f", top_posts=[{top_posts_summary}]"

            # 5. Inject into reup pipeline with BOOST_CONTEXT
            material.status = ViralStatus.REUP
            material.target_page = p["page_url"]
            material.scraped_by_account_id = p["account_id"]
            
            # 6. Notify via Telegram (enriched with niche info)
            try:
                niche_display = ", ".join(page_niches) if page_niches else "chưa set"
                match_label = "✅ Niche-match" if niche_matched else "📊 Top views"
                msg = (
                    f"🚀 <b>SMART BOOST</b> (FB)\n"
                    f"📄 Page: <code>{p['page_name']}</code>\n"
                    f"🔥 Status: <b>{p['status']}</b> (+{p['growth_pct']}%)\n"
                    f"🏷 Niche: <b>{niche_display}</b>\n"
                    f"🎯 Material: {match_label}\n"
                    f"🔗 <a href='{material.url}'>Link Video</a>"
                )
                NotifierService._broadcast(msg)
            except Exception as ne:
                logger.error("Failed to send boost notification: %s", ne)
            
            boosted_count += 1

        if boosted_count > 0:
            db.commit()
            logger.info("[STRATEGIC] Autonomous scan complete. Boosted %d FB pages.", boosted_count)
        else:
            logger.info("[STRATEGIC] Scan complete. No eligible FB pages (cooldown or no material).")
