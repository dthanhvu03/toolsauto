import logging
import datetime
import math
from typing import Any, List, Dict, Tuple
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, text
from app.core.database.models import Job, Account, DiscoveredChannel, IncidentGroup, ViralMaterial
from app.core.queue.worker import WorkerService
from app.constants import JobStatus, ViralStatus
from app.core import settings as runtime_settings
from app.core.account import AccountService
from app.core import feature_hooks
import app.config as config

logger = logging.getLogger(__name__)

class DashboardService:

    @staticmethod
    def get_overview_data(db: Session) -> Dict[str, Any]:
        accounts = db.query(Account).all()
        state = WorkerService.get_or_create_state(db)
        return {"accounts": accounts, "state": state}

    @staticmethod
    def save_setting(db: Session, key: str, value: str, updated_by: str = None) -> None:
        runtime_settings.upsert_setting(db, key=key, raw_value=value, updated_by=updated_by)
        runtime_settings.load_runtime_settings_into_process(db)

    @staticmethod
    def reset_setting(db: Session, key: str, updated_by: str = None) -> None:
        runtime_settings.reset_setting(db, key=key, updated_by=updated_by)
        runtime_settings.load_runtime_settings_into_process(db)

    @staticmethod
    def track_redirect_click(db: Session, code: str) -> str | None:
        job = db.query(Job).filter(Job.tracking_code == code).first()
        if not job or not job.affiliate_url:
            return None
        job.click_count = (job.click_count or 0) + 1
        db.commit()
        return job.affiliate_url

    @staticmethod
    def get_page_posting_stats(db: Session) -> Dict[str, Any]:
        try:
            cap = int(runtime_settings.get_effective(db, "publish.posts_per_page_per_day") or 0)
        except Exception:
            cap = int(getattr(config, "POSTS_PER_PAGE_PER_DAY", 0) or 0)

        tz = getattr(config, "TIMEZONE", "Asia/Ho_Chi_Minh")
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            now_dt = datetime.datetime.now(ZoneInfo(tz))
        except Exception:
            pass
        today_start = int(datetime.datetime.combine(now_dt.date(), datetime.time.min, tzinfo=getattr(now_dt, "tzinfo", None)).timestamp())

        rows = (
            db.query(Job.target_page, func.count(Job.id))
            .filter(Job.target_page.isnot(None), Job.status == JobStatus.DONE, Job.finished_at >= today_start)
            .group_by(Job.target_page)
            .order_by(func.count(Job.id).desc())
            .limit(50)
            .all()
        )

        stats = []
        for page_url, done_cnt in rows:
            used = int(done_cnt or 0)
            remaining = None
            if cap > 0:
                remaining = max(0, cap - used)
            stats.append({
                "page_url": page_url,
                "used": used,
                "cap": cap,
                "remaining": remaining,
            })

        return {
            "today_start": today_start,
            "cap": cap,
            "stats": stats,
        }

    @staticmethod
    def get_page_reup_stats(db: Session) -> Dict[str, Any]:
        try:
            cap = int(runtime_settings.get_effective(db, "publish.reup_videos_per_page_per_day") or 0)
        except Exception:
            cap = int(getattr(config, "REUP_VIDEOS_PER_PAGE_PER_DAY", 0) or 0)

        tz = getattr(config, "TIMEZONE", "Asia/Ho_Chi_Minh")
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        try:
            from zoneinfo import ZoneInfo
            now_dt = datetime.datetime.now(ZoneInfo(tz))
        except Exception:
            pass
        today_start = int(datetime.datetime.combine(now_dt.date(), datetime.time.min, tzinfo=getattr(now_dt, "tzinfo", None)).timestamp())

        reup_dir = str(config.REUP_DIR).rstrip("/")
        like_reup = f"{reup_dir}/%"
        active_statuses = [JobStatus.AWAITING_STYLE, JobStatus.AI_PROCESSING, JobStatus.DRAFT, JobStatus.PENDING, JobStatus.RUNNING]

        page_name_index: dict[str, str] = {}
        try:
            accounts = db.query(Account).all()
            for acc in accounts:
                for p in (acc.managed_pages_list or []):
                    p_url = AccountService.normalize_page_url(p.get("url"))
                    if not p_url:
                        continue
                    if p.get("name") and p_url not in page_name_index:
                        page_name_index[p_url] = str(p.get("name"))
        except Exception:
            page_name_index = {}

        rows_active = (
            db.query(Job.target_page, func.count(Job.id))
            .filter(
                Job.target_page.isnot(None),
                Job.status.in_(active_statuses),
                Job.created_at >= today_start,
                (Job.media_path.ilike(like_reup) | Job.processed_media_path.ilike(like_reup)),
            )
            .group_by(Job.target_page)
            .all()
        )
        active_map = {str(tp): int(cnt or 0) for tp, cnt in rows_active if tp}

        rows_done = (
            db.query(Job.target_page, func.count(Job.id))
            .filter(
                Job.target_page.isnot(None),
                Job.status == JobStatus.DONE,
                Job.finished_at >= today_start,
                (Job.media_path.ilike(like_reup) | Job.processed_media_path.ilike(like_reup)),
            )
            .group_by(Job.target_page)
            .all()
        )
        done_map = {str(tp): int(cnt or 0) for tp, cnt in rows_done if tp}

        pages = sorted(
            {*(active_map.keys()), *(done_map.keys())},
            key=lambda p: (-(active_map.get(p, 0) + done_map.get(p, 0)), p),
        )

        stats = []
        for page_url in pages[:50]:
            norm = AccountService.normalize_page_url(page_url)
            used = int(active_map.get(page_url, 0) + done_map.get(page_url, 0))
            remaining = None
            if cap > 0:
                remaining = max(0, cap - used)
            stats.append({
                "page_url": page_url,
                "page_name": page_name_index.get(norm) or "",
                "used": used,
                "cap": cap,
                "remaining": remaining,
                "active": int(active_map.get(page_url, 0)),
                "done": int(done_map.get(page_url, 0)),
            })

        return {
            "today_start": today_start,
            "cap": cap,
            "stats": stats,
        }

    @staticmethod
    def get_ai_analytics(db: Session) -> List[IncidentGroup]:
        return (
            db.query(IncidentGroup)
            .order_by(
                IncidentGroup.occurrence_count.desc(),
                IncidentGroup.last_seen_at.desc(),
            )
            .limit(50)
            .all()
        )

    @staticmethod
    def acknowledge_incident(db: Session, signature: str) -> IncidentGroup | None:
        group = db.query(IncidentGroup).filter(IncidentGroup.error_signature == signature).first()
        if group:
            group.status = "acknowledged"
            group.acknowledged_by = "dashboard"
            group.acknowledged_at = datetime.datetime.now(datetime.timezone.utc)
            db.commit()
            db.refresh(group)
        return group

    @staticmethod
    def get_viral_materials(
        db: Session, 
        page: int = 1, 
        per_page: int = 100, 
        q: str = "", 
        status: str = "", 
        platform: str = "", 
        min_views: int = 0
    ) -> Dict[str, Any]:
        per_page = max(50, min(200, int(per_page or 100)))
        page = max(1, int(page or 1))
        q = (q or "").strip()
        status = (status or "").strip()
        platform = (platform or "").strip()
        min_views = int(min_views or 0)

        query = db.query(ViralMaterial)
        if platform:
            query = query.filter(ViralMaterial.platform == platform)
        if status:
            query = query.filter(ViralMaterial.status == status)
        if min_views > 0:
            query = query.filter(ViralMaterial.views >= min_views)
        if q:
            query = query.filter(ViralMaterial.url.ilike(f"%{q}%"))

        total = query.count()
        total_pages = max(1, int(math.ceil(total / per_page))) if total else 1
        page = min(page, total_pages)

        items = (
            query.order_by(ViralMaterial.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
            .all()
        )
        accounts = {acc.id: acc.name for acc in db.query(Account).all()}
        from app.features.viral_intake.service import ViralService

        reup_by_id = ViralService.batch_reup_by_id(db, items)
        jobs_by_id = ViralService.batch_jobs_by_material(db, {it.id for it in items})
        banner = ViralService.pipeline_banner(db)

        return {
            "items": [
                {
                    "item": it,
                    "account_name": accounts.get(it.scraped_by_account_id, "Unknown"),
                    "has_reup": bool(reup_by_id.get(it.id)),
                    "job": jobs_by_id.get(it.id),
                }
                for it in items
            ],
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            **banner,
        }

    @staticmethod
    def get_queue_stats(db: Session) -> Dict[str, Any]:
        rows = db.execute(text("SELECT status, COUNT(*) FROM jobs GROUP BY status")).fetchall()
        counts = {str(s): int(c) for s, c in rows}
        viral_new = db.query(ViralMaterial).filter(ViralMaterial.status == ViralStatus.NEW).count()
        viral_failed = db.query(ViralMaterial).filter(ViralMaterial.status == ViralStatus.FAILED).count()
        return {
            "counts": counts,
            "viral_new": viral_new,
            "viral_failed": viral_failed,
        }

    @staticmethod
    def get_discovery_channels(db: Session) -> List[DiscoveredChannel]:
        return (
            db.query(DiscoveredChannel)
            .options(selectinload(DiscoveredChannel.account))
            .filter(DiscoveredChannel.status == ViralStatus.NEW)
            .order_by(DiscoveredChannel.score.desc())
            .all()
        )

    @staticmethod
    def approve_discovery(db: Session, channel_id: int, target_page: str = "") -> List[DiscoveredChannel]:
        channel = db.query(DiscoveredChannel).filter(DiscoveredChannel.id == channel_id).first()
        if channel and channel.status == ViralStatus.NEW:
            channel.status = "APPROVED"
            account = channel.account
            if account:
                AccountService.append_competitor_url_if_missing(
                    account,
                    channel.channel_url,
                    target_page if target_page else None,
                )
            db.commit()
        return DashboardService.get_discovery_channels(db)

    @staticmethod
    def reject_discovery(db: Session, channel_id: int) -> List[DiscoveredChannel]:
        channel = db.query(DiscoveredChannel).filter(DiscoveredChannel.id == channel_id).first()
        if channel and channel.status == ViralStatus.NEW:
            channel.status = "REJECTED"
            db.commit()
        return DashboardService.get_discovery_channels(db)

    @staticmethod
    def run_force_discovery(db: Session) -> Tuple[List[DiscoveredChannel], List[str], int]:
        total_found, scan_log = feature_hooks.call("viral.force_discovery", db)
        channels = DashboardService.get_discovery_channels(db)
        return channels, scan_log, total_found

    @staticmethod
    def get_settings_context(db: Session, query_params: Dict[str, Any] = None) -> Dict[str, Any]:
        grouped = runtime_settings.list_specs_for_settings_ui()
        overrides = runtime_settings.get_overrides(db, use_cache=False)
        effective: dict[str, dict] = {}
        for key, spec in runtime_settings.SETTINGS.items():
            default_val = spec.default_getter()
            has_override = key in overrides
            ov = overrides.get(key, None)
            # Secrets: don't echo into HTML value attrs — placeholder + keep_blank on save
            display_override = ov
            display_default = default_val
            if spec.is_secret:
                display_override = "" if ov else None
                display_default = ""
            effective[key] = {
                "key": key,
                "type": spec.type,
                "title": spec.title,
                "section": spec.section,
                "description": spec.description,
                "default": display_default if spec.is_secret else default_val,
                "override": display_override if spec.is_secret else ov,
                "has_value": bool(str(ov if has_override else default_val or "").strip()),
                "has_override": has_override,
                "min": spec.min,
                "max": spec.max,
                "choices": spec.choices or [],
                "enum_labels": spec.enum_labels or {},
                "unit": spec.unit,
                "source": runtime_settings.resolve_setting_source(spec, has_override),
                "is_secret": spec.is_secret,
                "keep_blank": spec.keep_blank,
                "restart_required": spec.restart_required,
                "env_only": spec.env_only,
                "pair_with": spec.pair_with,
            }
        section_counts = {
            sec: runtime_settings.section_visible_count(specs) for sec, specs in grouped.items()
        }
        return {
            "sections": grouped,
            "effective": effective,
            "section_counts": section_counts,
            "pair_skip": runtime_settings.pair_secondary_keys(),
            "message": (query_params or {}).get("m") or "",
        }

    @staticmethod
    def bulk_save_settings(db: Session, form_data: Dict[str, Any], updated_by: str = None) -> Dict[str, int]:
        overrides = runtime_settings.get_overrides(db, use_cache=False)
        changed = 0
        reset = 0

        for key in runtime_settings.SETTINGS.keys():
            spec = runtime_settings.SETTINGS[key]
            if spec.env_only or key not in form_data:
                continue

            raw = form_data.get(key)
            raw_s = "" if raw is None else str(raw).strip()

            # Password / secret: empty submit = keep current (do not wipe / reset)
            if (spec.keep_blank or spec.is_secret) and raw_s == "":
                continue

            try:
                v = runtime_settings.normalize_for_compare(key, raw)
                d = runtime_settings.default_value(key)
            except Exception:
                continue

            if v == d:
                if key in overrides:
                    runtime_settings.reset_setting(db, key=key, updated_by=updated_by)
                    reset += 1
                continue

            runtime_settings.upsert_setting(db, key=key, raw_value=str(raw), updated_by=updated_by)
            changed += 1

        if changed or reset:
            runtime_settings.load_runtime_settings_into_process(db)

        return {"changed": changed, "reset": reset}

    @staticmethod
    def get_ai_report_data(db: Session) -> Dict[str, Any]:
        from datetime import datetime, timedelta, timezone
        from app.core.ai.use_cases import AIUseCases

        since = datetime.now(timezone.utc) - timedelta(days=1)
        groups = (
            db.query(IncidentGroup)
            .filter(
                IncidentGroup.last_seen_at >= since,
                IncidentGroup.status.in_(["open", "acknowledged"]),
            )
            .order_by(IncidentGroup.occurrence_count.desc())
            .limit(20)
            .all()
        )

        if not groups:
            return {"groups": [], "text": None, "meta": {}}

        try:
            text, meta = AIUseCases.generate_incident_report(groups)
            return {"groups": groups, "text": text, "meta": meta}
        except Exception as exc:
            return {"groups": groups, "text": None, "meta": {"ok": False, "fail_reason": str(exc)}}

    @staticmethod
    def get_chart_data(db: Session) -> Dict[str, Any]:
        tz_str = getattr(config, "TIMEZONE", "Asia/Ho_Chi_Minh")
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(tz_str)
        except Exception:
            tz = datetime.timezone.utc
            
        now = datetime.datetime.now(tz)
        categories = []
        queued_data = []
        published_data = []
        
        for i in range(6, -1, -1):
            target_date = now - datetime.timedelta(days=i)
            start_dt = datetime.datetime.combine(target_date.date(), datetime.time.min, tzinfo=tz)
            end_dt = start_dt + datetime.timedelta(days=1)
            
            start_ts = int(start_dt.timestamp())
            end_ts = int(end_dt.timestamp())
            
            categories.append(target_date.strftime("%a"))
            queued_data.append(db.query(Job).filter(Job.created_at >= start_ts, Job.created_at < end_ts).count())
            published_data.append(db.query(Job).filter(Job.status == JobStatus.DONE, Job.finished_at >= start_ts, Job.finished_at < end_ts).count())
            
        return {
            "categories": categories,
            "series": [
                {"name": "Hàng đợi", "data": queued_data},
                {"name": "Đã đăng", "data": published_data}
            ]
        }
