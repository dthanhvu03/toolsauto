import unittest
from datetime import datetime, time as time_obj
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from zoneinfo import ZoneInfo

from app.database.core import Base
from app.database.models import Job, Account
from app.constants import JobStatus
import app.config as config
from workers.publisher import process_single_job

class TestDailyLimitPostpone(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        
        # Override config exactly for our test scopes
        config.MAX_CONCURRENT_ACCOUNTS = 2

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    @patch('workers.publisher.SystemMonitorService.check_health')
    def test_daily_limit_postpones_job_and_preserves_target_page(self, mock_health):
        mock_health.return_value = {"ram_percent": 50, "chrome_playwright_count": 0}
        
        today_start = int(datetime.combine(datetime.now(ZoneInfo(config.TIMEZONE)).date(), time_obj.min).timestamp())
        
        account = Account(
            id=1, 
            name="AccLimitTest", 
            platform="facebook",
            target_pages='["PageA", "PageB"]',
            daily_limit=1,
            is_active=True,
            login_status="ACTIVE"
        )
        self.db.add(account)
        self.db.commit()
        
        # 1 job already DONE for PageA today
        done_job = Job(
            id=1,
            account_id=1,
            platform="facebook",
            target_page="PageA",
            status=JobStatus.DONE,
            finished_at=today_start + 10,
            job_type="POST"
        )
        
        # The new PENDING job intended for PageA
        pending_job = Job(
            id=2,
            account_id=1,
            platform="facebook",
            target_page="PageA",
            status=JobStatus.PENDING,
            job_type="POST",
            schedule_ts=today_start - 3600
        )
        
        self.db.add_all([done_job, pending_job])
        self.db.commit()
        
        # Process the single job
        result = process_single_job(self.db)
        
        # Verify it claimed and processed
        self.assertTrue(result, "Should process a job")
        
        # Check Job 2
        self.db.expire_all()
        refreshed_job = self.db.query(Job).filter(Job.id == 2).first()
        
        # Verify it was postponed to tomorrow, NOT reassigned to PageB
        self.assertEqual(refreshed_job.target_page, "PageA", "Target page MUST remain PageA!")
        self.assertEqual(refreshed_job.status, JobStatus.PENDING, "Job must be set back to PENDING")
        
        expected_schedule = today_start + 86400 + 3600
        self.assertEqual(refreshed_job.schedule_ts, expected_schedule, "Job must be scheduled for tomorrow 1AM")

if __name__ == '__main__':
    unittest.main()
