"""
Affiliate Shopee lookup queue (runtime JSON, no migration).

Flow:
1. AI worker enqueue when caption không khớp kho → PENDING_LOOKUP
2. Processor mỗi tick: thử auto-resolve bằng fuzzy match kho hiện có
3. Operator resolve tay trên /affiliates (paste URL) → RESOLVED + save AffiliateLink
"""
from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.database.models import AffiliateLink, Job
from app.constants import JobStatus

logger = logging.getLogger(__name__)

QUEUE_PATH = Path("storage/db/config/affiliate_lookup_queue.json")

_VI_STOPWORDS = {
    "va", "la", "cua", "cho", "voi", "mot", "nhung", "cac", "dang", "se", "roi",
    "nhe", "nha", "nhi", "qua", "rat", "deo", "day", "kia", "nay", "do", "video",
    "clip", "review", "hang", "shop", "mua", "ban", "san", "pham", "duong", "dep",
}


def normalize_text(value: str) -> str:
    raw = (value or "").strip().lower()
    if not raw:
        return ""
    deaccent = "".join(
        ch for ch in unicodedata.normalize("NFD", raw) if unicodedata.category(ch) != "Mn"
    )
    deaccent = re.sub(r"[^a-z0-9]+", " ", deaccent)
    return re.sub(r"\s+", " ", deaccent).strip()


def load_queue() -> list[dict[str, Any]]:
    try:
        if not QUEUE_PATH.exists():
            return []
        data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("[LOOKUP_QUEUE] load failed: %s", exc)
        return []


def save_queue(items: list[dict[str, Any]]) -> None:
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def list_pending(limit: int = 50) -> list[dict[str, Any]]:
    pending = [x for x in load_queue() if isinstance(x, dict) and x.get("status") == "PENDING_LOOKUP"]
    pending.sort(key=lambda x: int(x.get("created_at") or 0), reverse=True)
    enriched = []
    for item in pending[:limit]:
        row = dict(item)
        hint = (row.get("affiliate_keyword") or "").strip()
        if not hint and row.get("hints"):
            hint = str(row["hints"][0])
        row["search_query"] = hint or " ".join((row.get("hints") or [])[:3])
        # Assist mode: mở đúng Shopee Affiliate thay vì auto-click để tránh pattern bot.
        row["shopee_offer_url"] = "https://affiliate.shopee.vn/offer/product_offer"
        row["shopee_custom_link_url"] = "https://affiliate.shopee.vn/offer/custom_link"
        enriched.append(row)
    return enriched


def pending_count() -> int:
    return sum(1 for x in load_queue() if isinstance(x, dict) and x.get("status") == "PENDING_LOOKUP")


def _score_link(corpus: str, keyword: str) -> int:
    kw_norm = normalize_text(keyword)
    if not kw_norm or not corpus:
        return 0
    score = 0
    if kw_norm in corpus:
        score += 100 + len(kw_norm)
    tokens = [t for t in kw_norm.split() if len(t) >= 3 and t not in _VI_STOPWORDS]
    score += sum(1 for t in tokens if t in corpus) * 15
    return score


def _best_warehouse_match(db: Session, item: dict[str, Any]) -> AffiliateLink | None:
    hints = list(item.get("hints") or [])
    aff_kw = (item.get("affiliate_keyword") or "").strip()
    if aff_kw:
        hints = [aff_kw] + hints
    corpus = " ".join(normalize_text(h) for h in hints if h)
    if not corpus:
        return None

    best: AffiliateLink | None = None
    best_score = 0
    for link in db.query(AffiliateLink).all():
        if not link.keyword:
            continue
        score = _score_link(corpus, link.keyword)
        if score > best_score:
            best_score = score
            best = link
    if best and best_score >= 25:
        return best
    return None


def _maybe_attach_job(db: Session, job_id: int | None, link: AffiliateLink) -> None:
    if not job_id:
        return
    try:
        job = db.query(Job).filter(Job.id == int(job_id)).first()
        if not job or job.status != JobStatus.DRAFT:
            return
        if job.affiliate_url:
            return
        from app.core.queue.job import JobService

        template = link.comment_template or "Xem thêm tại [LINK]"
        JobService.attach_affiliate_to_job(job, affiliate_url=link.url, comment_template=template)
        db.commit()
        if job.affiliate_url and job.tracking_code:
            JobService._register_vercel_tracking(job)
            db.commit()
        logger.info("[LOOKUP_QUEUE] Attached affiliate to DRAFT job=%s keyword=%s", job_id, link.keyword)
    except Exception as exc:
        logger.warning("[LOOKUP_QUEUE] attach job %s failed: %s", job_id, exc)
        db.rollback()


def mark_status(fingerprint: str, status: str, extra: dict[str, Any] | None = None) -> bool:
    queue = load_queue()
    changed = False
    for item in queue:
        if not isinstance(item, dict):
            continue
        if item.get("fingerprint") != fingerprint:
            continue
        item["status"] = status
        item["updated_at"] = int(time.time())
        if extra:
            item.update(extra)
        changed = True
        break
    if changed:
        save_queue(queue)
    return changed


def process_pending_against_warehouse(db: Session, limit: int = 10) -> dict[str, int]:
    """Auto-resolve PENDING items nếu kho affiliate đã có keyword khớp."""
    queue = load_queue()
    resolved = 0
    scanned = 0
    for item in queue:
        if scanned >= limit:
            break
        if not isinstance(item, dict) or item.get("status") != "PENDING_LOOKUP":
            continue
        scanned += 1
        link = _best_warehouse_match(db, item)
        if not link:
            continue
        item["status"] = "RESOLVED"
        item["resolved_via"] = "warehouse_auto"
        item["resolved_keyword"] = link.keyword
        item["resolved_url"] = link.url
        item["updated_at"] = int(time.time())
        resolved += 1
        _maybe_attach_job(db, item.get("job_id"), link)
        logger.info(
            "[LOOKUP_QUEUE] Auto-resolved fingerprint=%s → %s",
            item.get("fingerprint"),
            link.keyword,
        )
    if resolved:
        save_queue(queue)
    return {"scanned": scanned, "resolved": resolved}


def resolve_manual(
    db: Session,
    fingerprint: str,
    keyword: str,
    url: str,
    comment_template: str = "",
    commission_rate: float | None = None,
) -> tuple[bool, dict[str, Any]]:
    keyword = (keyword or "").strip()
    url = (url or "").strip()
    if not fingerprint or not keyword or not url:
        return False, {"error": "Thiếu fingerprint / keyword / url."}

    comment = (comment_template or "").strip() or f"Link {keyword} đây nhé: [LINK]"
    from app.features.affiliates.service import AffiliateService

    ok, err = AffiliateService.save_link(
        db,
        link_id=0,
        keyword=keyword,
        url=url,
        comment_template=comment,
        commission_rate=commission_rate,
    )
    if not ok:
        # Keyword đã tồn tại → cập nhật URL của bản cũ
        existing = db.query(AffiliateLink).filter(AffiliateLink.keyword == keyword).first()
        if existing:
            ok2, err2 = AffiliateService.save_link(
                db,
                link_id=existing.id,
                keyword=keyword,
                url=url,
                comment_template=comment,
                commission_rate=commission_rate,
            )
            if not ok2:
                return False, err2
            link = existing
        else:
            return False, err
    else:
        link = db.query(AffiliateLink).filter(AffiliateLink.keyword == keyword).first()

    queue = load_queue()
    job_id = None
    for item in queue:
        if isinstance(item, dict) and item.get("fingerprint") == fingerprint:
            item["status"] = "RESOLVED"
            item["resolved_via"] = "manual"
            item["resolved_keyword"] = keyword
            item["resolved_url"] = url
            item["updated_at"] = int(time.time())
            job_id = item.get("job_id")
            break
    save_queue(queue)

    if link:
        _maybe_attach_job(db, job_id, link)
    return True, {"keyword": keyword, "url": url}


def dismiss(fingerprint: str) -> bool:
    return mark_status(fingerprint, "DISMISSED")
