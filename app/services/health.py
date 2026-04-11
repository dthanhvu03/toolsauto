import time
import psutil
from sqlalchemy.orm import Session
from sqlalchemy import func, case, and_
from app.database.models import SystemState, Job, Account
from app.constants import AccountStatus, JobStatus


class HealthService:
    @staticmethod
    def get_system_health(db: Session, orphan_threshold_seconds: int = 300) -> dict:
        """
        Executes fast indexed count aggregations to evaluate system health.
        Avoids full table fetches.
        
        Phase C upgrade:
          - Per-account 7-day rolling success rate (single aggregated SQL)
          - Worker uptime tracking
          - Metrics summary (views, clicks)
        """
        now = int(time.time())
        
        # 1. Worker State (Fast 1-row fetch)
        sys_state = db.query(SystemState).filter(SystemState.id == 1).first()
        worker_status = sys_state.worker_status if sys_state else "UNKNOWN"
        worker_hb = sys_state.heartbeat_at if sys_state else 0
        safe_mode = sys_state.safe_mode if sys_state else False
        worker_hb_age = now - worker_hb if worker_hb else 999999
        worker_started = sys_state.worker_started_at if sys_state else None
        uptime_seconds = (now - worker_started) if worker_started else 0
        
        # 2. Job Counters (Indexed)
        running_jobs_count = db.query(Job).filter(Job.status == JobStatus.RUNNING).count()
        orphan_jobs_count = db.query(Job).filter(
            Job.status == JobStatus.RUNNING,
            Job.last_heartbeat_at < (now - orphan_threshold_seconds)
        ).count()
        
        failed_last_24h = db.query(Job).filter(
            Job.status == JobStatus.FAILED,
            Job.finished_at >= (now - 86400)
        ).count()
        
        # 3. Account Breaker Counters (Indexed)
        disabled_accounts_count = db.query(Account).filter(
            (Account.is_active == False) | (Account.login_status != AccountStatus.ACTIVE)
        ).count()
        
        # 4. Psutil Metrics
        try:
            process = psutil.Process()
            memory_usage_mb = process.memory_info().rss / 1024 / 1024
            
            # System wide metrics
            cpu_percent = psutil.cpu_percent(interval=None)
            vm = psutil.virtual_memory()
            sys_memory_percent = vm.percent
            sys_memory_total_gb = vm.total / (1024**3)
            sys_memory_used_gb = vm.used / (1024**3)
            
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            disk_total_gb = disk.total / (1024**3)
            disk_used_gb = disk.used / (1024**3)

            browser_process_count = sum(
                1 for p in psutil.process_iter(['name']) 
                if "playwright" in p.info.get('name', '').lower() or "chrome" in p.info.get('name', '').lower()
            )
        except Exception:
            memory_usage_mb = 0
            browser_process_count = 0
            cpu_percent = 0
            sys_memory_percent = 0
            sys_memory_total_gb = 0
            sys_memory_used_gb = 0
            disk_percent = 0
            disk_total_gb = 0
            disk_used_gb = 0

        # 5. Per-Account Health — 7-day rolling (SINGLE aggregated SQL, no N+1)
        seven_days_ago = now - 604800
        
        account_stats_raw = (
            db.query(
                Account.id,
                Account.name,
                Account.platform,
                Account.is_active,
                Account.login_status,
                Account.consecutive_fatal_failures,
                func.count(case((and_(Job.status == JobStatus.DONE, Job.finished_at >= seven_days_ago), 1))).label("done_7d"),
                func.count(case((and_(Job.status == JobStatus.FAILED, Job.finished_at >= seven_days_ago), 1))).label("failed_7d"),
            )
            .outerjoin(Job, and_(Job.account_id == Account.id, Job.finished_at >= seven_days_ago))
            .group_by(Account.id)
            .all()
        )
        
        account_stats = []
        for row in account_stats_raw:
            total = row.done_7d + row.failed_7d
            success_rate = round(row.done_7d / total * 100, 1) if total > 0 else 0
            account_stats.append({
                "id": row.id,
                "name": row.name,
                "platform": row.platform,
                "is_active": row.is_active,
                "login_status": row.login_status,
                "done_7d": row.done_7d,
                "failed_7d": row.failed_7d,
                "success_rate": success_rate,
                "circuit_breaker": row.consecutive_fatal_failures,
            })
        
        # 6. Metrics Overview (Phase 14+15 data)
        total_views = db.query(func.sum(Job.view_24h)).filter(Job.view_24h != None).scalar() or 0
        total_clicks = db.query(func.sum(Job.click_count)).filter(Job.click_count != None, Job.click_count > 0).scalar() or 0
        avg_views = db.query(func.avg(Job.view_24h)).filter(Job.view_24h != None).scalar() or 0
        
        posts_with_metrics = db.query(Job).filter(Job.metrics_checked == True).count()

        # === DETERMINISTIC DEGRADATION LOGIC ===
        status = "ok"
        degradation_reasons = []

        if worker_status != JobStatus.RUNNING:
            status = "degraded"
            degradation_reasons.append(f"Worker is {worker_status}")
            
        if worker_hb_age > 120 and worker_status == JobStatus.RUNNING: # 2 minutes dead
            status = "degraded"
            degradation_reasons.append(f"Worker heartbeat stale ({worker_hb_age}s)")

        if orphan_jobs_count > 0:
            status = "degraded"
            degradation_reasons.append(f"Detected {orphan_jobs_count} orphan jobs")

        if failed_last_24h > 10:
            status = "degraded"
            degradation_reasons.append(f"High failure rate ({failed_last_24h} in 24h)")
            
        if disabled_accounts_count > 0:
            status = "degraded"
            degradation_reasons.append(f"{disabled_accounts_count} accounts are disabled or invalid")

        return {
            "status": status,
            "reasons": degradation_reasons,
            "worker": {
                "status": worker_status,
                "heartbeat_age_seconds": worker_hb_age,
                "safe_mode": safe_mode,
                "uptime_seconds": uptime_seconds,
                "uptime_hours": round(uptime_seconds / 3600, 1),
            },
            "jobs": {
                "running": running_jobs_count,
                "orphans": orphan_jobs_count,
                "failed_24h": failed_last_24h
            },
            "accounts": {
                "disabled_or_invalid": disabled_accounts_count,
                "details": account_stats,
            },
            "metrics": {
                "total_views": total_views,
                "total_clicks": total_clicks,
                "avg_views_per_post": round(avg_views, 1),
                "posts_checked": posts_with_metrics,
            },
            "system": {
                "memory_mb": round(memory_usage_mb, 2),
                "browser_processes": browser_process_count,
                "cpu_percent": round(cpu_percent, 1),
                "sys_memory_percent": round(sys_memory_percent, 1),
                "sys_memory_total_gb": round(sys_memory_total_gb, 1),
                "sys_memory_used_gb": round(sys_memory_used_gb, 1),
                "disk_percent": round(disk_percent, 1),
                "disk_total_gb": round(disk_total_gb, 1),
                "disk_used_gb": round(disk_used_gb, 1),
            }
        }
