"""Daily AI health report for structured incidents."""
from __future__ import annotations

import html
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.utils.logger import setup_shared_logger

setup_shared_logger("app")
logger = setup_shared_logger(__name__ if __name__ != "__main__" else "ai_reporter")

import app.config as config
from app.database.core import SessionLocal
from app.database.models import IncidentGroup
from app.services.ai_runtime import pipeline
from app.services.notifier_service import NotifierService, TelegramNotifier


def _fetch_top_incidents(limit: int = 20) -> list[IncidentGroup]:
    since = datetime.now(timezone.utc) - timedelta(days=1)
    db = SessionLocal()
    try:
        return (
            db.query(IncidentGroup)
            .filter(
                IncidentGroup.last_seen_at >= since,
                IncidentGroup.status.in_(["open", "acknowledged"]),
            )
            .order_by(IncidentGroup.occurrence_count.desc(), IncidentGroup.last_seen_at.desc())
            .limit(limit)
            .all()
        )
    finally:
        db.close()


def _incident_rows_for_prompt(groups: list[IncidentGroup]) -> str:
    lines = []
    for idx, group in enumerate(groups, 1):
        lines.append(
            "\n".join(
                [
                    f"{idx}. signature={group.error_signature}",
                    f"   platform={group.last_platform or '-'} worker={group.last_worker_name or '-'}",
                    f"   severity={group.severity_max} count={group.occurrence_count}",
                    f"   last_seen={group.last_seen_at}",
                    f"   sample={group.last_sample_message or '-'}",
                    f"   job_id={group.last_job_id or '-'} account_id={group.last_account_id or '-'}",
                ]
            )
        )
    return "\n\n".join(lines)


def _build_prompt(groups: list[IncidentGroup]) -> str:
    return f"""
Bạn là AI vận hành hệ thống ToolsAuto. Hãy viết Daily Health Report bằng tiếng Việt, ngắn gọn, có Markdown.

Yêu cầu:
- Không bịa nguyên nhân nếu evidence chưa đủ.
- Mỗi nhận định root cause phải gắn với signature/job/platform/count.
- Chỉ đề xuất hành động vận hành an toàn; không đề xuất tự sửa code, không auto-healing.
- Format gồm: Tóm tắt, Top lỗi, Khả năng nguyên nhân, Hành động đề xuất, Cần người kiểm tra.

Dữ liệu top incident groups trong 24h:

{_incident_rows_for_prompt(groups)}
""".strip()


def _fallback_report(groups: list[IncidentGroup], reason: str) -> str:
    rows = []
    for idx, group in enumerate(groups[:20], 1):
        rows.append(
            f"{idx}. <b>{html.escape(group.severity_max.upper())}</b> "
            f"{html.escape(group.error_signature)} "
            f"({int(group.occurrence_count)} lần) - {html.escape(group.last_platform or '-')}: "
            f"{html.escape((group.last_sample_message or '-')[:180])}"
        )
    return (
        "<b>Daily Health Report</b>\n"
        f"<i>Gemini unavailable: {html.escape(reason)}</i>\n\n"
        + ("\n".join(rows) if rows else "Không có incident mới trong 24h.")
    )


def build_report(groups: list[IncidentGroup]) -> str:
    if not groups:
        return "<b>Daily Health Report</b>\nKhông có incident mới trong 24h."

    prompt = _build_prompt(groups)
    try:
        response, meta = pipeline.generate_text(prompt)
        if meta.get("ok") and response:
            return "<b>Daily Health Report</b>\n<pre>" + html.escape(response[:3500]) + "</pre>"
        return _fallback_report(groups, meta.get("fail_reason", "empty response"))
    except Exception as exc:
        logger.warning("[AI Reporter] Report generation failed: %s", exc)
        return _fallback_report(groups, str(exc))


def send_report(report: str) -> None:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        raise RuntimeError("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID")
    NotifierService.register(TelegramNotifier(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID))
    NotifierService._broadcast(report)


def main() -> int:
    groups = _fetch_top_incidents(limit=20)
    report = build_report(groups)
    send_report(report)
    logger.info("[AI Reporter] Sent daily health report. groups=%s", len(groups))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
