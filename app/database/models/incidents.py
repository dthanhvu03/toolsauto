from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database.models.base import Base


class IncidentLog(Base):
    """Append-only structured incident events for AI health reporting."""

    __tablename__ = "incident_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    platform = Column(String, nullable=False)
    feature = Column(String, nullable=True)
    category = Column(String, nullable=False, default="unknown", server_default="unknown")
    worker_name = Column(String, nullable=True)
    job_id = Column(String, nullable=True)
    account_id = Column(String, nullable=True)

    severity = Column(String, nullable=False)
    error_type = Column(String, nullable=False)
    error_signature = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)
    stacktrace = Column(Text, nullable=True)

    context_json = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=False, default=dict, server_default="{}")
    source_log_ref = Column(Text, nullable=True)
    resolved = Column(Boolean, nullable=False, default=False, server_default="false")

    __table_args__ = (
        CheckConstraint(
            "category IN ('ui_drift','auth','proxy','db','network','rate_limit','worker_crash','resource','unknown')",
            name="ck_incident_logs_category",
        ),
        CheckConstraint(
            "severity IN ('warning','error','critical')",
            name="ck_incident_logs_severity",
        ),
        Index("idx_incident_signature_time", "error_signature", "occurred_at"),
        Index("idx_incident_platform_time", "platform", "occurred_at"),
        Index("idx_incident_account_time", "account_id", "occurred_at"),
        Index("idx_incident_severity_time", "severity", "occurred_at"),
        Index("idx_incident_category_time", "category", "occurred_at"),
        Index("idx_incident_occurred_at", "occurred_at"),
        Index("idx_incident_job_id", "job_id"),
    )


class IncidentGroup(Base):
    """Denormalized incident aggregate used by reports and burst alerts."""

    __tablename__ = "incident_groups"

    error_signature = Column(String, primary_key=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)
    occurrence_count = Column(BigInteger, nullable=False, default=1, server_default="1")

    last_job_id = Column(String, nullable=True)
    last_account_id = Column(String, nullable=True)
    last_platform = Column(String, nullable=True)
    last_worker_name = Column(String, nullable=True)
    last_sample_message = Column(Text, nullable=True)
    severity_max = Column(String, nullable=False)

    status = Column(String, nullable=False, default="open", server_default="open")
    acknowledged_by = Column(String, nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('open','acknowledged','resolved','ignored')",
            name="ck_incident_groups_status",
        ),
        Index("idx_groups_status_lastseen", "status", "last_seen_at"),
        Index("idx_groups_count", "occurrence_count"),
    )
