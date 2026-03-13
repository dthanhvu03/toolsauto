import unittest
import time
from unittest.mock import patch, MagicMock
from app.services.gemini_rpa import GeminiRPAService, GeminiMaxRetriesExceeded

class TestGeminiRetry(unittest.TestCase):
    @patch('app.services.gemini_rpa.time.sleep')
    @patch('undetected_chromedriver.Chrome', autospec=True)
    def test_pass_on_second_attempt(self, mock_chrome, mock_sleep):
        svc = GeminiRPAService(max_retries=3)
        # Mock _execute to fail first time, then pass
        svc._execute = MagicMock(side_effect=[Exception("Lỗi mạng mô phỏng"), "Dữ liệu AI OK"])
        
        result = svc._run_session("test prompt")
        self.assertEqual(result, "Dữ liệu AI OK")
        self.assertEqual(svc._execute.call_count, 2)

    @patch('app.services.gemini_rpa.time.sleep')
    @patch('undetected_chromedriver.Chrome', autospec=True)
    def test_fail_all_3_attempts(self, mock_chrome, mock_sleep):
        svc = GeminiRPAService(max_retries=3)
        svc._execute = MagicMock(side_effect=[Exception("Fail 1"), Exception("Fail 2"), Exception("Fail 3")])
        
        with self.assertRaises(GeminiMaxRetriesExceeded):
            svc._run_session("test prompt")
        self.assertEqual(svc._execute.call_count, 3)

    @patch('app.services.gemini_rpa.time.sleep')
    @patch('app.services.gemini_rpa.GeminiResponseParser.extract_new_response')
    @patch('undetected_chromedriver.Chrome', autospec=True)
    def test_timeout_handled(self, mock_chrome, mock_extract, mock_sleep):
        # Simulate timeout returning None
        mock_extract.return_value = None
        svc = GeminiRPAService(max_retries=1)
        
        # Will raise exception because it failed (returns None inside _run_session, raising Exception)
        with self.assertRaises(GeminiMaxRetriesExceeded):
            svc._run_session("test prompt")

if __name__ == '__main__':
    unittest.main()
