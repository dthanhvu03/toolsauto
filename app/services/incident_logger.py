"""Structured incident logging for worker/dispatcher failures."""
from __future__ import annotations

import hashlib
import logging
import re
import traceback
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database.core import SessionLocal
from app.database.models import IncidentGroup, IncidentLog


logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "authorization",
    "auth",
    "access_token",
    "token",
    "cookie",
    "cookies",
    "password",
    "proxy",
    "proxy_auth",
    "proxy_url",
    "set-cookie",
}
MASK_VALUE_PATTERNS = [
    re.compile(r"bearer\s+[a-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"basic\s+[a-z0-9+/=._\-]+", re.IGNORECASE),
    re.compile(r"eyJ[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+\.[a-zA-Z0-9_\-]+"),
]
SEVERITY_RANK = {"warning": 1, "error": 2, "critical": 3}
PROJECT_ROOT_MARKER = "/home/vu/toolsauto/"


def normalize_message(message: str) -> str:
    """Normalize volatile parts so repeated failures share one signature."""
    text = (message or "").lower()
    text = re.sub(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "uuid",
        text,
    )
    text = re.sub(r"\b\d{4}-\d{2}-\d{2}[t\s]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:z|[+-]\d{2}:?\d{2})?\b", "timestamp", text)
    text = re.sub(r"\d+", "n", text)
    return re.sub(r"\s+", " ", text).strip()


def build_error_signature(error_type: str, message: str) -> str:
    normalized = f"{error_type}:{normalize_message(message)}"
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def redact_context(value: Any) -> Any:
    """Return a JSON-safe copy with secrets removed or masked."""
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, raw in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_KEYS or any(part in lowered for part in ("cookie", "token", "password", "proxy_auth")):
                continue
            clean[key_text] = redact_context(raw)
        return clean
    if isinstance(value, list):
        return [redact_context(item) for item in value]
    if isinstance(value, tuple):
        return [redact_context(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            masked = value
            for pattern in MASK_VALUE_PATTERNS:
                masked = pattern.sub("[REDACTED]", masked)
            return masked[:2000]
        return value
    return str(value)[:2000]


def _filtered_stacktrace(exc: BaseException) -> str:
    lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    kept = [line for line in lines if PROJECT_ROOT_MARKER in line or line.strip().startswith(type(exc).__name__)]
    return "".join(kept or lines[-12:])[:8000]


def _classify_category(error_type: str, message: str, context: dict[str, Any]) -> str:
    text = f"{error_type} {message}".lower()
    if any(marker in text for marker in ("selector", "locator", "caption area", "timeout")):
        return "ui_drift"
    if any(marker in text for marker in ("login", "cookie", "checkpoint", "sessioninvalid", "auth")):
        return "auth"
    if "proxy" in text:
        return "proxy"
    if any(marker in text for marker in ("database", "sql", "psycopg", "infailedsqltransaction")):
        return "db"
    if any(marker in text for marker in ("429", "rate limit", "quota")):
        return "rate_limit"
    if any(marker in text for marker in ("connection", "network", "http", "timeout")):
        return "network"
    if context.get("worker_name") and any(marker in text for marker in ("crash", "deadlock", "sigterm")):
        return "worker_crash"
    return "unknown"


class IncidentLogger:
    """Best-effort incident writer. Failures here must not break jobs."""

    @classmethod
    def log_incident(
        cls,
        *,
        exception: BaseException,
        platform: str,
        job_id: int | str | None = None,
        account_id: int | str | None = None,
        feature: str | None = None,
        worker_name: str | None = None,
        severity: str = "error",
        context: dict[str, Any] | None = None,
        source_log_ref: str | None = None,
        db: Session | None = None,
    ) -> str | None:
        owns_session = db is None
        session = db or SessionLocal()
        try:
            message = str(exception)
            error_type = type(exception).__name__
            context_json = redact_context(context or {})
            category = _classify_category(error_type, message, context_json)
            signature = build_error_signature(error_type, message)
            occurred_at = datetime.now(timezone.utc)

            incident = IncidentLog(
                occurred_at=occurred_at,
                platform=platform or "unknown",
                feature=feature,
                category=category,
                worker_name=worker_name,
                job_id=str(job_id) if job_id is not None else None,
                account_id=str(account_id) if account_id is not None else None,
                severity=severity,
                error_type=error_type,
                error_signature=signature,
                error_message=message[:2000],
                stacktrace=_filtered_stacktrace(exception),
                context_json=context_json,
                source_log_ref=source_log_ref,
            )
            session.add(incident)

            stmt = pg_insert(IncidentGroup).values(
                error_signature=signature,
                first_seen_at=occurred_at,
                last_seen_at=occurred_at,
                occurrence_count=1,
                last_job_id=str(job_id) if job_id is not None else None,
                last_account_id=str(account_id) if account_id is not None else None,
                last_platform=platform or "unknown",
                last_worker_name=worker_name,
                last_sample_message=message[:2000],
                severity_max=severity,
                status="open",
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[IncidentGroup.error_signature],
                set_={
                    "last_seen_at": stmt.excluded.last_seen_at,
                    "occurrence_count": IncidentGroup.occurrence_count + 1,
                    "last_job_id": stmt.excluded.last_job_id,
                    "last_account_id": stmt.excluded.last_account_id,
                    "last_platform": stmt.excluded.last_platform,
                    "last_worker_name": stmt.excluded.last_worker_name,
                    "last_sample_message": stmt.excluded.last_sample_message,
                    "severity_max": case(
                        (IncidentGroup.severity_max == "critical", "critical"),
                        (stmt.excluded.severity_max == "critical", "critical"),
                        (IncidentGroup.severity_max == "error", "error"),
                        (stmt.excluded.severity_max == "error", "error"),
                        else_="warning",
                    ),
                    "status": case(
                        (IncidentGroup.status == "resolved", "open"),
                        else_=IncidentGroup.status,
                    ),
                },
            )
            session.execute(stmt)
            session.commit()
            logger.info("[IncidentLogger] Recorded incident signature=%s job_id=%s", signature, job_id)
            return signature
        except Exception:
            session.rollback()
            logger.warning("[IncidentLogger] Failed to record incident", exc_info=True)
            return None
        finally:
            if owns_session:
                session.close()
