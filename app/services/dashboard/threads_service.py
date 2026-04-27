import logging
import time
from typing import Any, Dict, List, Tuple
from sqlalchemy.orm import Session
from app.database.models import Account, Job, NewsArticle, RuntimeSetting
from app.constants import JobType, JobStatus

logger = logging.getLogger(__name__)

class ThreadsService:

    @staticmethod
    def _platform_tokens(platform: str | None) -> set[str]:
        return {token.strip().lower() for token in (platform or "").split(",") if token.strip()}

    @staticmethod
    def classify_accounts(db: Session, all_accounts: List[Account]) -> Tuple[List[Account], List[Account], Dict[int, str], List[Account]]:
        """
        Classify Facebook accounts into 3 buckets for Threads connection UI.
        """
        linked_accounts = []
        verifying_accounts = []
        failed_verifications = {}
        available_accounts = []

        for acc in all_accounts:
            platforms = ThreadsService._platform_tokens(acc.platform)
            if "facebook" not in platforms:
                continue

            if "threads" in platforms:
                linked_accounts.append(acc)
                continue

            # Check for active verification jobs
            active_verify = db.query(Job).filter(
                Job.account_id == acc.id,
                Job.job_type == JobType.VERIFY_THREADS,
                Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
            ).first()

            if active_verify:
                verifying_accounts.append(acc)
                continue

            # Check for most recent failed verification
            failed_verify = db.query(Job).filter(
                Job.account_id == acc.id,
                Job.job_type == JobType.VERIFY_THREADS,
                Job.status == JobStatus.FAILED
            ).order_by(Job.id.desc()).first()

            if failed_verify:
                failed_verifications[acc.id] = failed_verify.last_error or "Xác minh thất bại"
                available_accounts.append(acc)
                continue

            available_accounts.append(acc)

        return linked_accounts, verifying_accounts, failed_verifications, available_accounts

    @staticmethod
    def get_dashboard_data(db: Session) -> Dict[str, Any]:
        stats = {
            "pending": db.query(Job).filter(Job.platform == "threads", Job.status == "PENDING").count(),
            "success": db.query(Job).filter(Job.platform == "threads", Job.status == "COMPLETED").count(),
            "failed": db.query(Job).filter(Job.platform == "threads", Job.status == "FAILED").count(),
        }
        latest_articles = db.query(NewsArticle).order_by(NewsArticle.id.desc()).limit(10).all()
        threads_jobs = db.query(Job).filter(Job.platform == "threads").order_by(Job.id.desc()).limit(10).all()
        
        all_accounts = db.query(Account).filter(Account.is_active == True).order_by(Account.id.asc()).all()
        linked, verifying, failed, available = ThreadsService.classify_accounts(db, all_accounts)
        
        return {
            "stats": stats,
            "articles": latest_articles,
            "jobs": threads_jobs,
            "linked_accounts": linked,
            "verifying_accounts": verifying,
            "failed_verifications": failed,
            "available_accounts": available,
        }

    @staticmethod
    def get_news_panel_data(db: Session) -> Dict[str, Any]:
        auto_mode_setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == "THREADS_AUTO_MODE").first()
        auto_mode = (auto_mode_setting.value.lower() == "true") if auto_mode_setting else False
        
        total_articles = db.query(NewsArticle).count()
        new_articles = db.query(NewsArticle).filter(NewsArticle.status == "NEW").count()
        latest_jobs = db.query(Job).filter(Job.platform == "threads").order_by(Job.id.desc()).limit(3).all()
        
        return {
            "auto_mode": auto_mode,
            "total_articles": total_articles,
            "new_articles": new_articles,
            "latest_jobs": latest_jobs
        }

    @staticmethod
    def toggle_auto_mode(db: Session) -> bool:
        setting = db.query(RuntimeSetting).filter(RuntimeSetting.key == "THREADS_AUTO_MODE").first()
        if setting:
            current_val = setting.value.lower() == "true"
            new_val = not current_val
            setting.value = "true" if new_val else "false"
        else:
            new_val = True
            setting = RuntimeSetting(key="THREADS_AUTO_MODE", value="true", type="bool")
            db.add(setting)
        db.commit()
        return new_val

    @staticmethod
    def link_account(db: Session, account_id: int) -> bool:
        account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
        if not account:
            return False

        platforms = ThreadsService._platform_tokens(account.platform)
        if "facebook" not in platforms:
            return False

        existing = db.query(Job).filter(
            Job.account_id == account_id,
            Job.job_type == JobType.VERIFY_THREADS,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
        ).first()

        if not existing:
            old_failed = db.query(Job).filter(
                Job.account_id == account_id,
                Job.job_type == JobType.VERIFY_THREADS,
                Job.status == JobStatus.FAILED
            ).all()
            for j in old_failed:
                j.status = JobStatus.CANCELLED
            
            verify_job = Job(
                platform="threads",
                account_id=account_id,
                job_type=JobType.VERIFY_THREADS,
                status=JobStatus.PENDING,
                caption="[VERIFY] Threads login verification",
                schedule_ts=int(time.time()),
            )
            db.add(verify_job)
            db.commit()
            logger.info("Created VERIFY_THREADS job #%s for account %s", verify_job.id, account_id)
        return True

    @staticmethod
    def cancel_verification(db: Session, account_id: int):
        active_jobs = db.query(Job).filter(
            Job.account_id == account_id,
            Job.job_type == JobType.VERIFY_THREADS,
            Job.status.in_([JobStatus.PENDING, JobStatus.RUNNING])
        ).all()

        for j in active_jobs:
            j.status = JobStatus.CANCELLED
            j.last_error = "Cancelled by user"
            j.finished_at = int(time.time())

        if active_jobs:
            db.commit()

    @staticmethod
    def retry_verification(db: Session, account_id: int) -> bool:
        account = db.query(Account).filter(Account.id == account_id, Account.is_active == True).first()
        if not account:
            return False

        old_jobs = db.query(Job).filter(
            Job.account_id == account_id,
            Job.job_type == JobType.VERIFY_THREADS,
            Job.status == JobStatus.FAILED
        ).all()
        for j in old_jobs:
            j.status = JobStatus.CANCELLED

        verify_job = Job(
            platform="threads",
            account_id=account_id,
            job_type=JobType.VERIFY_THREADS,
            status=JobStatus.PENDING,
            caption="[VERIFY] Threads login verification (retry)",
            schedule_ts=int(time.time()),
        )
        db.add(verify_job)
        db.commit()
        return True

    @staticmethod
    def unlink_account(db: Session, account_id: int):
        account = db.query(Account).filter(Account.id == account_id).first()
        if account:
            platforms = ThreadsService._platform_tokens(account.platform)
            platforms.discard("threads")
            account.platform = ",".join(sorted(platforms)) or "facebook"
            db.commit()
    @staticmethod
    def trigger_news_scrape(db: Session):
        from app.services.news_scraper import NewsScraper
        from app.services.threads_news import ThreadsNewsService
        
        try:
            scraper = NewsScraper()
            scraper.scrape_all()
            
            service = ThreadsNewsService()
            service.process_news_to_threads()
            return True
        except Exception as e:
            logger.error("trigger_news_scrape error: %s", e)
            return False
