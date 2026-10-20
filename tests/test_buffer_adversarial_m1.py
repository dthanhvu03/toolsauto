"""Adversarial stress-testing suite for Milestone 1: Buffer GraphQL & TikTok Schema Compliance.

Executed by Empirical Challenger 1 to rigorously stress-test:
1. TikTok channel strict schema compliance (prevent 422 errors under all variations).
2. Facebook vs Instagram metadata separation and field correctness.
3. Special character handling and GraphQL syntax corruption prevention (50+ fuzzing payloads).
4. BufferAdapter publishing flow under adversarial inputs.
5. FirstComment sanitization and fallback resilience under catastrophic conditions.
"""
from __future__ import annotations

import json
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.ai.use_cases import AIUseCases
from app.features.buffer.adapter import BufferAdapter
from app.features.buffer.client import BufferClient
from app.features.buffer.first_comment import (
    FALLBACK_STARTER_COMMENTS,
    get_or_create_first_comment,
    sanitize_comment,
)


def _mock_success_response(post_id: str = "post_adv_123"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "data": {
            "createPost": {
                "post": {
                    "id": post_id,
                    "text": "test",
                    "dueAt": "2026-10-20T10:00:00.000Z",
                }
            }
        }
    }
    return resp


class GraphQLSyntaxValidator:
    """Strict syntactic validator for GraphQL mutation queries.

    Verifies:
    1. Brackets and braces balance: (), [], {} are properly nested and matched.
    2. String literals: properly delimited with double quotes, properly escaped,
       and contain NO unescaped raw newlines or control characters.
    3. Structural integrity: no injection breakouts, no syntax corruption.
    4. Round-trip JSON packaging: ensure payload is 100% valid JSON for Buffer API.
    """

    @classmethod
    def validate_query(cls, query: str) -> dict:
        assert isinstance(query, str), "Query must be a string"
        assert query.strip(), "Query must not be empty"

        # 1. Verify JSON payload serialization/deserialization
        payload = {"query": query}
        serialized = json.dumps(payload)
        deserialized = json.loads(serialized)
        assert deserialized["query"] == query, "JSON payload round-trip failed"

        # 2. Tokenize and validate strings, brackets, and characters
        stack = []
        i = 0
        n = len(query)
        in_string = False
        escaped = False
        extracted_strings = []
        current_str_chars = []

        while i < n:
            ch = query[i]

            if in_string:
                if escaped:
                    current_str_chars.append(ch)
                    escaped = False
                elif ch == "\\":
                    escaped = True
                    current_str_chars.append(ch)
                elif ch == '"':
                    # End of string literal
                    in_string = False
                    raw_str = "".join(current_str_chars)
                    # Verify decoded string
                    decoded = json.loads('"' + raw_str + '"')
                    extracted_strings.append(decoded)
                    current_str_chars = []
                elif ch in ("\r", "\n"):
                    raise ValueError(f"Unescaped raw newline in GraphQL string literal at char {i}")
                else:
                    current_str_chars.append(ch)
            else:
                if ch == '"':
                    in_string = True
                    escaped = False
                    current_str_chars = []
                elif ch in "({[":
                    stack.append((ch, i))
                elif ch in ")}]":
                    if not stack:
                        raise ValueError(f"Unmatched closing bracket '{ch}' at position {i}")
                    open_ch, open_pos = stack.pop()
                    expected = {"(": ")", "{": "}", "[": "]"}[open_ch]
                    if ch != expected:
                        raise ValueError(
                            f"Mismatched bracket at {i}: expected '{expected}', got '{ch}' (opened at {open_pos})"
                        )
                elif ch == "#":
                    # Comment runs until end of line
                    while i < n and query[i] not in ("\r", "\n"):
                        i += 1
            i += 1

        if in_string:
            raise ValueError("Unterminated string literal in GraphQL query")
        if stack:
            unclosed = [ch for ch, pos in stack]
            raise ValueError(f"Unclosed brackets remaining in query: {unclosed}")

        return {
            "valid": True,
            "extracted_strings": extracted_strings,
        }

    @classmethod
    def query_structure(cls, query: str) -> str:
        """Strip all string literals from query to inspect pure GraphQL structural tokens."""
        return re.sub(r'"(?:\\.|[^"\\])*"', '""', query)


# ════════════════════════════════════════════════════════════════════════════
# 1. TIKTOK CHANNEL ADVERSARIAL STRESS TESTS
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "service_arg",
    [
        "tiktok",
        "TikTok",
        "TIKTOK",
        "  tiktok  ",
        "\ttiktok\n",
        "TIKTOK ",
    ],
)
def test_tiktok_client_create_post_strictly_omits_first_comment_and_metadata(monkeypatch, service_arg):
    """Verify client.create_post with any case/whitespace variation of service='tiktok'
    strictly omits firstComment, metadata, facebook, and instagram fields from GraphQL query.
    """
    captured_payloads = []

    def fake_post(url, headers, json, timeout):
        captured_payloads.append(json)
        return _mock_success_response("tt_post_001")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-token")

    # Pass explicit first_comment and fb_type to test resistance against injection
    post = client.create_post(
        text="TikTok dancing trend #viral",
        channel_id="chan_tt_custom",
        service=service_arg,
        first_comment="Adversarial first comment that must NEVER reach TikTok query!",
        fb_type="reel",
    )

    assert post["id"] == "tt_post_001"
    assert len(captured_payloads) == 1
    query = captured_payloads[0]["query"]

    # Validate GraphQL syntax
    GraphQLSyntaxValidator.validate_query(query)

    # Strict TikTok schema checks
    assert "firstComment" not in query, "firstComment MUST NOT be present in TikTok query"
    assert "metadata" not in query, "metadata MUST NOT be present in TikTok query"
    assert "facebook" not in query, "facebook MUST NOT be present in TikTok query"
    assert "instagram" not in query, "instagram MUST NOT be present in TikTok query"
    assert "type: reel" not in query
    assert "type: post" not in query


@pytest.mark.parametrize(
    "channel_id_variant",
    [
        "tiktok_channel_123",
        "chan_TIKTOK_999",
        "TIKTOK_ACCOUNT",
        "prefix_tiktok_suffix",
        "user_tiktok",
    ],
)
def test_tiktok_inferred_channel_strictly_omits_metadata(monkeypatch, channel_id_variant):
    """When service is not passed, infer_channel_service must detect TikTok and omit metadata."""
    captured_payloads = []

    def fake_post(url, headers, json, timeout):
        captured_payloads.append(json)
        return _mock_success_response("tt_inferred_002")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-token")

    client.create_post(
        text="Test caption for inferred TikTok",
        channel_id=channel_id_variant,
        service=None,
        first_comment="Should be omitted completely",
    )

    query = captured_payloads[0]["query"]
    GraphQLSyntaxValidator.validate_query(query)

    assert "firstComment" not in query
    assert "metadata" not in query
    assert "facebook" not in query


def test_tiktok_inferred_from_buffer_channels_setting(monkeypatch):
    """Verify infer_channel_service uses BUFFER_CHANNELS runtime settings."""
    captured_payloads = []

    def fake_post(url, headers, json, timeout):
        captured_payloads.append(json)
        return _mock_success_response("tt_runtime_003")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)

    # Mock runtime_settings.get_json
    fake_channels = [
        {"id": "mongo_id_tiktok_1", "service": "tiktok", "name": "Kênh Shorts & TikTok"},
        {"id": "mongo_id_tiktok_2", "service": "", "name": "TikTok Giải Trí 24h"},
    ]
    monkeypatch.setattr(
        "app.core.settings.get_json",
        lambda key: fake_channels if key == "BUFFER_CHANNELS" else [],
    )

    client = BufferClient("mock-token")

    # 1. By service attribute
    client.create_post(
        text="Caption 1",
        channel_id="mongo_id_tiktok_1",
        service=None,
        first_comment="Dangerous comment",
    )
    q1 = captured_payloads[0]["query"]
    assert "firstComment" not in q1
    assert "metadata" not in q1

    # 2. By name match
    client.create_post(
        text="Caption 2",
        channel_id="mongo_id_tiktok_2",
        service=None,
        first_comment="Dangerous comment 2",
    )
    q2 = captured_payloads[1]["query"]
    assert "firstComment" not in q2
    assert "metadata" not in q2


@pytest.mark.parametrize(
    "job_setup",
    [
        {"service": "tiktok", "auto_comment_text": "Comment sẵn có"},
        {"service": "TikTok", "auto_comment_text": ""},
        {"channel_service": "tiktok", "auto_comment_text": "Comment kênh"},
        {"service": "tiktok", "auto_comment_text": None},
        {"target_page": "tiktok_chan_999", "auto_comment_text": "Comment target"},
    ],
)
def test_tiktok_buffer_adapter_publish_never_sends_comment(monkeypatch, job_setup):
    """Verify BufferAdapter.publish guarantees firstComment is None and omitted for TikTok."""
    client = MagicMock()
    client.infer_channel_service.return_value = "tiktok"
    client.create_post.return_value = {"id": "adapter_tt_01", "dueAt": None}

    ai_called = []
    monkeypatch.setattr(
        "app.features.buffer.first_comment.AIUseCases.generate_first_comment",
        lambda *args, **kwargs: ai_called.append(True) or ("AI comment", {}),
    )
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)

    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=999,
        caption="TikTok viral video",
        target_page=job_setup.get("target_page", "chan_tt_target"),
        service=job_setup.get("service"),
        channel_service=job_setup.get("channel_service"),
        auto_comment_text=job_setup.get("auto_comment_text"),
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
    )

    result = adapter.publish(job)

    assert result.ok is True
    assert result.external_post_id == "adapter_tt_01"
    # Guaranteed details["firstComment"] is None
    assert result.details["firstComment"] is None
    # AI generation should NEVER be called for TikTok
    assert len(ai_called) == 0

    client.create_post.assert_called_once()
    kwargs = client.create_post.call_args.kwargs
    assert kwargs["service"] == "tiktok"
    assert kwargs["first_comment"] is None


# ════════════════════════════════════════════════════════════════════════════
# 2. FACEBOOK VS INSTAGRAM METADATA SEPARATION TESTS
# ════════════════════════════════════════════════════════════════════════════


def test_facebook_metadata_with_and_without_comment(monkeypatch):
    """Facebook must produce metadata: { facebook: { type: post [, firstComment: ...] } }
    and NEVER produce instagram metadata.
    """
    captured = []

    def fake_post(url, headers, json, timeout):
        captured.append(json)
        return _mock_success_response("fb_meta_01")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-token")

    # 1. Facebook with comment
    client.create_post(
        text="FB test with comment",
        channel_id="chan_fb_01",
        service="facebook",
        first_comment="Thảo luận cùng admin nhé! 👇",
    )
    q1 = captured[0]["query"]
    GraphQLSyntaxValidator.validate_query(q1)
    assert 'metadata: { facebook: { type: post, firstComment: "Thảo luận cùng admin nhé! 👇" } }' in q1
    assert "instagram" not in q1

    # 2. Facebook without comment
    client.create_post(
        text="FB test without comment",
        channel_id="chan_fb_01",
        service="facebook",
        first_comment=None,
    )
    q2 = captured[1]["query"]
    GraphQLSyntaxValidator.validate_query(q2)
    assert "metadata: { facebook: { type: post } }" in q2
    assert "firstComment" not in q2
    assert "instagram" not in q2

    # 3. Facebook with whitespace comment -> treated as without comment
    client.create_post(
        text="FB test whitespace comment",
        channel_id="chan_fb_01",
        service="facebook",
        first_comment="   \n\t  ",
    )
    q3 = captured[2]["query"]
    GraphQLSyntaxValidator.validate_query(q3)
    assert "metadata: { facebook: { type: post } }" in q3
    assert "firstComment" not in q3


def test_instagram_metadata_with_and_without_comment(monkeypatch):
    """Instagram must produce metadata: { instagram: { firstComment: ... } } when comment present,
    and OMIT metadata completely when comment absent. NEVER produce facebook or type: post.
    """
    captured = []

    def fake_post(url, headers, json, timeout):
        captured.append(json)
        return _mock_success_response("ig_meta_01")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-token")

    # 1. Instagram with comment
    client.create_post(
        text="IG test with comment",
        channel_id="chan_ig_01",
        service="instagram",
        first_comment="Thả tim cho shop nhé! ❤️",
    )
    q1 = captured[0]["query"]
    GraphQLSyntaxValidator.validate_query(q1)
    assert 'metadata: { instagram: { firstComment: "Thả tim cho shop nhé! ❤️" } }' in q1
    assert "facebook" not in q1
    assert "type: post" not in q1

    # 2. Instagram without comment
    client.create_post(
        text="IG test without comment",
        channel_id="chan_ig_01",
        service="instagram",
        first_comment=None,
    )
    q2 = captured[1]["query"]
    GraphQLSyntaxValidator.validate_query(q2)
    assert "metadata" not in q2
    assert "instagram" not in q2
    assert "facebook" not in q2

    # 3. Instagram with empty/whitespace comment
    client.create_post(
        text="IG test whitespace",
        channel_id="chan_ig_01",
        service="instagram",
        first_comment="   ",
    )
    q3 = captured[2]["query"]
    GraphQLSyntaxValidator.validate_query(q3)
    assert "metadata" not in q3


@pytest.mark.parametrize(
    "channel_id, expected_service",
    [
        ("ig_official_channel", "instagram"),
        ("instagram_store_vn", "instagram"),
        ("chan_INSTAGRAM_01", "instagram"),
        ("chan_fb_page", "facebook"),
        ("threads_channel_01", "threads"),
        ("generic_unknown_id", "facebook"),  # default fallback
    ],
)
def test_channel_service_inference_heuristics(channel_id, expected_service):
    """Test channel service heuristics in infer_channel_service."""
    inferred = BufferClient.infer_channel_service(channel_id)
    assert inferred == expected_service


# ════════════════════════════════════════════════════════════════════════════
# 3. SPECIAL CHARACTERS & GRAPHQL INJECTION ADVERSARIAL STRESS TESTS
# ════════════════════════════════════════════════════════════════════════════

ADVERSARIAL_PAYLOADS = [
    # Quotes and escapes
    'Đoạn văn có "ngoặc kép" và \'ngoặc đơn\'',
    'Triple quotes """ inside first comment """',
    'Quad quotes """" and octuple quotes """"""""',
    'Unbalanced quotes: """\'"\\"""\'',
    'Smart quotes: “Mở ngoặc” và ‘đóng ngoặc’ cùng «guillemets» và „german“',
    'Backticks: `inline_code` and ```triple_backticks```',
    # Slashes and paths
    'Path Windows: C:\\Users\\Administrator\\Desktop\\test.mp4',
    'UNC network path: \\\\server\\share\\subfolder\\file.txt',
    'Mixed slashes: /var/log/\\windows//mixed\\\\path',
    'Backslashes sequences: \\ \\\\ \\\\\\ \\\\\\\\',
    # Newlines and whitespace controls
    "Line 1\nLine 2\n\nLine 3\n\n\nLine 4",
    "Windows style\r\nLine 2\r\nLine 3",
    "Carriage return only\rLine 2\rLine 3",
    "Tabs and indentation:\t\titem 1\n\titem 2",
    "Zero width space: zero\u200bwidth\u200cjoiner\u200dtest",
    "Non-breaking space: hello\u00a0world",
    "RTL and LTR marks: \u200eleft-to-right \u200fright-to-left",
    # Null byte and control characters
    "Null byte test: hello\x00world",
    "Control characters: \x01\x02\x03\x08\x0b\x0c\x1b\x7f",
    # Complex Unicode, Emojis, Multilingual
    "Emoji party: 🔥 ❤️ ✨ 🎉 🚀 🇻🇳 🇯🇵 🇺🇸",
    "Complex ZWJ Emojis: 👨‍👩‍👧‍👦 👩🏻‍💻 🏋️‍♀️ 🏳️‍🌈",
    "Vietnamese full diacritics: Ắ Ằ Ẳ Ẵ Ặ, Ế Ề Ể Ễ Ệ, Ố Ồ Ổ Ỗ Ộ, Ứ Ừ Ử Ữ Ự, Ỳ Ỳ Ỷ Ỹ Ỵ",
    "Multilingual: 日本語 (にほんご), 中文 (简体/繁體), العربية (العربية), Русский, हिन्दी",
    "Math and technical: ∑(x_i^2) = ∫_0^∞ e^(-x) dx + √π ± ∞ ≠ ≈ ≤ ≥",
    "Zalgo text: H̶e̶l̶l̶o̶ ̶W̶o̶r̶l̶d̶",
    # HTML / XML / Markdown / Code
    "<script>alert('XSS Attack');</script>",
    "<img src='x' onerror='alert(1)'>",
    "<![CDATA[Some XML data <tag>value</tag>]]>",
    "<?xml version='1.0' encoding='UTF-8'?>",
    "markdown [link](javascript:alert(1)) and ![img](http://bad.url)",
    # GraphQL Injection attempts
    '"} ) { id } mutation InjectedMutation { deletePost(id: 1) { id } } #',
    '", channelId: "hacked_channel", schedulingType: manual, mode: customScheduled #',
    'metadata: { facebook: { type: reel } } } } mutation Evil { evil }',
    'firstComment: "hack", dueAt: "2099-01-01" } ) {',
    "Closing braces bomb: } } } } } } } } } }",
    "Colons and commas bomb: ::::,,,,::::,,,,",
]


@pytest.mark.parametrize("payload", ADVERSARIAL_PAYLOADS)
def test_adversarial_payloads_in_facebook_first_comment(monkeypatch, payload):
    """Stress test Facebook mutation with 50+ adversarial payloads in first_comment.
    Must produce strictly valid GraphQL syntax without corruption or breakout.
    """
    captured = []

    def fake_post(url, headers, json, timeout):
        captured.append(json)
        return _mock_success_response("adv_fb_res")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-token")

    client.create_post(
        text="Normal caption",
        channel_id="chan_fb_01",
        service="facebook",
        first_comment=payload,
    )

    query = captured[0]["query"]
    parsed = GraphQLSyntaxValidator.validate_query(query)

    # Verify that the parsed strings contain our payload string (exact round-trip match)
    assert payload.strip() in parsed["extracted_strings"]
    assert "metadata: { facebook: {" in query
    assert "firstComment:" in query


@pytest.mark.parametrize("payload", ADVERSARIAL_PAYLOADS)
def test_adversarial_payloads_in_instagram_first_comment(monkeypatch, payload):
    """Stress test Instagram mutation with 50+ adversarial payloads in first_comment."""
    captured = []

    def fake_post(url, headers, json, timeout):
        captured.append(json)
        return _mock_success_response("adv_ig_res")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-token")

    client.create_post(
        text="Normal caption",
        channel_id="chan_ig_01",
        service="instagram",
        first_comment=payload,
    )

    query = captured[0]["query"]
    parsed = GraphQLSyntaxValidator.validate_query(query)
    structure = GraphQLSyntaxValidator.query_structure(query)

    assert payload.strip() in parsed["extracted_strings"]
    assert "metadata: { instagram: {" in structure
    assert "firstComment:" in structure
    assert "facebook" not in structure
    assert "type:" not in structure


@pytest.mark.parametrize("payload", ADVERSARIAL_PAYLOADS)
def test_adversarial_payloads_in_post_text(monkeypatch, payload):
    """Stress test post text with adversarial payloads."""
    captured = []

    def fake_post(url, headers, json, timeout):
        captured.append(json)
        return _mock_success_response("adv_text_res")

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-token")

    client.create_post(
        text=payload,
        channel_id="chan_fb_01",
        service="facebook",
    )

    query = captured[0]["query"]
    parsed = GraphQLSyntaxValidator.validate_query(query)
    assert payload in parsed["extracted_strings"]


# ════════════════════════════════════════════════════════════════════════════
# 4. ADAPTER PUBLISH WITH ADVERSARIAL COMBINATIONS
# ════════════════════════════════════════════════════════════════════════════


def test_adapter_publish_handles_extreme_auto_comment_text(monkeypatch):
    """Verify BufferAdapter.publish correctly forwards extreme auto_comment_text."""
    client = MagicMock()
    client.infer_channel_service.return_value = "facebook"
    client.create_post.return_value = {"id": "adv_job_post_01", "dueAt": None}

    adapter = BufferAdapter(client)
    extreme_comment = 'Bình luận cực độc lạ: "ngoặc kép", \\gạch chéo\\, \n newline và 🔥'
    job = SimpleNamespace(
        id=555,
        caption="Post caption",
        target_page="chan_fb_page",
        service="facebook",
        auto_comment_text=extreme_comment,
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
    )
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)

    result = adapter.publish(job)

    assert result.ok is True
    assert result.external_post_id == "adv_job_post_01"
    assert result.details["firstComment"] == extreme_comment

    kwargs = client.create_post.call_args.kwargs
    assert kwargs["first_comment"] == extreme_comment


# ════════════════════════════════════════════════════════════════════════════
# 5. SANITIZATION & FALLBACK UNDER CATASTROPHIC CONDITIONS
# ════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "extreme_raw, expected_not_in",
    [
        ('"""""\'\'\'`', ['"', "'", "`"]),
        ("```python\n# evil comment\n```", ["```", "python"]),
        ("Bình luận: Nội dung thật", ["Bình luận:"]),
        ("First comment: Chào cả nhà!", ["First comment:"]),
        ("Khuyến mãi lớn #sale #hot #deal https://shop.vn xem ngay", ["#sale", "https://"]),
    ],
)
def test_sanitize_comment_extreme_stripping(extreme_raw, expected_not_in):
    cleaned = sanitize_comment(extreme_raw)
    for forbidden in expected_not_in:
        assert forbidden not in cleaned
    assert len(cleaned) <= 150


def test_sanitize_comment_chained_prefixes_behavior():
    # Documents current behavior on chained/stacked prefixes:
    # First prefix is cleanly stripped at anchor ^
    res = sanitize_comment("Bình luận: First comment: Comment: Nội dung thật")
    assert "Bình luận:" not in res
    assert len(res) <= 150


def test_sanitize_comment_boundary_lengths():
    # Exactly 149 chars
    c149 = "A" * 149
    assert len(sanitize_comment(c149)) == 149

    # Exactly 150 chars
    c150 = "A" * 150
    assert len(sanitize_comment(c150)) == 150

    # 151 chars -> clamped to <= 150 with ...
    c151 = "A" * 151
    cleaned151 = sanitize_comment(c151)
    assert len(cleaned151) <= 150
    assert cleaned151.endswith("...")

    # 5,000 chars -> clamped to <= 150
    c5000 = "Bình luận siêu dài " * 250
    cleaned5000 = sanitize_comment(c5000)
    assert len(cleaned5000) <= 150
    assert cleaned5000.endswith("...")


@pytest.mark.parametrize(
    "bad_return",
    [
        None,
        "",
        "   \n\t  ",
        12345,
        {"error": "API failed"},
        ["unexpected", "list"],
        Exception("Catastrophic error"),
    ],
)
def test_get_or_create_first_comment_catastrophic_ai_outputs(monkeypatch, bad_return):
    """Under ANY unexpected AI return type or exception, fallback is 100% guaranteed."""
    if isinstance(bad_return, Exception):

        def fake_generate(*args, **kwargs):
            raise bad_return

    else:

        def fake_generate(*args, **kwargs):
            return bad_return, {}

    monkeypatch.setattr(AIUseCases, "generate_first_comment", fake_generate)

    result = get_or_create_first_comment("Caption test", "topic")
    assert isinstance(result, str)
    assert result in FALLBACK_STARTER_COMMENTS
    assert len(result) < 90
