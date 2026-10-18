import pytest
from unittest.mock import patch, MagicMock
from app.adapters.dispatcher import Dispatcher
from app.features.facebook.adapter import FacebookAdapter

class TestN8nLitePhase2:
    
    @patch('app.services.workflow_registry.WorkflowRegistry.get_cta_templates')
    def test_cta_injection_with_valid_template(self, mock_get_cta):
        mock_get_cta.return_value = ["Cùng xem ngay: {link}"]
        
        # Text chỉ chứa link, hợp lệ để bọc CTA
        raw_text = "https://example.com"
        result = Dispatcher._inject_cta("facebook", raw_text)
        
        assert result == "Cùng xem ngay: https://example.com"
        mock_get_cta.assert_called_once_with("facebook", locale="vi")

    @patch('app.services.workflow_registry.WorkflowRegistry.get_cta_templates')
    def test_cta_injection_fallback_on_db_empty(self, mock_get_cta):
        mock_get_cta.return_value = [] # DB trả về rỗng
        
        raw_text = "https://example.com"
        result = Dispatcher._inject_cta("facebook", raw_text)
        
        # Nếu DB rỗng, nó fallback về list nội tại của FB Adapter
        # Mình chỉ cần assert nó khác raw_text (vì đã được nhét vô CTA)
        assert "{link}" not in result
        assert "https://example.com" in result
        assert result != raw_text

    @patch('app.services.workflow_registry.WorkflowRegistry.get_cta_templates')
    def test_cta_injection_ignores_custom_comment(self, mock_get_cta):
        # Text chứa chữ do user gõ, không phải raw link
        raw_text = "Bài viết hay quá\nhttps://example.com"
        result = Dispatcher._inject_cta("facebook", raw_text)
        
        assert result == raw_text
        mock_get_cta.assert_not_called()
