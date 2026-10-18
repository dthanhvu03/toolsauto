import pytest
from unittest.mock import patch, MagicMock
from app.core.observability.workflow_registry import WorkflowRegistry

class TestWorkflowRegistryCacheShape:

    @patch("app.database.core.SessionLocal")
    def test_selector_cache_grouping_includes_name(self, mock_session):
        # Giả lập kết quả trả về của DB khi _load_all() quét bảng platform_selectors
        # Cấu trúc row trả về: id, platform, category, selector_name, selector_type, selector_value, locale, priority, notes
        mock_db = MagicMock()
        mock_session.return_value = mock_db
        
        mock_db.execute.return_value.fetchall.side_effect = [
            # Query 1: Platforms
            [],
            # Query 2: Workflows
            [],
            # Query 3: Selectors
            [
                (1, "facebook", "post", "post_button", "css", ".fb-post-btn", "en", 10, ""),
                (2, "facebook", "post", "caption_field", "css", ".fb-input", "en", 9, "")
            ],
            # Query 4: CTA templates
            []
        ]
        
        # Ép chạy lại _load_all() để hứng data
        from app.core.observability.workflow_registry import _load_all
        data = _load_all()
        print("DEBUG _load_all data:", data)
        
        # Rút trích dict được cache
        selectors = data.get("selectors", {})
        
        # KỲ VỌNG: 2 selector khác name nhưng chung category phải bị đẩy vào 2 key RIÊNG BIỆT 
        # (Nghĩa là key phải có dạng {platform}:{category}:{selector_name})
        assert "facebook:post:post_button" in selectors, "Bug cũ tái hiện! Thiếu selector_name trong cache key!"
        assert "facebook:post:caption_field" in selectors, "Bug cũ tái hiện! Thiếu selector_name trong cache key!"
        
        assert len(selectors["facebook:post:post_button"]) == 1
        assert selectors["facebook:post:post_button"][0].selector_value == ".fb-post-btn"
        
        assert len(selectors["facebook:post:caption_field"]) == 1
        assert selectors["facebook:post:caption_field"][0].selector_value == ".fb-input"

    @patch("app.services.workflow_registry._get_cache")
    def test_get_selector_values_matches_shape(self, mock_get_cache):
        # Trực tiếp giả lập kết quả của _get_cache để test API public
        from app.core.observability.workflow_registry import SelectorItem
        
        mock_get_cache.return_value = {
            "selectors": {
                "facebook:recovery:session_recovery_button": [
                    SelectorItem(id=1, name="session_recovery_button", selector_type="css", selector_value="db_val", locale="*", priority=10, notes="")
                ]
            },
            "cta": {}
        }
        
        # Test xem get_selector_values khi gọi kiểu n8n-lite có ăn khớp với DB cache shape hay không
        vals = WorkflowRegistry.get_selector_values("facebook", "recovery:session_recovery_button")
        
        assert len(vals) == 1
        assert vals[0] == "db_val"
