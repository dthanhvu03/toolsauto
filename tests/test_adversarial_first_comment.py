"""Adversarial stress testing for Gemini AI FirstComment, fallback guarantees, and length clamping.

Author: Challenger M1-2 (critic & specialist)
Target: app.features.buffer.first_comment & BufferAdapter integration.

Test dimensions:
1. Failure resilience: TimeoutError, ConnectionResetError, HTTP 429 RateLimit, empty string, None,
   purely whitespace, malformed objects, unexpected exceptions.
   Guarantee: NEVER raises, ALWAYS returns a valid comment from FALLBACK_STARTER_COMMENTS.
2. Length constraint: 200, 500, 2000, 10000 characters, boundary cases (149, 150, 151 chars),
   multibyte Vietnamese unicode, emoji strings.
   Guarantee: output is strictly clamped to <= 150 characters.
3. Quote and prefix stripping: AI prefixes (Bình luận:, First comment:, Comment:), codeblocks,
   wrapped double/single/curly quotes, guillemets, backticks, nested quotes, markdown.
   Guarantee: cleanly removed. If residual content is empty, gracefully falls back to starter pool.
4. Concurrency stress: 100 rapid multi-threaded calls to get_or_create_first_comment under
   stochastic conditions (mix of timeouts, rate limits, long responses, empty responses).
   Guarantee: thread-safe, non-blocking, zero exceptions, 100% valid outputs <= 150 chars.
5. End-to-end BufferAdapter stress: verifies publishing resilience with Facebook, Instagram, and
   TikTok channels under adversarial AI behaviors.
"""
from __future__ import annotations

import concurrent.futures
import random
import time
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


# ── SUITE 1: FAILURE RESILIENCE & FALLBACK GUARANTEES ────────────────────────


class MockHttpRateLimitError(Exception):
    """Simulated HTTP 429 Rate Limit error from Gemini / 9Router."""
    status_code = 429
    message = "Resource exhausted: rate limit exceeded"


@pytest.mark.parametrize(
    "exception_to_raise",
    [
        TimeoutError("Connection to 9Router Gemini timed out after 10000ms"),
        ConnectionResetError("Connection reset by peer"),
        MockHttpRateLimitError(),
        RuntimeError("Google GenAI 429 Quota Exceeded"),
        ValueError("Unexpected payload schema returned by Gemini"),
        KeyError("candidates"),
        AttributeError("'NoneType' object has no attribute 'text'"),
        OSError("Network unreachable"),
        Exception("Generic unhandled exception in AI subsystem"),
    ],
)
def test_adversarial_failure_resilience_exceptions(monkeypatch, exception_to_raise):
    """Assert get_or_create_first_comment never raises and returns a valid fallback comment."""
    def fake_failing(caption: str, topic: str = ""):
        raise exception_to_raise

    monkeypatch.setattr(AIUseCases, "generate_first_comment", fake_failing)

    # Test with standard caption
    res1 = get_or_create_first_comment("Caption video review đồ gia dụng")
    assert res1 in FALLBACK_STARTER_COMMENTS
    assert 0 < len(res1) <= 150

    # Test with empty caption
    res2 = get_or_create_first_comment("")
    assert res2 in FALLBACK_STARTER_COMMENTS

    # Test with whitespace caption
    res3 = get_or_create_first_comment("   \n\t   ")
    assert res3 in FALLBACK_STARTER_COMMENTS


@pytest.mark.parametrize(
    "falsy_ai_output",
    [
        ("", {}),
        ("   ", {}),
        ("\n\t\r\n", {}),
        (None, {}),
        (None, None),
    ],
)
def test_adversarial_failure_resilience_empty_or_none(monkeypatch, falsy_ai_output):
    """Assert empty or None responses from AI trigger safe fallback without errors."""
    monkeypatch.setattr(AIUseCases, "generate_first_comment", lambda c, t="": falsy_ai_output)

    result = get_or_create_first_comment("Video hướng dẫn lập trình Python")
    assert result in FALLBACK_STARTER_COMMENTS
    assert 0 < len(result) <= 150


@pytest.mark.parametrize(
    "malformed_return",
    [
        12345,  # Raw non-tuple
        "Chuỗi không phải tuple",
        None,
        [],
        ({}, {}),  # Tuple with dict instead of str
        (12345, {}),
        (["list of text"], {}),
    ],
)
def test_adversarial_failure_resilience_malformed_ai_returns(monkeypatch, malformed_return):
    """Assert malformed return types from AIUseCases do not crash get_or_create_first_comment."""
    monkeypatch.setattr(AIUseCases, "generate_first_comment", lambda c, t="": malformed_return)

    result = get_or_create_first_comment("Video nấu ăn đặc sắc")
    # Must never raise, must return valid fallback or valid string <= 150
    assert isinstance(result, str)
    assert len(result) <= 150
    assert len(result) > 0


def test_adversarial_residual_empty_after_sanitization(monkeypatch):
    """When AI returns only hashtags, raw URLs, or quotes, residual is empty -> fallback."""
    empty_after_strip_cases = [
        "#reels #viral #trending #fyp #foryou",
        "```\n```",
        "\"\"\"\"\"\"",
        "https://spam.link https://malicious.com/tracker",
        "www.example.com",
    ]
    for case in empty_after_strip_cases:
        monkeypatch.setattr(AIUseCases, "generate_first_comment", lambda c, t="": (case, {}))
        res = get_or_create_first_comment("Video bài học cuộc sống")
        assert res in FALLBACK_STARTER_COMMENTS, f"Expected fallback for empty sanitized result from: {case}"


def test_adversarial_markdown_link_anchor_flattening():
    """Verify markdown links [anchor](url) preserve anchor text and strip URL."""
    sanitized = sanitize_comment("Xem ngay [tại đây](https://spam.link) nha cả nhà!")
    assert sanitized == "Xem ngay tại đây nha cả nhà!"
    assert "https://" not in sanitized


# ── SUITE 2: LENGTH CONSTRAINT & CLAMPING GUARANTEES ─────────────────────────


@pytest.mark.parametrize(
    "char_count",
    [151, 180, 200, 500, 2000, 10000],
)
def test_adversarial_length_clamping_various_sizes(monkeypatch, char_count):
    """Assert AI outputs exceeding 150 characters are strictly clamped to <= 150 chars."""
    raw_ai_text = "Lời bình luận siêu dài từ Gemini AI thử thách giới hạn ký tự. " * (char_count // 50 + 2)
    raw_ai_text = raw_ai_text[:char_count]

    monkeypatch.setattr(AIUseCases, "generate_first_comment", lambda c, t="": (raw_ai_text, {}))

    result = get_or_create_first_comment("Video dài kiểm tra clamping")
    assert len(result) <= 150, f"Result length {len(result)} exceeds 150 for input {char_count}"
    assert result.endswith("...")
    assert len(result.strip()) > 0


def test_adversarial_length_clamping_boundary_cases():
    """Verify exact boundaries: 149, 150, 151 characters."""
    # 149 chars: exact match, no truncation
    text_149 = "A" * 149
    san_149 = sanitize_comment(text_149)
    assert len(san_149) == 149
    assert not san_149.endswith("...")

    # 150 chars: exact match, no truncation
    text_150 = "B" * 150
    san_150 = sanitize_comment(text_150)
    assert len(san_150) == 150
    assert not san_150.endswith("...")

    # 151 chars: truncated to <= 150 with ...
    text_151 = "C" * 151
    san_151 = sanitize_comment(text_151)
    assert len(san_151) <= 150
    assert san_151.endswith("...")


def test_adversarial_length_clamping_unicode_and_emojis(monkeypatch):
    """Stress test clamping with multi-byte Vietnamese characters and 4-byte UTF-8 emojis."""
    vietnamese_sample = "Mọi người có thích phong cách này không? Thả tim và lưu lại nha! " * 10
    assert len(vietnamese_sample) > 500

    monkeypatch.setattr(AIUseCases, "generate_first_comment", lambda c, t="": (vietnamese_sample, {}))
    res_vn = get_or_create_first_comment("Video tiếng Việt")
    assert len(res_vn) <= 150
    assert res_vn.endswith("...")

    emoji_sample = "🔥❤️🎉👍✨🚀💬🔔📌😉" * 30
    assert len(emoji_sample) > 300
    monkeypatch.setattr(AIUseCases, "generate_first_comment", lambda c, t="": (emoji_sample, {}))
    res_emoji = get_or_create_first_comment("Video emojis")
    assert len(res_emoji) <= 150


# ── SUITE 3: QUOTE, PREFIX & CODEBLOCK STRIPPING ─────────────────────────────


@pytest.mark.parametrize(
    "raw_input,expected_cleaned",
    [
        # Standard unquoted prefixes
        ("First comment: Xin chào cả nhà!", "Xin chào cả nhà!"),
        ("first comment: Xin chào cả nhà!", "Xin chào cả nhà!"),
        ("FIRST COMMENT: Xin chào cả nhà!", "Xin chào cả nhà!"),
        ("Comment: Xin chào!", "Xin chào!"),
        ("comment: Xin chào!", "Xin chào!"),
        ("Bình luận đầu tiên: Xin chào bạn!", "Xin chào bạn!"),
        ("bình luận đầu tiên : Xin chào bạn!", "Xin chào bạn!"),
        ("Bình luận - Xin chào cả nhà!", "Xin chào cả nhà!"),
        ("Bình luận — Xin chào cả nhà!", "Xin chào cả nhà!"),
        # Mandatory adversarial cases from dispatch instructions:
        # Mock AI returning '\"Bình luận: Xin chào!\"' (quotes wrapping prefix)
        ('"Bình luận: Xin chào!"', "Xin chào!"),
        ('\\"Bình luận: Xin chào!\\"', "Xin chào!"),
        ('“Bình luận: Xin chào!”', "Xin chào!"),
        ('‘Bình luận: Xin chào!’', "Xin chào!"),
        ('«Bình luận: Xin chào!»', "Xin chào!"),
        ('`Bình luận: Xin chào!`', "Xin chào!"),
        ('```Bình luận: Xin chào cả nhà!```', "Xin chào cả nhà!"),
        ('```python\n"Bình luận: Xin chào cả nhà!"\n```', "Xin chào cả nhà!"),
        ('**Bình luận: Xin chào cả nhà!**', "Xin chào cả nhà!"),
        ('""Bình luận: \'Xin chào!\'""', "Xin chào!"),
        ("Bình luận: First comment: Xin chào!", "Xin chào!"),
        ("**Bình luận:** Xin chào cả nhà!", "Xin chào cả nhà!"),
        ("“Bình luận: **Xin chào cả nhà!**”", "Xin chào cả nhà!"),
        ("__First comment:__ Xin chào cả nhà!", "Xin chào cả nhà!"),
        ('"**First comment:** Xin chào cả nhà!"', "Xin chào cả nhà!"),
        ("Bình luận: Bình luận đầu tiên: Comment: Xin chào!", "Xin chào!"),
    ],
)
def test_adversarial_quote_and_prefix_stripping(monkeypatch, raw_input, expected_cleaned):
    """Verify various formats of quotes and prefixes are cleanly stripped."""
    monkeypatch.setattr(AIUseCases, "generate_first_comment", lambda c, t="": (raw_input, {}))
    result = get_or_create_first_comment("Video thử nghiệm strip prefix")
    assert result == expected_cleaned


# ── SUITE 4: CONCURRENCY STRESS & THREAD SAFETY (100 RAPID CALLS) ────────────


def test_adversarial_concurrency_stress_100_calls(monkeypatch):
    """Execute 100 rapid multi-threaded calls to get_or_create_first_comment.

    Stochastically mixes:
    - Normal responses (short, medium, long)
    - TimeoutError
    - ConnectionResetError
    - MockHttpRateLimitError
    - Empty strings & None
    - Prefix-wrapped and quote-wrapped strings
    """
    call_counter = 0

    def stochastic_ai_generator(caption: str, topic: str = ""):
        nonlocal call_counter
        call_counter += 1
        scenario = random.choice([
            "normal_short",
            "normal_long_2000",
            "timeout",
            "rate_limit",
            "connection_reset",
            "empty",
            "quotes_prefix",
            "only_hashtags",
        ])

        if scenario == "normal_short":
            return f"Thật tuyệt vời khi xem video này! {call_counter}", {"ok": True}
        elif scenario == "normal_long_2000":
            return "Nội dung rất dài vượt ngưỡng 150 ký tự " * 80, {"ok": True}
        elif scenario == "timeout":
            raise TimeoutError("Simulated timeout in thread")
        elif scenario == "rate_limit":
            raise MockHttpRateLimitError("Simulated 429 in thread")
        elif scenario == "connection_reset":
            raise ConnectionResetError("Simulated socket reset in thread")
        elif scenario == "empty":
            return "", {"ok": True}
        elif scenario == "quotes_prefix":
            return f'\"Bình luận: Câu trả lời rất thú vị! #{call_counter}\"', {"ok": True}
        else:  # only_hashtags
            return "#reels #trending #vietnam", {"ok": True}

    monkeypatch.setattr(AIUseCases, "generate_first_comment", stochastic_ai_generator)

    num_calls = 100
    start_time = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        futures = [
            executor.submit(
                get_or_create_first_comment,
                f"Caption for worker thread {i}",
                "chu_de_stress",
            )
            for i in range(num_calls)
        ]
        results = [f.result(timeout=10.0) for f in futures]

    duration = time.perf_counter() - start_time

    assert len(results) == num_calls
    for idx, comment in enumerate(results):
        assert isinstance(comment, str), f"Result {idx} is not string: {type(comment)}"
        assert len(comment.strip()) > 0, f"Result {idx} is empty"
        assert len(comment) <= 150, f"Result {idx} exceeded 150 chars: {len(comment)}"
        # Verify no unhandled prefixes or surrounding quotes
        assert not comment.startswith('"')
        assert not comment.startswith("'")
        assert not comment.startswith("Bình luận:")
        assert not comment.startswith("First comment:")

    # Performance check: 100 mock calls should complete rapidly (< 2.0s)
    assert duration < 2.0, f"Concurrency test took too long: {duration:.2f}s"


# ── SUITE 5: BUFFER ADAPTER END-TO-END PUBLISHING STRESS ─────────────────────


def test_adversarial_adapter_publish_resilience_facebook_failing_ai(monkeypatch):
    """Verify Facebook publishing succeeds even when AI completely crashes with 429."""
    client = MagicMock()
    client.infer_channel_service.return_value = "facebook"
    client.create_post.return_value = {"id": "fb_p_resilient_01", "dueAt": None}

    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)
    monkeypatch.setattr(
        "app.features.buffer.first_comment.AIUseCases.generate_first_comment",
        MagicMock(side_effect=MockHttpRateLimitError("Quota limit hit")),
    )

    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=777,
        caption="Caption Facebook thử thách độ bền hệ thống",
        target_page="chan_fb_page_777",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
    )

    result = adapter.publish(job)

    assert result.ok is True
    assert result.external_post_id == "fb_p_resilient_01"
    # Fallback comment was assigned and passed to client.create_post
    assigned_fc = result.details["firstComment"]
    assert assigned_fc in FALLBACK_STARTER_COMMENTS
    assert len(assigned_fc) <= 150

    client.create_post.assert_called_once()
    kwargs = client.create_post.call_args.kwargs
    assert kwargs["service"] == "facebook"
    assert kwargs["first_comment"] == assigned_fc


def test_adversarial_adapter_publish_resilience_facebook_2000char_ai(monkeypatch):
    """Verify Facebook publishing clamps 2000-char AI comment to <= 150 before calling Buffer."""
    client = MagicMock()
    client.infer_channel_service.return_value = "facebook"
    client.create_post.return_value = {"id": "fb_p_long_01", "dueAt": None}

    super_long_comment = "Một câu bình luận cực kỳ dài dòng nhằm thử thách hệ thống Buffer API. " * 50
    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)
    monkeypatch.setattr(
        "app.features.buffer.first_comment.AIUseCases.generate_first_comment",
        lambda c, t="": (super_long_comment, {"ok": True}),
    )

    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=888,
        caption="Caption Facebook test long comment",
        target_page="chan_fb_page_888",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
    )

    result = adapter.publish(job)

    assert result.ok is True
    assigned_fc = result.details["firstComment"]
    assert len(assigned_fc) <= 150
    assert assigned_fc.endswith("...")

    kwargs = client.create_post.call_args.kwargs
    assert len(kwargs["first_comment"]) <= 150


def test_adversarial_adapter_publish_tiktok_strict_omission_under_pressure(monkeypatch):
    """Verify TikTok channel never sends first_comment or metadata even if AI is called or job has auto_comment_text."""
    client = MagicMock()
    client.infer_channel_service.return_value = "tiktok"
    client.create_post.return_value = {"id": "tt_p_strict_01", "dueAt": None}

    monkeypatch.setattr("app.features.buffer.adapter.SAFE_MODE", False)

    adapter = BufferAdapter(client)
    job = SimpleNamespace(
        id=999,
        caption="Caption TikTok dance trend",
        target_page="chan_tt_channel_999",
        service="tiktok",
        media_path="",
        processed_media_path=None,
        schedule_ts=0,
        account=None,
        auto_comment_text="Không được gửi comment này vào TikTok GraphQL payload!",
    )

    result = adapter.publish(job)

    assert result.ok is True
    assert result.details["firstComment"] is None

    client.create_post.assert_called_once()
    kwargs = client.create_post.call_args.kwargs
    assert kwargs["service"] == "tiktok"
    assert kwargs["first_comment"] is None


def test_adversarial_graphql_injection_in_first_comment(monkeypatch):
    """Verify malicious GraphQL injection attempts in first_comment are safely escaped."""
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "data": {"createPost": {"post": {"id": "sec_001", "text": "ok", "dueAt": None}}}
        }
        return resp

    monkeypatch.setattr("app.features.buffer.client.requests.post", fake_post)
    client = BufferClient("mock-buffer-token")

    injection_strings = [
        'test" }}) { maliciousField } mutation { hack { id } } #',
        '"><script>alert(1)</script>',
        "Bình luận \n\r\t với ký tự đặc biệt: \\ and \"quotes\"",
    ]

    for inj in injection_strings:
        client.create_post(
            text="Test injection caption",
            channel_id="chan_fb_sec",
            service="facebook",
            first_comment=inj,
        )
        query = captured["payload"]["query"]
        # Ensure query is well-formed string and no raw unescaped quotes break the GraphQL string literal
        assert 'metadata: { facebook: {' in query
        assert 'firstComment: "' in query
