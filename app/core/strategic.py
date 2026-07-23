import logging
import time
import json
from sqlalchemy import text, or_
from sqlalchemy.orm import Session
from app.core.database.models import PageInsight, ViralMaterial, Account, Job
from app.core.notifier.service import NotifierService
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
        params = {}
        platform_filter = ""
        if platform:
            # Parameterized — never interpolate user input into SQL.
            platform_filter = "WHERE platform = :platform"
            params["platform"] = platform
        
        sql = f"""
        WITH PageSnapshots AS (
            SELECT 
                page_url, page_name, platform, account_id,
                SUM(views) as total_views,
                AVG(CASE WHEN views > 0 THEN (CAST(likes AS FLOAT) / views) * 100 ELSE 0 END) as avg_eng_rate,
                MAX(recorded_at) as recorded_at,
                ROW_NUMBER() OVER(PARTITION BY page_url ORDER BY time_bucket DESC) as rn
            FROM (
                SELECT 
                    page_url, page_name, platform, account_id, post_url, 
                    MAX(views) as views, 
                    MAX(likes) as likes, 
                    MAX(recorded_at) as recorded_at,
                    (recorded_at / 3600) as time_bucket
                FROM page_insights
                {platform_filter}
                GROUP BY page_url, page_name, platform, account_id, post_url, (recorded_at / 3600)
            ) subq
            GROUP BY page_url, page_name, platform, account_id, time_bucket
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
        
        results = db.execute(text(sql), params).fetchall()
        
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
                from app.core.ai.use_cases import AIPurpose, AIUseCases
                if AIUseCases.is_enabled():
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
                    
                    ai_text, meta = AIUseCases.generate_text(
                        prompt, purpose=AIPurpose.STRATEGIC_ADVICE
                    )
                    
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
    def _lookup_page_niches_from_account(account: Account | None, page_url: str) -> list[str]:
        if not account:
            return []
        pn_map = account.page_niches_map or {}
        for p_url, niches in pn_map.items():
            if page_url in p_url or p_url in page_url:
                return niches if isinstance(niches, list) else []
        return []

    @staticmethod
    def _lookup_page_niches(db: Session, account_id: int, page_url: str) -> list[str]:
        """Lookup niche keywords for a specific page from Account.page_niches."""
        account = db.query(Account).filter(Account.id == account_id).first()
        return PageStrategicService._lookup_page_niches_from_account(account, page_url)

    @staticmethod
    def _find_niche_material_in_pool(
        pool: list[ViralMaterial], niches: list[str]
    ) -> ViralMaterial | None:
        if not niches or not pool:
            return None
        lowered = [kw.lower() for kw in niches if kw]
        for mat in pool:
            title = (mat.title or "").lower()
            if any(kw in title for kw in lowered):
                return mat
        return None

    @staticmethod
    def _find_niche_material(db: Session, niches: list[str], source_platforms: list[str] | None = None) -> ViralMaterial | None:
        """Find a NEW ViralMaterial whose title matches any of the niche keywords."""
        if not niches:
            return None
        platforms = source_platforms or ["tiktok", "facebook"]
        filters = [ViralMaterial.title.ilike(f"%{kw}%") for kw in niches]
        return db.query(ViralMaterial).filter(
            ViralMaterial.platform.in_(platforms),
            ViralMaterial.status == ViralStatus.NEW,
            ViralMaterial.title.isnot(None),
            or_(*filters)
        ).order_by(ViralMaterial.views.desc()).first()

    @staticmethod
    def _summarize_top_posts(top_posts: list) -> str:
        if not top_posts:
            return ""
        parts = []
        for tp in top_posts:
            cap_preview = (tp.caption or "")[:60].replace('"', "'")
            parts.append(f'"{cap_preview}..." ({tp.views:,} views)')
        return "; ".join(parts)

    @staticmethod
    def _get_top_posts_summary(db: Session, page_url: str, limit: int = 3) -> str:
        """Get a short summary of top-performing posts for context injection."""
        top_posts = db.query(PageInsight).filter(
            PageInsight.page_url == page_url,
            PageInsight.caption.isnot(None),
            PageInsight.caption != ""
        ).order_by(PageInsight.views.desc()).limit(limit).all()
        return PageStrategicService._summarize_top_posts(top_posts)

    @staticmethod
    def run_auto_boost(db: Session):
        """
        Scan FB pages. If EXPLODING → đề xuất BOOST_PENDING (chờ Approve trên Insights).
        Material nguồn: tiktok (và facebook) NEW — không lọc theo platform page.
        """
        logger.info("[STRATEGIC] Running autonomous FB growth scan (propose BOOST_PENDING)...")
        pages = PageStrategicService.get_page_analysis(db, platform="facebook")
        exploding_pages = [p for p in pages if "EXPLODING" in p["status"]]

        if not exploding_pages:
            logger.info("[STRATEGIC] No exploding FB pages detected.")
            return

        source_platforms = ["tiktok", "facebook"]
        page_urls = [p["page_url"] for p in exploding_pages if p.get("page_url")]
        account_ids = {p["account_id"] for p in exploding_pages if p.get("account_id")}

        accounts_by_id = {
            a.id: a
            for a in db.query(Account).filter(Account.id.in_(account_ids)).all()
        } if account_ids else {}

        cooldown_cutoff = int(time.time()) - 3600
        cooling_pages = {
            url
            for (url,) in db.query(ViralMaterial.target_page)
            .filter(
                ViralMaterial.target_page.in_(page_urls),
                ViralMaterial.status.in_([ViralStatus.REUP, ViralStatus.BOOST_PENDING]),
                ViralMaterial.updated_at >= cooldown_cutoff,
            )
            .distinct()
            .all()
        } if page_urls else set()

        from collections import defaultdict

        top_posts_by_page: dict[str, list] = defaultdict(list)
        if page_urls:
            posts = (
                db.query(PageInsight)
                .filter(
                    PageInsight.page_url.in_(page_urls),
                    PageInsight.caption.isnot(None),
                    PageInsight.caption != "",
                )
                .order_by(PageInsight.views.desc())
                .all()
            )
            for tp in posts:
                bucket = top_posts_by_page[tp.page_url]
                if len(bucket) < 3:
                    bucket.append(tp)

        # Pool NEW materials once; consume as assigned (tránh query top-NEW mỗi page)
        material_pool = (
            db.query(ViralMaterial)
            .filter(
                ViralMaterial.platform.in_(source_platforms),
                ViralMaterial.status == ViralStatus.NEW,
            )
            .order_by(ViralMaterial.views.desc())
            .limit(200)
            .all()
        )

        boosted_count = 0
        for p in exploding_pages:
            if p["page_url"] in cooling_pages:
                logger.debug("[STRATEGIC] Page '%s' still in 1h boost cooldown, skipping.", p["page_name"])
                continue

            account = accounts_by_id.get(p["account_id"])
            page_niches = PageStrategicService._lookup_page_niches_from_account(
                account, p["page_url"]
            )

            material = None
            niche_matched = False
            if page_niches:
                material = PageStrategicService._find_niche_material_in_pool(
                    material_pool, page_niches
                )
                if not material:
                    # Fallback SQL: pool top-200 có thể miss niche thấp views (giữ behavior cũ)
                    material = PageStrategicService._find_niche_material(
                        db, page_niches, source_platforms=source_platforms
                    )
                if material:
                    niche_matched = True
                    logger.info(
                        "[STRATEGIC] Niche-matched material #%s for page '%s' (niches: %s)",
                        material.id,
                        p["page_name"],
                        page_niches,
                    )

            if not material and material_pool:
                material = material_pool[0]

            if not material:
                logger.info("[STRATEGIC] No NEW material available for page '%s'.", p["page_name"])
                continue

            material_pool = [m for m in material_pool if m.id != material.id]

            niches_str = ",".join(page_niches) if page_niches else "general"
            top_posts_summary = PageStrategicService._summarize_top_posts(
                top_posts_by_page.get(p["page_url"], [])
            )
            boost_context = (
                f"Page đang EXPLODING (+{p['growth_pct']}%), niche={niches_str}"
            )
            if top_posts_summary:
                boost_context += f", top_posts=[{top_posts_summary}]"

            # Persist BOOST_CONTEXT trên title (không cần migration cột)
            clean_title = material.title or ""
            if "### BOOST_CONTEXT:" in clean_title:
                import re as _re
                clean_title = _re.sub(r"\s*###\s*BOOST_CONTEXT:.*?###\s*", " ", clean_title).strip()
            material.title = f"{clean_title} ### BOOST_CONTEXT: {boost_context} ###".strip()
            material.status = ViralStatus.BOOST_PENDING
            material.target_page = p["page_url"]
            material.scraped_by_account_id = p["account_id"]
            cooling_pages.add(p["page_url"])

            logger.info(
                "[STRATEGIC] 📋 BOOST_PENDING page '%s' material #%s %s",
                p["page_name"],
                material.id,
                material.url,
            )

            try:
                niche_display = ", ".join(page_niches) if page_niches else "chưa set"
                match_label = "✅ Niche-match" if niche_matched else "📊 Top views"
                msg = (
                    f"📋 <b>BOOST ĐỀ XUẤT</b> — chờ Approve trên Insights\n"
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
            logger.info("[STRATEGIC] Proposed %d BOOST_PENDING items.", boosted_count)
        else:
            logger.info("[STRATEGIC] Scan complete. No eligible proposals.")

    @staticmethod
    def list_boost_proposals(db: Session) -> list[dict]:
        rows = (
            db.query(ViralMaterial)
            .filter(ViralMaterial.status == ViralStatus.BOOST_PENDING)
            .order_by(ViralMaterial.updated_at.desc())
            .limit(50)
            .all()
        )
        out = []
        for m in rows:
            ctx = ""
            if m.title and "### BOOST_CONTEXT:" in m.title:
                import re as _re
                match = _re.search(r"###\s*BOOST_CONTEXT:\s*(.+?)\s*###", m.title)
                if match:
                    ctx = match.group(1).strip()
            display_title = m.title or m.url
            if "### BOOST_CONTEXT:" in display_title:
                import re as _re
                display_title = _re.sub(r"\s*###\s*BOOST_CONTEXT:.*?###\s*", " ", display_title).strip()
            out.append(
                {
                    "id": m.id,
                    "url": m.url,
                    "title": display_title,
                    "views": m.views or 0,
                    "platform": m.platform,
                    "target_page": m.target_page,
                    "boost_context": ctx,
                    "account_id": m.scraped_by_account_id,
                }
            )
        return out

    @staticmethod
    def approve_boost_proposal(db: Session, material_id: int) -> ViralMaterial:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
        if not mat or mat.status != ViralStatus.BOOST_PENDING:
            raise ValueError("Đề xuất boost không tồn tại hoặc đã xử lý.")
        mat.status = ViralStatus.REUP
        db.commit()
        logger.info("[STRATEGIC] Approved BOOST → REUP material #%s", mat.id)
        return mat

    @staticmethod
    def reject_boost_proposal(db: Session, material_id: int) -> ViralMaterial:
        mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
        if not mat or mat.status != ViralStatus.BOOST_PENDING:
            raise ValueError("Đề xuất boost không tồn tại hoặc đã xử lý.")
        # Trả về NEW, giữ URL; gỡ marker BOOST_CONTEXT khỏi title
        if mat.title and "### BOOST_CONTEXT:" in mat.title:
            import re as _re
            mat.title = _re.sub(r"\s*###\s*BOOST_CONTEXT:.*?###\s*", " ", mat.title).strip() or mat.title
        mat.status = ViralStatus.NEW
        mat.target_page = None
        db.commit()
        logger.info("[STRATEGIC] Rejected BOOST_PENDING material #%s → NEW", mat.id)
        return mat
