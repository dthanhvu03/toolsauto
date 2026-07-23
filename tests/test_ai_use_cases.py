"""Unit tests for AIUseCases facade (domain prompts + purpose stamp)."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.ai.use_cases import AIPurpose, AIUseCases


@pytest.fixture
def mock_pipeline():
    with patch("app.core.ai.use_cases.pipeline") as pipe:
        pipe.enabled = True
        pipe.generate_text.return_value = ("ok-text", {"ok": True, "provider": "9router"})
        pipe.generate_text_async = AsyncMock(
            return_value=("async-text", {"ok": True, "provider": "9router"})
        )
        pipe.generate_caption.return_value = (
            MagicMock(caption="cap"),
            {"ok": True},
        )
        yield pipe


def test_is_enabled_reads_pipeline(mock_pipeline):
    mock_pipeline.enabled = False
    assert AIUseCases.is_enabled() is False
    mock_pipeline.enabled = True
    assert AIUseCases.is_enabled() is True


def test_generate_text_stamps_purpose(mock_pipeline):
    text, meta = AIUseCases.generate_text("hi", purpose=AIPurpose.GENERIC)
    assert text == "ok-text"
    assert meta["purpose"] == AIPurpose.GENERIC
    mock_pipeline.generate_text.assert_called_once_with("hi")


def test_generate_affiliate_comment_embeds_keyword_and_link_token(mock_pipeline):
    text, meta = AIUseCases.generate_affiliate_comment("son moi", "https://x.test/a")
    assert text == "ok-text"
    assert meta["purpose"] == AIPurpose.AFFILIATE_COMMENT
    prompt = mock_pipeline.generate_text.call_args[0][0]
    assert "son moi" in prompt
    assert "https://x.test/a" in prompt
    assert "[LINK]" in prompt


def test_generate_affiliate_bundle_embeds_product_fields(mock_pipeline):
    _, meta = AIUseCases.generate_affiliate_bundle("Kem A", "skincare", "199000", "12")
    assert meta["purpose"] == AIPurpose.AFFILIATE_GENERATE
    prompt = mock_pipeline.generate_text.call_args[0][0]
    assert "Kem A" in prompt
    assert "skincare" in prompt
    assert "199000" in prompt
    assert "12" in prompt


def test_rewrite_for_facebook_compliance_lists_violations(mock_pipeline):
    violations = [
        SimpleNamespace(category="claim", evidence="chữa khỏi", suggestion="bỏ claim")
    ]
    _, meta = AIUseCases.rewrite_for_facebook_compliance(
        "Chữa khỏi 100%", violations, "health"
    )
    assert meta["purpose"] == AIPurpose.COMPLIANCE_REWRITE
    prompt = mock_pipeline.generate_text.call_args[0][0]
    assert "Chữa khỏi 100%" in prompt
    assert "claim" in prompt
    assert "chữa khỏi" in prompt
    assert "health" in prompt


def test_generate_threads_reply(mock_pipeline):
    import asyncio

    text, meta = asyncio.run(AIUseCases.generate_threads_reply("Hay quá!"))
    assert text == "async-text"
    assert meta["purpose"] == AIPurpose.THREADS_REPLY
    prompt = mock_pipeline.generate_text_async.call_args[0][0]
    assert "Hay quá!" in prompt


def test_generate_incident_report_formats_groups(mock_pipeline):
    groups = [
        SimpleNamespace(
            error_signature="TimeoutError",
            last_platform="facebook",
            last_worker_name="publisher",
            severity_max="high",
            occurrence_count=5,
            last_seen_at="2026-07-22",
            last_sample_message="timed out",
            last_job_id=9,
            last_account_id=2,
        )
    ]
    _, meta = AIUseCases.generate_incident_report(groups)
    assert meta["purpose"] == AIPurpose.INCIDENT_REPORT
    prompt = mock_pipeline.generate_text.call_args[0][0]
    assert "TimeoutError" in prompt
    assert "facebook" in prompt
    assert "occurrence" not in prompt.lower() or "count=5" in prompt
    assert "count=5" in prompt
