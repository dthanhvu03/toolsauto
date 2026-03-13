import unittest
import time
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.core import Base
from app.database.models import Job, Account
from workers.ai_generator import process_draft_job
from app.services.gemini_rpa import GeminiMaxRetriesExceeded
from workers.publisher import check_crash_recovery

class TestIntegration(unittest.TestCase):
    def setUp(self):
        # RULE: ALWAYS USE IN-MEMORY DB FOR TESTS (No destructive operations)
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        
    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    @patch('app.services.content_orchestrator.ContentOrchestrator.generate_caption')
    @patch('app.services.notifier.NotifierService._broadcast')
    def test_integration_gemini_fail_marks_job_failed(self, mock_notify, mock_generate):
        # Setup isolated DB with 1 job in DRAFT requiring AI Generation
        self.db.add(Account(id=1, name="Acc1", platform="facebook"))
        self.db.add(Job(id=10, status="DRAFT", platform="facebook", account_id=1, caption="Test [AI_GENERATE]"))
        self.db.commit()
        
        # Simulate Exception from Gemini Wrapper
        mock_generate.side_effect = GeminiMaxRetriesExceeded("3 times failed mock")
        
        # Run worker tick action
        process_draft_job(self.db)
        
        # Assetion
        job = self.db.query(Job).filter_by(id=10).first()
        self.assertEqual(job.status, "FAILED", "Job phải chuyển sang FAILED sau 3 lần fail")
        mock_notify.assert_called()
        self.assertIn("GEMINI RPA FAILED", mock_notify.call_args[0][0])

    def test_integration_crash_recovery(self):
        # Mô phỏng Job 20 kẹt ở RUNNING với heartbeat vượt tuổi chớp tủy (>WORKER_CRASH_THRESHOLD)
        old_time = int(time.time()) - 400 # 400 giây trước (~ 6.6 phút)
        self.db.add(Account(id=1, name="Acc1"))
        self.db.add(Job(id=20, status="RUNNING", platform="facebook", account_id=1, last_heartbeat_at=old_time))
        self.db.commit()
        
        # Khởi động tick đầu tiên của Publisher
        check_crash_recovery(self.db)
        
        # Job bị reset về PENDING
        job = self.db.query(Job).filter_by(id=20).first()
        self.assertEqual(job.status, "PENDING", "Crash worker job không bị thu hồi lại PENDING")

if __name__ == '__main__':
    unittest.main()
