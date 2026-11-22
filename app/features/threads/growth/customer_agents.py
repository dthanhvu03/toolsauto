"""Aggregate status for the two PLAN-178 roles inside the existing worker.

This is reporting only: no model calls, customer text, send tools or queue writes.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)
DEFAULT_STATUS_PATH = Path(__file__).resolve().parents[4] / "reports/customer-agents/status.json"
PHASES = {"working", "waiting", "quiet_hours", "disabled", "no_ready_account", "error"}
ACCOUNT_LABELS = {"us28qt": "primary", "anlinh": "store"}


def _stamp(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value is not None else None


def _count(report, key: str) -> int:
    value = getattr(report, key, 0)
    return max(0, int(value)) if isinstance(value, (int, float)) else 0


def cycle_counts(report) -> dict:
    """Whitelist counters; never serialize a raw CycleReport containing customer data."""
    dms = getattr(report, "dms", []) or []
    return {
        "scanned_posts": _count(report, "scanned"),
        "opportunities_reviewed": _count(report, "opportunities_reviewed"),
        "opportunities_blocked": _count(report, "opportunities_blocked"),
        "buyer_opportunities": _count(report, "buyer_opportunities"),
        "help_opportunities": _count(report, "help_opportunities"),
        "queue_replies_blocked": _count(report, "queue_replies_blocked"),
        "drafts_created": _count(report, "ingested"),
        "public_replies_sent": _count(report, "posted"),
        "buyer_replies_sent": _count(report, "buyer_replies_sent"),
        "help_replies_sent": _count(report, "help_replies_sent"),
        "public_send_failures": _count(report, "failed"),
        "dm_checks": _count(report, "dm_checks"),
        "followup_pages_checked": _count(report, "followup_checks"),
        "public_followups_sent": len(getattr(report, "followups", []) or []),
        "dm_replies_sent": sum(bool(d.get("sent", d.get("action") == "reply")) for d in dms),
        "handoffs": _count(report, "support_handoffs")
        + sum(d.get("action") in ("handoff", "handoff_more") for d in dms),
        "dm_failures": sum(d.get("action") == "failed" for d in dms),
        "errors": len(getattr(report, "errors", []) or []),
    }


class CustomerAgentStatus:
    """Best-effort atomic report; the worker and DB remain the delivery authority."""

    def __init__(self, path: Path = DEFAULT_STATUS_PATH):
        self.path = Path(path)
        self.started_at = datetime.now(timezone.utc)
        self.last_cycle: dict | None = None
        self.last_activity: dict | None = None

    def update(self, *, phase: str, now: datetime, cfg, roles: dict, report=None,
               last_scan: datetime | None = None, last_dm: dict | None = None,
               last_followup: dict | None = None, error_type: str | None = None,
               active_role: str | None = None) -> bool:
        if phase not in PHASES:
            raise ValueError("Unknown customer-agent phase")
        counts = cycle_counts(report) if report is not None else None
        cycle = {"observed_at": _stamp(now), "counts": counts} if counts is not None else None
        if cycle is not None and phase != "working":
            self.last_cycle = cycle
            if any(counts[k] for k in ("drafts_created", "public_replies_sent", "public_send_failures",
                                      "public_followups_sent", "dm_replies_sent", "handoffs", "dm_failures", "errors")):
                self.last_activity = cycle
        accounts = {
            ACCOUNT_LABELS[key]: {"enabled": bool(role.enabled),
                                  "bots": [b for b in role.bots if b in ("cashbot", "ai_store")],
                                  "dm_enabled": bool(role.dm)}
            for key, role in roles.items() if key in ACCOUNT_LABELS
        }
        def state(role: str) -> str:
            return "waiting" if phase == "working" and role != active_role else phase

        payload = {
            "schema_version": 1,
            "plan": "PLAN-178",
            "strategy_plan": "PLAN-179",
            "strategy_review_path": "reports/customer-agents/strategy/latest.json",
            "missions": {
                "acquisition": "Tìm nhu cầu mua và câu hỏi CapCut cụ thể; trợ giúp không link.",
                "engagement": "Trả lời inbound đúng nhu cầu; chuyển ca tiền/đơn/bảo hành cho chủ shop.",
                "measurement": "Đo khách mới dùng thật và hội thoại theo cửa sổ 24h/7 ngày.",
                "conversion": "Mỗi6giờ chọn tối đa2 thử nghiệm với điều kiện giữ/bỏ.",
                "content": "Mỗi6giờ chuẩn bị2 nháp từ nhu cầu có bằng chứng, chưa tự đăng.",
            },
            "heartbeat_at": _stamp(now),
            "worker_started_at": _stamp(self.started_at),
            "worker_pid": os.getpid(),
            "phase": phase,
            "error_type": error_type,
            "stale_after_seconds": 2700 if phase == "working" else 180,
            "quiet_hours_vn": str(cfg.quiet_hours),
            "scan_interval_minutes": int(cfg.scan_interval_min),
            "accounts": accounts,
            "agents": {
                "acquisition": {"state": state("acquisition"), "channel": "public_posts",
                                "last_scan_started_at": _stamp(last_scan)},
                "engagement": {
                    "state": state("engagement"), "channels": ["public_inbound", "dm_inbound"],
                    "dm_enabled_accounts": [k for k, r in accounts.items() if r["enabled"] and r["dm_enabled"]],
                    "last_dm_attempt_at": {ACCOUNT_LABELS[k]: _stamp(v) for k, v in (last_dm or {}).items()
                                           if k in ACCOUNT_LABELS},
                    "last_followup_attempt_at": {ACCOUNT_LABELS[k]: _stamp(v)
                                                 for k, v in (last_followup or {}).items() if k in ACCOUNT_LABELS},
                },
            },
            "current_cycle": cycle if phase == "working" else None,
            "last_cycle": self.last_cycle,
            "last_activity": self.last_activity,
            "limits": ["single_existing_sender", "inbound_only_dm", "existing_quotas_and_quiet_hours",
                       "counts_are_not_acquired_customers"],
        }
        tmp = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.path.parent,
                                             prefix=".customer-agents-", suffix=".tmp", delete=False) as f:
                tmp = Path(f.name)
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
            tmp.replace(self.path)
            return True
        except OSError as exc:
            logger.warning("customer-agent status unavailable (%s)", type(exc).__name__)
            return False
        finally:
            if tmp is not None:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
