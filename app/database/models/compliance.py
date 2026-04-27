from sqlalchemy import Boolean, Column, Integer, String, Text

from app.database.models.base import Base, now_ts


class KeywordBlacklist(Base):
    """Configurable FB compliance keywords (seeded + maintainable)."""
    __tablename__ = "keyword_blacklist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    keyword = Column(String, nullable=False, unique=True, index=True)
    category = Column(String, nullable=False, index=True)
    severity = Column(String, nullable=False)
    source = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(Integer, default=now_ts)
    updated_at = Column(Integer, nullable=True, onupdate=now_ts)


class ComplianceAllowlist(Base):
    """Cụm từ được bỏ qua khi quét keyword (vd: trị giá)."""
    __tablename__ = "compliance_allowlist"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    phrase = Column(String, unique=True, nullable=False, index=True)
    reason = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    source = Column(String, nullable=True)
    created_at = Column(Integer, default=now_ts)


class ComplianceRegexRule(Base):
    """Quy tắc định dạng spam (regex) — mức độ thường là WARNING."""
    __tablename__ = "compliance_regex_rules"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    pattern = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=False)
    severity = Column(String, nullable=False, default="WARNING")
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(Integer, default=now_ts)


class ViolationLog(Base):
    """Audit trail for FB compliance checks (publisher + optional UI)."""
    __tablename__ = "violation_log"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    affiliate_id = Column(Integer, nullable=True, index=True)
    job_id = Column(Integer, nullable=True, index=True)
    content_type = Column(String, nullable=True)
    original_content = Column(Text, nullable=True)
    rewritten_content = Column(Text, nullable=True)
    violations_found = Column(Text, nullable=True)
    action_taken = Column(String, nullable=True, index=True)
    checked_at = Column(Integer, default=now_ts, index=True)
