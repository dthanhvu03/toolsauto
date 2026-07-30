"""Seed FB compliance keywords + allowlist + regex (Postgres-safe). Idempotent."""
from __future__ import annotations

import time

from sqlalchemy.exc import IntegrityError

from app.core.database.core import SessionLocal
from app.core.database.models import (
    ComplianceAllowlist,
    ComplianceRegexRule,
    KeywordBlacklist,
)
from app.core.compliance.facebook_compliance import invalidate_keyword_cache

NOW = int(time.time())

# Meta/affiliate-sensitive phrases for VN beauty + sales captions.
# VIOLATION = hard block publish / rewrite; WARNING = soft flag.
KEYWORDS = [
    # Personal attributes / targeting (Meta ads policy)
    ("bạn đang bị", "personal_attr", "VIOLATION"),
    ("bạn đang mụn", "personal_attr", "VIOLATION"),
    ("bạn béo", "personal_attr", "VIOLATION"),
    ("bạn gầy", "personal_attr", "VIOLATION"),
    ("bạn nghèo", "personal_attr", "VIOLATION"),
    ("bạn nợ", "personal_attr", "VIOLATION"),
    # Absolute health claims (YMYL)
    ("chữa khỏi", "health_claim", "VIOLATION"),
    ("trị dứt điểm", "health_claim", "VIOLATION"),
    ("hết bệnh", "health_claim", "VIOLATION"),
    ("diệt khuẩn 100%", "health_claim", "VIOLATION"),
    ("không tác dụng phụ", "health_claim", "VIOLATION"),
    ("cam kết hết", "health_claim", "VIOLATION"),
    ("đảm bảo khỏi", "health_claim", "VIOLATION"),
    ("100% hiệu quả", "health_claim", "VIOLATION"),
    ("hiệu quả 100%", "health_claim", "VIOLATION"),
    # Misleading before/after / miracle
    ("trước và sau", "misleading", "WARNING"),
    ("trước sau", "misleading", "WARNING"),
    ("thần kỳ", "misleading", "WARNING"),
    ("kỳ diệu", "misleading", "WARNING"),
    ("bí quyết", "misleading", "WARNING"),
    ("ngay lập tức", "misleading", "WARNING"),
    ("chỉ sau 1 đêm", "misleading", "WARNING"),
    ("chỉ sau 1 ngày", "misleading", "WARNING"),
    ("giảm cân thần tốc", "weight_loss", "VIOLATION"),
    ("đốt cháy mỡ", "weight_loss", "VIOLATION"),
    ("tan mỡ", "weight_loss", "VIOLATION"),
    # Hard sell / spammy money claims
    ("làm giàu nhanh", "income_claim", "VIOLATION"),
    ("thu nhập thụ động", "income_claim", "WARNING"),
    ("cam kết lợi nhuận", "income_claim", "VIOLATION"),
    # Direct link / platform spam — caption only (check_before_publish skips
    # category=direct_link for content_type=comment so affiliate comments OK)
    ("http://", "direct_link", "VIOLATION"),
    ("https://", "direct_link", "VIOLATION"),
    ("shopee.vn", "direct_link", "VIOLATION"),
    ("s.shopee.vn", "direct_link", "VIOLATION"),
    ("lazada.vn", "direct_link", "VIOLATION"),
    ("tiki.vn", "direct_link", "VIOLATION"),
    ("click vào link", "direct_link", "WARNING"),
    ("bấm vào link", "direct_link", "WARNING"),
    ("inbox lấy link", "direct_link", "WARNING"),
    # Superlatives / pressure (often reduce distribution)
    ("rẻ nhất", "superlative", "WARNING"),
    ("tốt nhất", "superlative", "WARNING"),
    ("số 1", "superlative", "WARNING"),
    ("#1", "superlative", "WARNING"),
    ("duy nhất", "superlative", "WARNING"),
    ("đảm bảo", "superlative", "WARNING"),
    ("miễn phí 100%", "superlative", "WARNING"),
]

# Research batch 2026-07-30 — Meta Transparency (Health/Wellness, Personal Attributes)
# + VN marketer roundups (CAS, Clickweb) + Meta VN remarks (before-after, unrealistic claims).
# Prefer multi-word phrases to reduce false positives on normal beauty copy.
RESEARCH_KEYWORDS = [
    # Personal attributes (Meta: Privacy / Personal Attributes)
    ("bạn bị mụn", "personal_attr", "VIOLATION"),
    ("bạn bị nám", "personal_attr", "VIOLATION"),
    ("bạn đang béo", "personal_attr", "VIOLATION"),
    ("bạn đang gầy", "personal_attr", "VIOLATION"),
    ("bạn đang nợ", "personal_attr", "VIOLATION"),
    ("bạn có phải", "personal_attr", "WARNING"),
    ("bạn đang gặp rắc rối", "personal_attr", "VIOLATION"),
    ("có phải bạn đang", "personal_attr", "VIOLATION"),
    ("đừng để mình xấu", "personal_attr", "WARNING"),
    ("trông bạn già", "personal_attr", "VIOLATION"),
    ("bạn xấu", "personal_attr", "VIOLATION"),
    ("răng xấu", "personal_attr", "WARNING"),
    ("da xấu", "personal_attr", "WARNING"),
    ("hôi miệng", "health_claim", "WARNING"),
    # Health / beauty absolute claims (Meta Health & Wellness + VN roundups)
    ("trị mụn tận gốc", "health_claim", "VIOLATION"),
    ("trị khỏi nám", "health_claim", "VIOLATION"),
    ("chữa nám", "health_claim", "VIOLATION"),
    ("xóa thâm ngay", "health_claim", "VIOLATION"),
    ("trắng cấp tốc", "health_claim", "VIOLATION"),
    ("triệt gốc", "health_claim", "VIOLATION"),
    ("khỏi hoàn toàn", "health_claim", "VIOLATION"),
    ("khỏi hẳn", "health_claim", "VIOLATION"),
    ("phục hồi 100%", "health_claim", "VIOLATION"),
    ("không cần thuốc", "health_claim", "VIOLATION"),
    ("xóa sẹo 100%", "health_claim", "VIOLATION"),
    ("trẻ hóa tức thì", "health_claim", "VIOLATION"),
    ("cam kết khỏi", "health_claim", "VIOLATION"),
    ("cam kết 100%", "health_claim", "VIOLATION"),
    ("đảm bảo tuyệt đối", "health_claim", "VIOLATION"),
    ("clinically proven", "health_claim", "WARNING"),
    ("clinically tested", "health_claim", "WARNING"),
    ("guaranteed results", "health_claim", "VIOLATION"),
    ("miracle cure", "health_claim", "VIOLATION"),
    ("instant relief", "health_claim", "WARNING"),
    ("chữa ung thư", "health_claim", "VIOLATION"),
    ("chữa tiểu đường", "health_claim", "VIOLATION"),
    ("chữa hiv", "health_claim", "VIOLATION"),
    ("hết ung thư", "health_claim", "VIOLATION"),
    # Weight / body (Meta clickbait + timeframe outcomes)
    ("giảm cân cấp tốc", "weight_loss", "VIOLATION"),
    ("giảm cân nhanh", "weight_loss", "VIOLATION"),
    ("giảm 5kg", "weight_loss", "VIOLATION"),
    ("giảm 10kg", "weight_loss", "VIOLATION"),
    ("eo thon ngay", "weight_loss", "VIOLATION"),
    ("đốt mỡ", "weight_loss", "VIOLATION"),
    ("x kg trong", "weight_loss", "WARNING"),
    ("trong 7 ngày", "timeframe_claim", "WARNING"),
    ("sau 7 ngày", "timeframe_claim", "WARNING"),
    ("trong 1 tuần", "timeframe_claim", "WARNING"),
    ("before after", "misleading", "WARNING"),
    ("before/after", "misleading", "WARNING"),
    ("before-and-after", "misleading", "WARNING"),
    # Finance / income (Meta misleading + VN)
    ("duyệt 100%", "income_claim", "VIOLATION"),
    ("bao vay", "income_claim", "VIOLATION"),
    ("xóa nợ xấu", "income_claim", "VIOLATION"),
    ("nợ xấu vẫn vay", "income_claim", "VIOLATION"),
    ("lợi nhuận chắc chắn", "income_claim", "VIOLATION"),
    ("chắc chắn sinh lời", "income_claim", "VIOLATION"),
    ("cam kết hoàn tiền", "income_claim", "WARNING"),
    ("đổi đời", "income_claim", "WARNING"),
    ("kiếm tiền nhanh", "income_claim", "VIOLATION"),
    ("$500/day", "income_claim", "VIOLATION"),
    ("earn $", "income_claim", "WARNING"),
    # Urgency / fear pressure (distribution risk)
    ("không làm là hối hận", "pressure", "WARNING"),
    ("còn đúng 1 suất", "pressure", "WARNING"),
    ("chỉ hôm nay thôi", "pressure", "WARNING"),
    ("sắp hết hàng", "pressure", "WARNING"),
    ("hotline ngay", "pressure", "WARNING"),
    # Superlatives / monopoly claims
    ("hàng đầu", "superlative", "WARNING"),
    ("độc quyền", "superlative", "WARNING"),
    ("bao đậu", "superlative", "VIOLATION"),
    ("chắc chắn khỏi", "superlative", "VIOLATION"),
]

KEYWORDS = KEYWORDS + RESEARCH_KEYWORDS

ALLOWLIST = [
    ("trị giá", "seed — không nhầm với 'trị' bệnh"),
    ("miễn phí ship", "seed — ship OK"),
    ("freeship", "seed"),
    ("flash sale", "seed"),
    ("deal hot", "seed"),
]

REGEX = [
    (r"[!?]{3,}", "Dấu câu lặp lại (!!!, ???)", "WARNING", 0),
    (r"[A-ZÀÁÂÃÈÉÊÌÍÒÓÔÕÙÚÝĂĐƠƯ]{5,}", "Chữ IN HOA quá nhiều", "WARNING", 1),
    (r"[\U0001F300-\U0001FFFF]{6,}", "Quá nhiều emoji liên tiếp", "WARNING", 2),
    (r"(#\w+\s*){6,}", "Quá nhiều hashtag", "WARNING", 3),
    (r"(.{15,})\1{2,}", "Lặp lại nội dung", "WARNING", 4),
]


def main() -> None:
    db = SessionLocal()
    added_kw = skipped_kw = 0
    try:
        existing = {
            (r.keyword or "").strip().lower()
            for r in db.query(KeywordBlacklist.keyword).all()
        }
        for kw, cat, sev in KEYWORDS:
            phrase = kw.strip().lower()
            if phrase in existing:
                skipped_kw += 1
                continue
            db.add(
                KeywordBlacklist(
                    keyword=phrase,
                    category=cat,
                    severity=sev,
                    source=(
                        "research_meta_vn_2026"
                        if (kw, cat, sev) in RESEARCH_KEYWORDS
                        else "seed_beauty_affiliate_2026"
                    ),
                    is_active=True,
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            existing.add(phrase)
            added_kw += 1

        existing_al = {
            (r.phrase or "").strip().lower()
            for r in db.query(ComplianceAllowlist.phrase).all()
        }
        added_al = 0
        for phrase, reason in ALLOWLIST:
            p = phrase.strip().lower()
            if p in existing_al:
                continue
            db.add(
                ComplianceAllowlist(
                    phrase=p,
                    reason=reason,
                    is_active=True,
                    source="seed",
                    created_at=NOW,
                )
            )
            existing_al.add(p)
            added_al += 1

        existing_rx = {
            (r.pattern or "").strip() for r in db.query(ComplianceRegexRule.pattern).all()
        }
        added_rx = 0
        for pat, desc, sev, so in REGEX:
            if pat in existing_rx:
                continue
            db.add(
                ComplianceRegexRule(
                    pattern=pat,
                    description=desc,
                    severity=sev,
                    is_active=True,
                    sort_order=so,
                    created_at=NOW,
                )
            )
            existing_rx.add(pat)
            added_rx += 1

        db.commit()
        invalidate_keyword_cache()
        print(
            f"OK added_kw={added_kw} skipped_kw={skipped_kw} "
            f"added_allow={added_al} added_regex={added_rx}"
        )
        print(
            "totals",
            db.query(KeywordBlacklist).filter(KeywordBlacklist.is_active.is_(True)).count(),
            db.query(ComplianceAllowlist).filter(ComplianceAllowlist.is_active.is_(True)).count(),
            db.query(ComplianceRegexRule).filter(ComplianceRegexRule.is_active.is_(True)).count(),
        )
    except IntegrityError as e:
        db.rollback()
        print("IntegrityError", e)
    finally:
        db.close()


if __name__ == "__main__":
    main()
