"""
Facebook Content Compliance Checker
3-layer: DB-backed keywords (cached) → Regex patterns → AI rewrite
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # seconds

_keyword_cache: dict[str, Any] = {
    "block": [],
    "warning": [],
    "last_loaded": 0,
}
_cache_lock = threading.Lock()


def _load_keywords_from_db() -> None:
    """Load active keywords from keyword_blacklist table into cache."""
    block_list: list[str] = []
    warning_list: list[str] = []
    try:
        from sqlalchemy import select

        from app.database.core import SessionLocal
        from app.database.models import KeywordBlacklist

        with SessionLocal() as db:
            rows = db.execute(
                select(KeywordBlacklist.keyword, KeywordBlacklist.severity).where(
                    KeywordBlacklist.is_active.is_(True)
                )
            ).all()

        for row in rows:
            kw, sev = row[0], row[1]
            if not kw:
                continue
            phrase = kw.strip().lower()
            s = (sev or "").strip().upper()
            if s == "VIOLATION":
                block_list.append(phrase)
            elif s == "WARNING":
                warning_list.append(phrase)

        with _cache_lock:
            _keyword_cache["block"] = block_list
            _keyword_cache["warning"] = warning_list
            _keyword_cache["last_loaded"] = time.time()
        logger.info(
            "[Compliance] Loaded %s BLOCK + %s WARNING keywords from DB",
            len(block_list),
            len(warning_list),
        )
        if not block_list and not warning_list:
            logger.warning(
                "[Compliance] No active keywords in DB; only regex rules apply."
            )
    except Exception as e:
        logger.error("[Compliance] Failed to load keywords: %s", e)


def _get_keywords() -> tuple[list[str], list[str]]:
    """Return cached keyword lists; reload if TTL expired."""
    now = time.time()
    last = _keyword_cache.get("last_loaded", 0)
    if now - last > CACHE_TTL:
        _load_keywords_from_db()
    with _cache_lock:
        return (
            list(_keyword_cache.get("block", [])),
            list(_keyword_cache.get("warning", [])),
        )


def invalidate_keyword_cache() -> None:
    """Force reload on next check (call after CRUD)."""
    with _cache_lock:
        _keyword_cache["last_loaded"] = 0.0


class Severity(str, Enum):
    SAFE = "SAFE"
    WARNING = "WARNING"
    VIOLATION = "VIOLATION"


@dataclass
class ViolationItem:
    category: str
    severity: Severity
    evidence: str
    suggestion: str


@dataclass
class ComplianceResult:
    status: Severity
    violations: list[ViolationItem] = field(default_factory=list)
    rewritten: Optional[str] = None


class CompliancePublishError(ValueError):
    """Raised when content must not be published (VIOLATION)."""


ALLOWLIST_PHRASES = [
    "trị giá",
    "miễn phí ship",
    "freeship",
    "flash sale",
    "deal hot",
]

SPAM_PATTERNS = [
    (r"[!?]{3,}", "Dấu câu lặp lại (!!!, ???)", Severity.WARNING),
    (r"[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯ]{5,}", "Chữ IN HOA quá nhiều", Severity.WARNING),
    (r"[\U0001F300-\U0001FFFF]{6,}", "Quá nhiều emoji liên tiếp", Severity.WARNING),
    (r"(#\w+\s*){6,}", "Quá nhiều hashtag", Severity.WARNING),
    (r"(.{15,})\1{2,}", "Lặp lại nội dung", Severity.WARNING),
]


class FBComplianceChecker:
    def _mask_allowlisted_phrases(self, content_lower: str) -> str:
        """Replace allowlisted substrings so keyword scan ignores them."""
        masked = content_lower
        for i, phrase in enumerate(ALLOWLIST_PHRASES):
            if phrase in masked:
                masked = masked.replace(phrase, f" __allow{i}__ ")
        return masked

    def check(self, content: str) -> ComplianceResult:
        violations: list[ViolationItem] = []
        if not content or not content.strip():
            return ComplianceResult(status=Severity.SAFE)

        content_lower = content.lower()
        masked_lower = self._mask_allowlisted_phrases(content_lower)

        block_keywords, warning_keywords = _get_keywords()

        for kw in block_keywords:
            if kw in masked_lower:
                violations.append(
                    ViolationItem(
                        category="prohibited",
                        severity=Severity.VIOLATION,
                        evidence=kw,
                        suggestion=f"Xóa hoặc thay thế '{kw}'",
                    )
                )

        for kw in warning_keywords:
            if kw in masked_lower:
                violations.append(
                    ViolationItem(
                        category="misleading",
                        severity=Severity.WARNING,
                        evidence=kw,
                        suggestion=f"Làm mềm ngôn ngữ: '{kw}'",
                    )
                )

        for pattern, description, severity in SPAM_PATTERNS:
            if re.search(pattern, content):
                violations.append(
                    ViolationItem(
                        category="spam_format",
                        severity=severity,
                        evidence=description,
                        suggestion=f"Sửa định dạng: {description}",
                    )
                )

        if any(v.severity == Severity.VIOLATION for v in violations):
            return ComplianceResult(status=Severity.VIOLATION, violations=violations)
        if violations:
            return ComplianceResult(status=Severity.WARNING, violations=violations)
        return ComplianceResult(status=Severity.SAFE)

    def rewrite(
        self,
        content: str,
        violations: list[ViolationItem],
        product_category: str = "general",
    ) -> str:
        from app.services.gemini_api import GeminiAPIService

        violation_list = "\n".join(
            [f"- [{v.category}] {v.evidence}: {v.suggestion}" for v in violations]
        )

        prompt = (
            f"Bạn là chuyên gia nội dung Facebook tuân thủ chính sách "
            f"cho thị trường Việt Nam.\n\n"
            f"Viết lại comment/caption sau để tuân thủ chính sách "
            f"Facebook, đồng thời giữ nguyên ý nghĩa marketing:\n\n"
            f"Nội dung gốc:\n{content}\n\n"
            f"Vi phạm cần sửa:\n{violation_list}\n\n"
            f"Danh mục sản phẩm: {product_category}\n\n"
            f"Yêu cầu:\n"
            f"- Xóa/thay thế các từ vi phạm\n"
            f"- Giữ nguyên [LINK] nếu có\n"
            f"- Dùng tiếng Việt tự nhiên\n"
            f"- Tối đa 3 emoji\n"
            f"- Dưới 300 ký tự nếu là comment\n"
            f"- Nếu không thể sửa an toàn, trả về: [REJECT]\n\n"
            f"Chỉ trả về nội dung đã viết lại, không giải thích."
        )

        try:
            api = GeminiAPIService()
            result = api.ask(prompt)
            if not result:
                logger.error("[Compliance] Rewrite returned empty from API")
                return content
            if "[REJECT]" in result:
                logger.warning("[Compliance] AI rejected rewrite for: %s", content[:50])
                return "[REJECT]"
            return result.strip()
        except Exception as e:
            logger.error("[Compliance] Rewrite failed: %s", e)
            return content

    def check_and_rewrite(
        self,
        content: str,
        product_category: str = "general",
        max_iterations: int = 2,
    ) -> ComplianceResult:
        result = self.check(content)

        if result.status == Severity.SAFE:
            return result

        if result.status == Severity.VIOLATION:
            return result

        current_content = content
        original_violations = list(result.violations)
        for _ in range(max_iterations):
            rewritten = self.rewrite(
                current_content,
                original_violations,
                product_category,
            )

            if rewritten == "[REJECT]":
                return ComplianceResult(
                    status=Severity.VIOLATION,
                    violations=original_violations,
                    rewritten=None,
                )

            new_result = self.check(rewritten)
            if new_result.status == Severity.SAFE:
                return ComplianceResult(
                    status=Severity.WARNING,
                    violations=original_violations,
                    rewritten=rewritten,
                )
            current_content = rewritten

        return ComplianceResult(
            status=Severity.VIOLATION,
            violations=original_violations,
            rewritten=None,
        )


compliance_checker = FBComplianceChecker()


def log_violation(
    *,
    content: str,
    violations: list[ViolationItem],
    action: str,
    job_id: Optional[int] = None,
    affiliate_id: Optional[int] = None,
    content_type: str = "comment",
    rewritten: Optional[str] = None,
) -> None:
    from app.database.core import SessionLocal
    from app.database.models import ViolationLog

    try:
        with SessionLocal() as db:
            db.add(
                ViolationLog(
                    job_id=job_id,
                    affiliate_id=affiliate_id,
                    content_type=content_type,
                    original_content=content,
                    rewritten_content=rewritten,
                    violations_found=json.dumps(
                        [
                            {"evidence": v.evidence, "category": v.category}
                            for v in violations
                        ],
                        ensure_ascii=False,
                    ),
                    action_taken=action,
                    checked_at=int(time.time()),
                )
            )
            db.commit()
    except Exception as e:
        logger.error("[Compliance] Failed to log violation: %s", e)


def check_before_publish(
    comment_text: str,
    *,
    job_id: Optional[int] = None,
    content_type: str = "comment",
) -> str:
    """
    Hard block VIOLATION. SAFE and WARNING pass through (WARNING logged if any hits).
    """
    result = compliance_checker.check(comment_text)

    if result.violations:
        log_violation(
            content=comment_text,
            violations=result.violations,
            action=result.status.value,
            job_id=job_id,
            content_type=content_type,
        )

    if result.status == Severity.VIOLATION:
        ev = [v.evidence for v in result.violations]
        raise CompliancePublishError(
            f"Nội dung vi phạm chính sách Facebook: {ev}"
        )

    return comment_text
