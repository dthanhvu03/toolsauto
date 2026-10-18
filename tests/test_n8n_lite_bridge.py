import pytest
import logging
from unittest.mock import patch, MagicMock

# Import class chúng ta vừa patch
from app.features.facebook.adapter import FacebookAdapter

@pytest.fixture
def adapter():
    return FacebookAdapter()

class TestN8nLiteWiring:

    # ---------------------------------------------------------
    # TEST 1: DB Selector Miss -> Trả về chuẩn Static Fallback
    # ---------------------------------------------------------
    @patch("app.services.workflow_registry.WorkflowRegistry.get_selector_values")
    def test_selector_miss_fallback_static(self, mock_get_selector, adapter):
        # Giả lập DB rỗng
        mock_get_selector.return_value = []
        static_fallback = 'div[role="button"]:has-text("Tiếp tục"), div[id="old"]'
        
        result = adapter._get_dynamic_selectors("recovery", "session_recovery_button", static_fallback)
        
        # Mong đợi array fallback tĩnh không bị lộn xộn
        assert len(result) == 2
        assert result[0] == 'div[role="button"]:has-text("Tiếp tục")'
        assert result[1] == 'div[id="old"]'


    # ---------------------------------------------------------
    # TEST 2: DB Selector Hit -> Gom với Static Fallback
    # ---------------------------------------------------------
    @patch("app.services.workflow_registry.WorkflowRegistry.get_selector_values")
    def test_selector_hit_prepends_db(self, mock_get_selector, adapter):
        # Giả lập Admin vừa config 1 selector mới ưu tiên cao trên Web UI
        mock_get_selector.return_value = ['div[aria-label="Continue"]']
        
        static_fallback = 'div[role="button"]:has-text("Tiếp tục")'
        
        result = adapter._get_dynamic_selectors("recovery", "session_recovery_button", static_fallback)
        
        # Mong đợi thẻ mới từ DB phải nằm ưu tiên số 1 Array (index 0)
        assert len(result) == 2
        assert result[0] == 'div[aria-label="Continue"]'
        assert result[1] == 'div[role="button"]:has-text("Tiếp tục")'


    # ---------------------------------------------------------
    # TEST 3: Registry Throw Error -> Không làm gãy luồng
    # ---------------------------------------------------------
    @patch("app.services.workflow_registry.WorkflowRegistry.get_selector_values")
    def test_registry_error_safe_fallback(self, mock_get_selector, adapter):
        # Giả lập kết nối Redis/SQLite hỏng văng Exception
        mock_get_selector.side_effect = Exception("DB Connection Lost")
        
        static_fallback = 'test_fallback'
        
        # Nhờ try/except trong _get_dynamic_selectors, exception sẽ được nuốt và fallback tĩnh sẽ được xài.
        result = adapter._get_dynamic_selectors("recovery", "session_recovery", static_fallback)
        assert len(result) == 1
        assert result[0] == 'test_fallback'

    # ---------------------------------------------------------
    # TEST 4: Timing Hit -> Lấy Setting mới từ admin
    # ---------------------------------------------------------
    @patch("app.services.workflow_registry.WorkflowRegistry.get_timing")
    def test_timing_hit(self, mock_get_timing, adapter):
        # Giả lập config giảm timing trên Admin UI
        mock_get_timing.return_value = 2000 
        
        val = adapter._get_dynamic_timing("upload_settle_wait", 8000)
        assert val == 2000

    # ---------------------------------------------------------
    # TEST 5: Timing Miss -> Trả về literal an toàn
    # ---------------------------------------------------------
    @patch("app.services.workflow_registry.WorkflowRegistry.get_timing")
    def test_timing_miss_fallback(self, mock_get_timing, adapter):
        # Giả lập chưa ai config timing này trên admin
        def side_effect(platform, job_type, key, default):
            return default
            
        mock_get_timing.side_effect = side_effect
        
        val = adapter._get_dynamic_timing("feed_browse_pause", 4000)
        assert val == 4000
