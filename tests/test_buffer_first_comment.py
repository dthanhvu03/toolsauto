"""Comprehensive unit tests for Milestone 1: Automated Gemini AI FirstComment for Buffer.

Covers:
- FirstComment length <= 150 characters.
- Special characters and quote stripping.
- Safe fallback on AI exception/timeout/empty response (verify one of fallback starter comments is returned).
- GraphQL mutation payload for Facebook containing firstComment.
- GraphQL mutation payload for Instagram containing firstComment.
- Strict omission of firstComment and metadata for TikTok channel (prevent 422).
- Buffer adapter publishing flow with Facebook and TikTok channels.
- AIUseCases facade FIRST_COMMENT purpose and prompt construction.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.ai.use_cases import AIPurpose, AIUseCases
from app.features.buffer.adapter import BufferAdapter
from app.features.buffer.client import BufferClient
from app.features.buffer.first_comment import (
    FALLBACK_STARTER_COMMENTS,
    get_or_create_first_comment,
    sanitize_comment,
)


def _mock_response(payload: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    return resp


# ── 1. Sanitization & Length Clamping Tests ─────────────────────────────────


def test_sanitize_comment_strips_quotes_and_codeblocks():
    # Quotes and smart quotes
    assert sanitize_comment('"Câu bình luận mẫu"') == "Câu bình luận mẫu"
    assert sanitize_comment("'Câu bình luận mẫu'") == "Câu bình luận mẫu"
    assert sanitize_comment("“Câu bình luận mẫu”") == "Câu bình luận mẫu"
    assert sanitize_comment("‘Câu bình luận mẫu’") == "Câu bình luận mẫu"
    assert sanitize_comment("«Câu bình luận mẫu»") == "Câu bình luận mẫu"
    assert sanitize_comment("`Câu bình luận mẫu`") == "Câu bình luận mẫu"

    # Markdown code blocks
    raw_block = "```\nBình luận trong code block\n```"
    assert sanitize_comment(raw_block) == "Bình luận trong code block"


def test_sanitize_comment_strips_prefixes_and_markdown():
    # Common AI prefixes
    assert sanitize_comment("First comment: Chào cả nhà!") == "Chào cả nhà!"
    assert sanitize_comment("Comment: Chào cả nhà!") == "Chào cả nhà!"
    assert sanitize_comment("Bình luận: Chào cả nhà!") == "Chào cả nhà!"
    assert sanitize_comment("Bình luận đầu tiên: Chào cả nhà!") == "Chào cả nhà!"

    # Markdown styles (bold, italic, strikethrough)
    assert sanitize_comment("**Thả tim** và *chia sẻ* nha!") == "Thả tim và chia sẻ nha!"

    # Hashtags and URLs
    dirty = "Xem video hay quá #trending #reels https://example.com/link www.fb.com nha cả nhà!"
    cleaned = sanitize_comment(dirty)
    assert "#trending" not in cleaned
    assert "#reels" not in cleaned
    assert "https://" not in cleaned
    assert "www." not in cleaned
    assert "Xem video hay quá nha cả nhà!" in cleaned

    # Markdown links
    assert sanitize_comment("Xem [tại đây](https://link.vn) nhé!") == "Xem tại đây nhé!"


def test_sanitize_comment_clamps_to_150_characters():
    # Long text (200 characters)
    long_text = "Nội dung bình luận này được viết rất dài " * 5
    assert len(long_text) > 150

    cleaned = sanitize_comment(long_text)
    assert len(cleaned) <= 150
    assert cleaned.endswith("...")


def test_sanitize_comment_empty_or_whitespace():
    assert sanitize_comment("") == ""
    assert sanitize_comment("   ") == ""
    assert sanitize_comment(None) == ""


# ── 2. Fallback Starter Pool Tests ──────────────────────────────────────────


def test_fallback_starter_comments_pool_integrity():
    assert len(FALLBACK_STARTER_COMMENTS) == 8
    for comment in FALLBACK_STARTER_COMMENTS:
        assert isinstance(comment, str)
        assert len(comment.strip()) > 0
        # Requirement: engaging starter comments < 90 chars
        assert len(comment) < 90
        # Vietnamese engagement signals
        assert any(
            word in comment
            for word in ["nhé", "nha", "nè", "cả nhà", "mọi người", "Comment", "chia sẻ", "bình luận"]
        )


def test_get_or_create_first_comment_empty_caption_fallback():
    # When caption is empty, immediately returns one of the fallback comments
    comment = get_or_create_first_comment("")
    assert comment in FALLBACK_STARTER_COMMENTS

    comment2 = get_or_create_first_comment("   ")
    assert comment2 in FALLBACK_STARTER_COMMENTS


# ── 3. AI FirstComment Generation & Safe Fallback Tests ────────────────────


def test_get_or_create_first_comment_success(monkeypatch):
    def fake_generate_first_comment(caption: str, topic: str = ""):
        return '  "Mọi người thấy video này thế nào? Comment chia sẻ nha!"  ', {
            "purpose": "first_comment",
            "provider": "gemini",
        }

    monkeypatch.setattr(AIUseCases, "generate_first_comment", fake_generate_first_comment)
    result = get_or_create_first_comment(caption="Video ẩm thực đường phố Sài Gòn", topic="ẩm thực")

    assert result == "Mọi người thấy video này thế nào? Comment chia sẻ nha!"
    assert len(result) <= 150
    assert '"' not in result


def test_get_or_create_first_comment_fallback_on_ai_exception(monkeypatch):
    def fake_generate_failing(caption: str, topic: str = ""):
        raise RuntimeError("Google GenAI 429 Quota Exceeded")

    monkeypatch.setattr(AIUseCases, "generate_first_comment", fake_generate_failing)
    result = get_or_create_first_comment(caption="Video review du lịch")

    # Safe fallback guaranteed, never raises
    assert result in FALLBACK_STARTER_COMMENTS


def test_get_or_create_first_comment_fallback_on_ai_timeout(monkeypatch):
    def fake_generate_timeout(caption: str, topic: str = ""):
        raise TimeoutError("9Router connection timed out after 10s")

    monkeypatch.setattr(AIUseCases, "generate_first_comment", fake_generate_timeout)
    result = get_or_create_first_comment(caption="Video mẹo vặt cuộc sống")

    assert result in FALLBACK_STARTER_COMMENTS


def test_get_or_create_first_comment_fallback_on_empty_ai_response(monkeypatch):
    def fake_generate_empty(caption: str, topic: str = ""):
        return None, {"purpose": "first_comment"}

    monkeypatch.setattr(AIUseCases, "generate_first_comment", fake_generate_empty)
    result = get_or_create_first_comment(caption="Video thể thao")

    assert result in FALLBACK_STARTER_COMMENTS


def test_get_or_create_first_comment_fallback_on_whitespace_ai_response(monkeypatch):
    def fake_generate_whitespace(caption: str, topic: str = ""):
        return "   \n\t  ", {"purpose": "first_comment"}

    monkeypatch.setattr(AIUseCases, "generate_first_comment", fake_generate_whitespace)
    result = get_or_create_first_comment(caption="Video thể thao")

    assert result in FALLBACK_STARTER_COMMENTS


# ── 4. BufferClient GraphQL Mutation & Metadata Tests ────────────────────────


def test_create_post_facebook_payload_with_first_comment(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["body"] = json
        return _mock_response(
            {"data": {"createPost": {"post": {"id": "fb_post_1", "text": "test", "dueAt": None}}}}
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-buffer-token")
    post = client.create_post(
        text="Caption bài đăng Facebook",
        channel_id="chan_fb_01",
        service="facebook",
        first_comment="Mọi người có thích mẫu này không ạ? 👇",
    )

    assert post["id"] == "fb_post_1"
    query = seen["body"]["query"]
    assert 'metadata: { facebook: { type: post, firstComment: "Mọi người có thích mẫu này không ạ? 👇" } }' in query
    assert "instagram:" not in query


def test_create_post_facebook_payload_without_first_comment(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["body"] = json
        return _mock_response(
            {"data": {"createPost": {"post": {"id": "fb_post_2", "text": "test", "dueAt": None}}}}
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-buffer-token")
    client.create_post(
        text="Caption bài đăng Facebook",
        channel_id="chan_fb_01",
        service="facebook",
        first_comment=None,
    )

    query = seen["body"]["query"]
    assert "metadata: { facebook: { type: post } }" in query
    assert "firstComment" not in query


def test_create_post_instagram_payload_with_first_comment(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["body"] = json
        return _mock_response(
            {"data": {"createPost": {"post": {"id": "ig_post_1", "text": "test", "dueAt": None}}}}
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-buffer-token")
    client.create_post(
        text="Reels Instagram",
        channel_id="chan_ig_01",
        service="instagram",
        first_comment="Thả tim và lưu lại nha cả nhà! ❤️",
    )

    query = seen["body"]["query"]
    assert 'metadata: { instagram: { firstComment: "Thả tim và lưu lại nha cả nhà! ❤️" } }' in query
    # Instagram does not use facebook metadata
    assert "facebook:" not in query
    assert "type: post" not in query


def test_create_post_instagram_payload_without_first_comment(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["body"] = json
        return _mock_response(
            {"data": {"createPost": {"post": {"id": "ig_post_2", "text": "test", "dueAt": None}}}}
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-buffer-token")
    client.create_post(
        text="Reels Instagram",
        channel_id="chan_ig_01",
        service="instagram",
        first_comment=None,
    )

    query = seen["body"]["query"]
    assert "metadata" not in query


def test_create_post_tiktok_strictly_omits_first_comment_and_metadata(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["body"] = json
        return _mock_response(
            {"data": {"createPost": {"post": {"id": "tt_post_1", "text": "test", "dueAt": None}}}}
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-buffer-token")
    # Even if first_comment is passed explicitly, TikTok MUST strictly omit it to prevent 422
    client.create_post(
        text="TikTok video dancing",
        channel_id="chan_tt_01",
        service="tiktok",
        first_comment="Comment này không được phép xuất hiện trên TikTok payload!",
    )

    query = seen["body"]["query"]
    assert "firstComment" not in query
    assert "metadata" not in query
    assert "facebook" not in query
    assert "instagram" not in query


def test_create_post_escapes_special_characters_in_first_comment(monkeypatch):
    seen = {}

    def fake_post(url, headers, json, timeout):
        seen["body"] = json
        return _mock_response(
            {"data": {"createPost": {"post": {"id": "esc_post_1", "text": "test", "dueAt": None}}}}
        )

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-buffer-token")

    complex_comment = 'Bình luận có "ngoặc kép", emoji 🔥 và dấu \\ gạch chéo!'
    client.create_post(
        text="Test caption",
        channel_id="chan_fb_01",
        service="facebook",
        first_comment=complex_comment,
    )

    query = seen["body"]["query"]
    # Verify valid JSON escaping in query
    assert '\\"ngoặc kép\\"' in query
    assert "🔥" in query


# ── 5. BufferAdapter Publishing Flow Tests ──────────────────────────────────


def test_adapter_publish_facebook_flow(monkeypatch):
    client = MagicMock()
    client.infer_channel_service.return_value = "facebook"
    client.create_post.return_value = {"id": "buffer_p100", "dueAt": None}

    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=100,
        caption="Video mẹo vặt nhà bếp thông minh",
        target_page="chan_fb_page",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
        ai_style="meo_vat",
    )
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)
    monkeypatch.setattr(
        "app.features.buffer.first_comment.AIUseCases.generate_first_comment",
        lambda caption, topic="": ("Có ai đã thử mẹo này chưa? Cho mình xin review nhé! 👇", {"ok": True}),
    )

    result = adapter.publish(job)

    assert result.ok is True
    assert result.external_post_id == "buffer_p100"
    assert result.details["firstComment"] == "Có ai đã thử mẹo này chưa? Cho mình xin review nhé! 👇"
    assert getattr(job, "auto_comment_text", None) == "Có ai đã thử mẹo này chưa? Cho mình xin review nhé! 👇"

    client.create_post.assert_called_once()
    kwargs = client.create_post.call_args.kwargs
    assert kwargs["channel_id"] == "chan_fb_page"
    assert kwargs["service"] == "facebook"
    assert kwargs["first_comment"] == "Có ai đã thử mẹo này chưa? Cho mình xin review nhé! 👇"


def test_adapter_publish_facebook_uses_existing_auto_comment_text(monkeypatch):
    client = MagicMock()
    client.infer_channel_service.return_value = "facebook"
    client.create_post.return_value = {"id": "buffer_p101", "dueAt": None}

    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=101,
        caption="Video hài hước",
        target_page="chan_fb_page",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
        auto_comment_text="Bình luận đã được định sẵn bởi người dùng",
    )
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)

    generator_mock = MagicMock()
    monkeypatch.setattr("app.features.buffer.first_comment.AIUseCases.generate_first_comment", generator_mock)

    result = adapter.publish(job)

    assert result.ok is True
    assert result.details["firstComment"] == "Bình luận đã được định sẵn bởi người dùng"
    # Ensure generator was not called since auto_comment_text was already provided
    generator_mock.assert_not_called()

    kwargs = client.create_post.call_args.kwargs
    assert kwargs["first_comment"] == "Bình luận đã được định sẵn bởi người dùng"


def test_adapter_publish_tiktok_omits_first_comment(monkeypatch):
    client = MagicMock()
    client.infer_channel_service.return_value = "tiktok"
    client.create_post.return_value = {"id": "buffer_tt_102", "dueAt": None}

    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=102,
        caption="Trend dance TikTok",
        target_page="chan_tt_channel",
        service="tiktok",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
        auto_comment_text="Bình luận này không được gửi sang TikTok",
    )
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)

    result = adapter.publish(job)

    assert result.ok is True
    assert result.external_post_id == "buffer_tt_102"
    assert result.details["firstComment"] is None

    client.create_post.assert_called_once()
    kwargs = client.create_post.call_args.kwargs
    assert kwargs["service"] == "tiktok"
    assert kwargs["first_comment"] is None


# ── 6. AIUseCases Facade Tests ──────────────────────────────────────────────


def test_ai_use_cases_generate_first_comment_prompt_and_purpose(monkeypatch):
    captured = {}

    def fake_generate_text(prompt: str, purpose: str = AIPurpose.GENERIC):
        captured["prompt"] = prompt
        captured["purpose"] = purpose
        return "Bình luận mẫu từ AI", {"purpose": purpose}

    monkeypatch.setattr(AIUseCases, "generate_text", fake_generate_text)

    text, meta = AIUseCases.generate_first_comment(
        caption="Hướng dẫn làm bánh bông lan trứng muối siêu ngon",
        topic="nấu ăn",
    )

    assert text == "Bình luận mẫu từ AI"
    assert meta["purpose"] == AIPurpose.FIRST_COMMENT
    assert captured["purpose"] == AIPurpose.FIRST_COMMENT
    assert "DƯỚI 150 ký tự" in captured["prompt"]
    assert "KHÔNG dùng hashtag" in captured["prompt"]
    assert "KHÔNG chèn link" in captured["prompt"]
    assert "Hướng dẫn làm bánh bông lan trứng muối" in captured["prompt"]
    assert "Chủ đề/Phong cách: nấu ăn" in captured["prompt"]


def test_ai_use_cases_generate_first_comment_caps_caption_to_2000_chars(monkeypatch):
    captured = {}

    def fake_generate_text(prompt: str, purpose: str = AIPurpose.GENERIC):
        captured["prompt"] = prompt
        return "Bình luận ngắn", {"purpose": purpose}

    monkeypatch.setattr(AIUseCases, "generate_text", fake_generate_text)

    # Giant caption with 10,000 characters
    giant_caption = "X" * 10000
    AIUseCases.generate_first_comment(caption=giant_caption)

    # The prompt should contain exactly 2000 X's, not 10000
    assert "X" * 2000 in captured["prompt"]
    assert "X" * 2001 not in captured["prompt"]


def test_sanitize_comment_remediation_edge_cases():
    """Verify specific edge cases from Reviewer 2 / Challenger 2 remediation."""
    assert sanitize_comment('"Bình luận: Xin chào!"') == "Xin chào!"
    assert sanitize_comment('\\"Bình luận: Xin chào!\\"') == "Xin chào!"
    assert sanitize_comment("“Bình luận: Xin chào!”") == "Xin chào!"
    assert sanitize_comment("**Bình luận: Xin chào!**") == "Xin chào!"
    assert sanitize_comment("**Bình luận:** Xin chào!") == "Xin chào!"
    assert sanitize_comment("Bình luận: First comment: Xin chào!") == "Xin chào!"
    assert sanitize_comment("```Bình luận: Xin chào!```") == "Xin chào!"
    assert sanitize_comment('```python\n"Bình luận: Xin chào!"\n```') == "Xin chào!"

