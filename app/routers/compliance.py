"""
Keyword blacklist management + violation analytics.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.core import get_db
from app.database.models import KeywordBlacklist
from app.main_templates import templates
from app.services.fb_compliance import invalidate_keyword_cache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/compliance", tags=["compliance"])


class KeywordCreateBody(BaseModel):
    keyword: str = ""
    category: str = "custom"
    severity: str = "WARNING"


class KeywordUpdateBody(BaseModel):
    severity: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[bool] = None


@router.get("/", response_class=HTMLResponse)
def compliance_page(request: Request):
    return templates.TemplateResponse(
        "pages/compliance.html",
        {
            "request": request,
            "active_tab": "compliance",
        },
    )


@router.get("/keywords")
def list_keywords(
    category: str = "",
    severity: str = "",
    search: str = "",
    db: Session = Depends(get_db),
):
    q = db.query(KeywordBlacklist)
    if category:
        q = q.filter(KeywordBlacklist.category == category)
    if severity:
        q = q.filter(KeywordBlacklist.severity == severity)
    if search.strip():
        like = f"%{search.strip().lower()}%"
        q = q.filter(KeywordBlacklist.keyword.ilike(like))
    rows = (
        q.order_by(
            KeywordBlacklist.severity.desc(),
            KeywordBlacklist.category,
            KeywordBlacklist.keyword,
        )
        .all()
    )
    return [
        {
            "id": r.id,
            "keyword": r.keyword,
            "category": r.category,
            "severity": r.severity,
            "source": r.source,
            "is_active": bool(r.is_active),
            "created_at": r.created_at,
            "updated_at": getattr(r, "updated_at", None),
        }
        for r in rows
    ]


@router.post("/keywords")
def add_keyword(payload: KeywordCreateBody, db: Session = Depends(get_db)):
    keyword = payload.keyword.strip().lower()
    category = payload.category.strip() or "custom"
    severity = payload.severity.strip().upper()

    if not keyword:
        return JSONResponse(
            {"error": "Keyword không được để trống."},
            status_code=400,
        )
    if severity not in ("VIOLATION", "WARNING"):
        return JSONResponse(
            {"error": "Severity phải là VIOLATION hoặc WARNING."},
            status_code=400,
        )

    now = int(time.time())
    row = KeywordBlacklist(
        keyword=keyword,
        category=category,
        severity=severity,
        source="manual",
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        invalidate_keyword_cache()
        return {"success": True, "keyword": keyword, "id": row.id}
    except IntegrityError:
        db.rollback()
        return JSONResponse(
            {"error": f"Keyword '{keyword}' đã tồn tại."},
            status_code=409,
        )
    except Exception as e:
        db.rollback()
        logger.exception("add_keyword failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.put("/keywords/{keyword_id}")
def update_keyword(
    keyword_id: int,
    payload: KeywordUpdateBody,
    db: Session = Depends(get_db),
):
    row = db.query(KeywordBlacklist).filter(KeywordBlacklist.id == keyword_id).first()
    if not row:
        return JSONResponse({"error": "Không tìm thấy."}, status_code=404)

    if payload.severity is not None:
        sev = payload.severity.strip().upper()
        if sev not in ("VIOLATION", "WARNING"):
            return JSONResponse(
                {"error": "Severity phải là VIOLATION hoặc WARNING."},
                status_code=400,
            )
        row.severity = sev
    if payload.category is not None:
        row.category = payload.category.strip() or row.category
    if payload.is_active is not None:
        row.is_active = bool(payload.is_active)

    if payload.model_dump(exclude_unset=True) == {}:
        return JSONResponse(
            {"error": "Không có trường nào để cập nhật."},
            status_code=400,
        )

    row.updated_at = int(time.time())
    db.commit()
    invalidate_keyword_cache()
    return {"success": True}


@router.delete("/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.query(KeywordBlacklist).filter(KeywordBlacklist.id == keyword_id).first()
    if not row:
        return JSONResponse({"error": "Không tìm thấy."}, status_code=404)
    if (row.source or "") == "fb_policy":
        return JSONResponse(
            {
                "error": "Từ khóa nguồn fb_policy: hãy tắt Active thay vì xóa, "
                "hoặc xác nhận với admin.",
            },
            status_code=400,
        )
    db.delete(row)
    db.commit()
    invalidate_keyword_cache()
    return {"success": True}


@router.patch("/keywords/{keyword_id}/toggle")
def toggle_keyword(keyword_id: int, db: Session = Depends(get_db)):
    row = db.query(KeywordBlacklist).filter(KeywordBlacklist.id == keyword_id).first()
    if not row:
        return JSONResponse({"error": "Không tìm thấy."}, status_code=404)
    row.is_active = not bool(row.is_active)
    row.updated_at = int(time.time())
    db.commit()
    invalidate_keyword_cache()
    return {"success": True, "is_active": bool(row.is_active)}


@router.get("/analytics")
def get_analytics(days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(days, 366))
    cutoff = int(time.time()) - (days * 86400)
    now_ts = int(time.time())
    today_start = now_ts - (now_ts % 86400)

    def scalar_one(sql: str, params: dict[str, Any]) -> int:
        r = db.execute(text(sql), params).fetchone()
        return int(r[0] or 0) if r and r[0] is not None else 0

    try:
        top_rows = db.execute(
            text(
                """
                SELECT
                  json_extract(j.value, '$.evidence') AS kw,
                  COUNT(*) AS cnt,
                  SUM(CASE WHEN action_taken = 'VIOLATION' THEN 1 ELSE 0 END) AS blocked,
                  SUM(CASE WHEN action_taken = 'WARNING' THEN 1 ELSE 0 END) AS warned
                FROM violation_log, json_each(violation_log.violations_found) AS j
                WHERE checked_at >= :cutoff
                  AND violations_found IS NOT NULL
                  AND TRIM(violations_found) != ''
                  AND violations_found LIKE '[%'
                GROUP BY kw
                HAVING kw IS NOT NULL AND kw != ''
                ORDER BY cnt DESC
                LIMIT 20
                """
            ),
            {"cutoff": cutoff},
        ).fetchall()
    except Exception:
        logger.warning("analytics top_keywords query failed", exc_info=True)
        top_rows = []

    daily_trend = db.execute(
        text(
            """
            SELECT
              date(checked_at, 'unixepoch') AS d,
              COUNT(*) AS total,
              SUM(CASE WHEN action_taken = 'VIOLATION' THEN 1 ELSE 0 END) AS violations,
              SUM(CASE WHEN action_taken = 'WARNING' THEN 1 ELSE 0 END) AS warnings
            FROM violation_log
            WHERE checked_at >= :cutoff
            GROUP BY d
            ORDER BY d DESC
            LIMIT :lim
            """
        ),
        {"cutoff": cutoff, "lim": days},
    ).fetchall()

    breakdown_rows = db.execute(
        text(
            """
            SELECT action_taken, COUNT(*) AS c
            FROM violation_log
            WHERE checked_at >= :cutoff
            GROUP BY action_taken
            """
        ),
        {"cutoff": cutoff},
    ).fetchall()

    category_stats = db.execute(
        text(
            """
            SELECT category, COUNT(*) AS c
            FROM keyword_blacklist
            WHERE is_active = 1
            GROUP BY category
            ORDER BY c DESC
            """
        )
    ).fetchall()

    total_keywords = scalar_one(
        "SELECT COUNT(*) FROM keyword_blacklist WHERE is_active = 1",
        {},
    )
    total_violations = scalar_one(
        "SELECT COUNT(*) FROM violation_log WHERE checked_at >= :cutoff AND action_taken = 'VIOLATION'",
        {"cutoff": cutoff},
    )
    blocked_today = scalar_one(
        "SELECT COUNT(*) FROM violation_log WHERE action_taken = 'VIOLATION' AND checked_at >= :ts",
        {"ts": today_start},
    )
    rewritten_count = scalar_one(
        "SELECT COUNT(*) FROM violation_log WHERE checked_at >= :cutoff AND rewritten_content IS NOT NULL AND TRIM(rewritten_content) != ''",
        {"cutoff": cutoff},
    )

    return {
        "top_keywords": [
            {
                "keyword": r[0],
                "count": int(r[1] or 0),
                "blocked": int(r[2] or 0),
                "warned": int(r[3] or 0),
            }
            for r in top_rows
            if r[0]
        ],
        "daily_trend": [
            {
                "date": r[0],
                "total": int(r[1] or 0),
                "violations": int(r[2] or 0),
                "warnings": int(r[3] or 0),
            }
            for r in daily_trend
        ],
        "breakdown": {r[0] or "UNKNOWN": int(r[1] or 0) for r in breakdown_rows},
        "category_stats": [
            {"category": r[0], "count": int(r[1] or 0)} for r in category_stats
        ],
        "total_keywords": total_keywords,
        "total_violations": total_violations,
        "blocked_today": blocked_today,
        "rewritten_count": rewritten_count,
    }
