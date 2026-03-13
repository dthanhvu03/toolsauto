import unittest
import random
from unittest.mock import patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database.core import Base
from app.database.models import Job, Account
import app.config as config
from workers.publisher import process_single_job

class TestConcurrentLimit(unittest.TestCase):
    def setUp(self):
        # RULE: ALWAYS USE IN-MEMORY DB FOR TESTS (No destructive operations)
        self.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db = self.Session()
        
        # Override config exactly for our test scopes
        config.MAX_CONCURRENT_ACCOUNTS = 2
        config.POST_DELAY_MIN_SEC = 30
        config.POST_DELAY_MAX_SEC = 90

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(self.engine)

    def test_limit_blocks_3rd_job(self):
        # Insert 3 Fake Accounts
        self.db.add_all([
            Account(id=1, name="Acc1", platform="facebook"),
            Account(id=2, name="Acc2", platform="facebook"),
            Account(id=3, name="Acc3", platform="facebook")
        ])
        self.db.commit()
        
        # Setup Queue: 2 are RUNNING on Facebook, 1 is PENDING
        self.db.add_all([
            Job(id=1, status="RUNNING", platform="facebook", account_id=1),
            Job(id=2, status="RUNNING", platform="facebook", account_id=2),
            Job(id=3, status="PENDING", platform="facebook", account_id=3)
        ])
        self.db.commit()
        
        # Try to process_single_job which claims PENDING tasks
        result = process_single_job(self.db)
        
        # MUST return False because running_fb_count (2) >= MAX_CONCURRENT_ACCOUNTS (2)
        # Even though there's a PENDING job available.
        self.assertFalse(result, "Job 3 should not be processed. Concurrent limit reached.")

    def test_random_delay_range(self):
        delays = set()
        for _ in range(10):
            d = random.randint(config.POST_DELAY_MIN_SEC, config.POST_DELAY_MAX_SEC)
            self.assertTrue(30 <= d <= 90, "Delay must be within 30-90 seconds")
            delays.add(d)
        
        # Verify that delays are actually randomizing
        self.assertTrue(len(delays) > 1, "There should be multiple distinct delays")

if __name__ == '__main__':
    unittest.main()
