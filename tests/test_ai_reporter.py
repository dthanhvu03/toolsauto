from datetime import datetime, timezone
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.database.models import IncidentGroup
from workers import ai_reporter


def _group(
    signature: str = "sig-test-1",
    *,
    count: int = 3,
    severity: str = "error",
    sample: str = "Selector timeout",
) -> IncidentGroup:
    return IncidentGroup(
        error_signature=signature,
        first_seen_at=datetime(2026, 4, 26, 1, 0, tzinfo=timezone.utc),
        last_seen_at=datetime(2026, 4, 26, 8, 0, tzinfo=timezone.utc),
        occurrence_count=count,
        last_job_id="job-123",
        last_account_id="account-456",
        last_platform="facebook",
        last_worker_name="FB_Publisher_1",
        last_sample_message=sample,
        severity_max=severity,
        status="open",
    )


def test_build_report_uses_mock_pipeline(monkeypatch):
    def fake_generate_text(prompt: str):
        assert "sig-test-1" in prompt
        return "Tóm tắt: hệ thống có 1 nhóm lỗi.", {
            "ok": True,
            "model": "mock",
            "fallback_used": False,
            "primary_fail_reason": None,
        }

    monkeypatch.setattr(ai_reporter.pipeline, "generate_text", fake_generate_text)

    report = ai_reporter.build_report([_group()])

    assert report.startswith("<b>Daily Health Report</b>")
    assert "<pre>" in report
    assert "Tóm tắt" in report
    # Happy path → no fallback warning
    assert "Dự phòng" not in report


def test_build_report_surfaces_fallback_warning_when_native_used(monkeypatch):
    """ADR-006: when meta['fallback_used'] is True, the Telegram report must
    include a visible warning so the reader knows output came from native path."""
    def fake_generate_text(prompt: str):
        return "Báo cáo từ native.", {
            "ok": True,
            "model": "gemini-2.5-flash",
            "provider": "native_gemini",
            "fallback_used": True,
            "primary_fail_reason": "circuit_open",
        }

    monkeypatch.setattr(ai_reporter.pipeline, "generate_text", fake_generate_text)

    report = ai_reporter.build_report([_group()])

    assert report.startswith("<b>Daily Health Report</b>")
    assert "Dự phòng" in report
    assert "Gemini Native" in report
    assert "gemini-2.5-flash" in report
    assert "circuit_open" in report
    assert "Báo cáo từ native." in report


def test_build_report_falls_back_when_pipeline_fails(monkeypatch):
    def fail_generate_text(prompt: str):
        raise RuntimeError("mock router down")

    monkeypatch.setattr(ai_reporter.pipeline, "generate_text", fail_generate_text)

    report = ai_reporter.build_report([_group()])

    assert "<b>Daily Health Report</b>" in report
    assert "Gemini unavailable: mock router down" in report
    assert "sig-test-1" in report
    assert "Selector timeout" in report


def test_build_report_empty_groups_returns_heartbeat_without_pipeline(monkeypatch):
    called = False

    def fake_generate_text(prompt: str):
        nonlocal called
        called = True
        return "unused", {"ok": True}

    monkeypatch.setattr(ai_reporter.pipeline, "generate_text", fake_generate_text)

    report = ai_reporter.build_report([])

    assert report == "<b>Daily Health Report</b>\nKhông có incident mới trong 24h."
    assert called is False


def test_incident_rows_for_prompt_formats_operational_fields():
    rows = ai_reporter._incident_rows_for_prompt(
        [_group("sig-a", count=7, severity="critical", sample="DB connection failed")]
    )

    assert "1. signature=sig-a" in rows
    assert "platform=facebook worker=FB_Publisher_1" in rows
    assert "severity=critical count=7" in rows
    assert "sample=DB connection failed" in rows
    assert "job_id=job-123 account_id=account-456" in rows
