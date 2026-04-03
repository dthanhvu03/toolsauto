"""
Keyword blacklist management + violation analytics.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import time
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.core import get_db
from app.database.models import ComplianceAllowlist, KeywordBlacklist, ViolationLog
from app.main_templates import templates
from app.services.fb_compliance import (
    Severity,
    compliance_checker,
    invalidate_keyword_cache,
)

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


class TestCheckBody(BaseModel):
    content: str = ""


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


@router.get("/keywords/sample-csv")
def download_sample_csv():
    """Download sample CSV for bulk keyword import."""
    sample = (
        "keyword,category,severity\n"
        "chữa khỏi bệnh,health,VIOLATION\n"
        "trị dứt điểm,health,VIOLATION\n"
        "giảm cân nhanh,health,VIOLATION\n"
        "không tác dụng phụ,health,VIOLATION\n"
        "cam kết hoàn tiền 100%,financial,VIOLATION\n"
        "thu nhập thụ động,financial,VIOLATION\n"
        "100% hiệu quả,misleading,WARNING\n"
        "chỉ còn hôm nay,urgency,WARNING\n"
        "tag bạn bè để nhận,engagement_bait,WARNING\n"
        "share để nhận quà,engagement_bait,WARNING\n"
    )
    return Response(
        content=sample.encode("utf-8-sig"),
        media_type="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=keyword_import_sample.csv",
        },
    )


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


@router.post("/keywords/bulk-import")
async def bulk_import_keywords(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Import keywords from CSV: keyword,category,severity."""
    raw = await file.read()
    try:
        text_content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return JSONResponse(
            {"error": "File phải là UTF-8."},
            status_code=400,
        )

    reader = csv.DictReader(io.StringIO(text_content))
    imported = 0
    skipped = 0
    errors: list[str] = []
    now = int(time.time())

    for i, row in enumerate(reader, 1):
        keyword = (row.get("keyword") or "").strip().lower()
        category = (row.get("category") or "custom").strip() or "custom"
        severity = (row.get("severity") or "WARNING").strip().upper()

        if not keyword:
            skipped += 1
            continue
        if severity not in ("VIOLATION", "WARNING"):
            errors.append(f"Dòng {i}: severity không hợp lệ")
            skipped += 1
            continue

        try:
            dup = db.execute(
                text(
                    "SELECT 1 FROM keyword_blacklist WHERE keyword = :kw LIMIT 1"
                ),
                {"kw": keyword},
            ).fetchone()
            if dup:
                skipped += 1
                continue
            db.execute(
                text(
                    """
                    INSERT INTO keyword_blacklist
                    (keyword, category, severity, source, is_active, created_at, updated_at)
                    VALUES (:kw, :cat, :sev, 'bulk_import', 1, :now, :now)
                    """
                ),
                {"kw": keyword, "cat": category, "sev": severity, "now": now},
            )
            imported += 1
        except Exception as e:
            errors.append(f"Dòng {i} '{keyword}': {e!s}")
            skipped += 1

    db.commit()
    invalidate_keyword_cache()
    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors[:10],
    }


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


@router.get("/violations")
def get_violations(
    days: int = 30,
    action: str = "",
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """Paginated violation log with filters."""
    days = max(1, min(days, 366))
    limit = max(1, min(limit, 100))
    page = max(1, page)
    cutoff = int(time.time()) - (days * 86400)
    offset = (page - 1) * limit

    base_where = "checked_at >= :cutoff"
    params: dict[str, Any] = {"cutoff": cutoff}
    if action:
        base_where += " AND action_taken = :action"
        params["action"] = action

    count_sql = f"SELECT COUNT(*) FROM violation_log WHERE {base_where}"
    total = db.execute(text(count_sql), params).scalar() or 0
    total = int(total)

    list_sql = f"""
        SELECT id, affiliate_id, job_id, content_type,
               original_content, rewritten_content,
               violations_found, action_taken, checked_at
        FROM violation_log
        WHERE {base_where}
        ORDER BY checked_at DESC
        LIMIT :limit OFFSET :offset
    """
    list_params = {**params, "limit": limit, "offset": offset}
    rows = db.execute(text(list_sql), list_params).fetchall()

    def parse_violations(raw: Any) -> list[dict[str, Any]]:
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return []
        if isinstance(raw, list):
            return raw
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    violations = []
    for r in rows:
        violations.append(
            {
                "id": r[0],
                "affiliate_id": r[1],
                "job_id": r[2],
                "content_type": r[3],
                "original_content": r[4],
                "rewritten_content": r[5],
                "violations_found": parse_violations(r[6]),
                "action_taken": r[7],
                "checked_at": r[8],
            }
        )

    total_pages = max(1, (total + limit - 1) // limit) if total else 1
    return {
        "violations": violations,
        "total": total,
        "page": page,
        "total_pages": total_pages,
    }


@router.get("/violations/{viol_id}")
def get_violation_detail(viol_id: int, db: Session = Depends(get_db)):
    row = db.query(ViolationLog).filter(ViolationLog.id == viol_id).first()
    if not row:
        return JSONResponse({"error": "Không tìm thấy."}, status_code=404)

    viols: list[dict[str, Any]] = []
    if row.violations_found:
        try:
            parsed = json.loads(row.violations_found)
            viols = parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            viols = []

    return {
        "id": row.id,
        "affiliate_id": row.affiliate_id,
        "job_id": row.job_id,
        "content_type": row.content_type,
        "original_content": row.original_content,
        "rewritten_content": row.rewritten_content,
        "violations_found": viols,
        "action_taken": row.action_taken,
        "checked_at": row.checked_at,
    }


@router.post("/test-check")
def test_check(payload: TestCheckBody):
    """
    Test compliance on arbitrary text. Returns structured violations only
    (no server-side HTML — client highlights safely).
    """
    content = (payload.content or "").strip()
    if not content:
        return JSONResponse(
            {"error": "Nội dung không được để trống."},
            status_code=400,
        )

    result = compliance_checker.check(content)

    def sev_str(s: Any) -> str:
        if isinstance(s, Severity):
            return s.value
        return str(s)

    violations_out = [
        {
            "category": v.category,
            "severity": sev_str(v.severity),
            "evidence": v.evidence,
            "suggestion": v.suggestion,
        }
        for v in result.violations
    ]

    return {
        "status": sev_str(result.status),
        "violations": violations_out,
        "violation_count": sum(
            1 for v in result.violations if sev_str(v.severity) == "VIOLATION"
        ),
        "warning_count": sum(
            1 for v in result.violations if sev_str(v.severity) == "WARNING"
        ),
    }


@router.post("/ai-suggest-keywords")
def ai_suggest_keywords(db: Session = Depends(get_db)):
    """Suggest blacklist keywords from recent violation_log via Gemini API."""
    cutoff = int(time.time()) - 30 * 86400
    rows = db.execute(
        text(
            """
            SELECT violations_found, original_content
            FROM violation_log
            WHERE checked_at >= :cutoff
              AND violations_found IS NOT NULL
              AND TRIM(violations_found) != ''
            ORDER BY checked_at DESC
            LIMIT 100
            """
        ),
        {"cutoff": cutoff},
    ).fetchall()

    if not rows:
        return {
            "suggestions": [],
            "message": "Chưa có đủ dữ liệu vi phạm để phân tích.",
        }

    violation_samples: list[dict[str, Any]] = []
    for r in rows[:20]:
        try:
            viols = json.loads(r[0]) if r[0] else []
            evidences = [
                v.get("evidence")
                for v in viols
                if isinstance(v, dict) and v.get("evidence")
            ]
            violation_samples.append(
                {
                    "content": (r[1] or "")[:200],
                    "violations": evidences,
                }
            )
        except Exception:
            continue

    if not violation_samples:
        return {
            "suggestions": [],
            "message": "Chưa có mẫu violations_found hợp lệ.",
        }

    prompt = (
        "Phân tích các nội dung vi phạm chính sách Facebook sau "
        "từ thị trường affiliate Việt Nam:\n\n"
        f"{json.dumps(violation_samples, ensure_ascii=False, indent=2)}\n\n"
        "Dựa trên pattern, đề xuất 10 từ khóa/cụm từ mới nên thêm "
        "vào blacklist.\n\n"
        "Trả về JSON (KHÔNG markdown, KHÔNG backtick):\n"
        '{"suggestions": ['
        '{"keyword": "...", "category": "health|financial|'
        'misleading|engagement_bait|spam_format", '
        '"severity": "VIOLATION|WARNING", "reason": "..."}'
        ", ...]}"
    )

    try:
        from app.services.gemini_api import GeminiAPIService

        api = GeminiAPIService()
        raw = api.ask(prompt)
        if not raw or not str(raw).strip():
            return JSONResponse(
                {"error": "AI không trả về nội dung."},
                status_code=503,
            )
        cleaned = str(raw).strip()
        if cleaned.startswith("```"):
            parts = cleaned.split("```")
            cleaned = parts[1] if len(parts) > 1 else cleaned
            if cleaned.lstrip().startswith("json"):
                cleaned = cleaned.lstrip()[4:].lstrip()
        data = json.loads(cleaned.strip())
        if not isinstance(data, dict):
            raise ValueError("Response is not an object")
        return data
    except json.JSONDecodeError as e:
        logger.error("[Compliance] AI suggest JSON parse failed: %s", e)
        return JSONResponse(
            {"error": "AI trả về định dạng không hợp lệ."},
            status_code=503,
        )
    except Exception as e:
        logger.error("[Compliance] AI suggest failed: %s", e, exc_info=True)
        return JSONResponse(
            {"error": "AI không thể phân tích lúc này."},
            status_code=503,
        )


@router.get("/export-keywords")
def export_keywords(db: Session = Depends(get_db)):
    """Export active + inactive keywords as CSV."""
    rows = (
        db.query(KeywordBlacklist)
        .order_by(KeywordBlacklist.keyword)
        .all()
    )

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            ["keyword", "category", "severity", "source", "is_active"]
        )
        yield "\ufeff" + buf.getvalue()
        for r in rows:
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [
                    r.keyword,
                    r.category,
                    r.severity,
                    r.source or "",
                    1 if r.is_active else 0,
                ]
            )
            yield buf.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="keywords_export.csv"'
        },
    )


@router.get("/export-violations")
def export_violations(days: int = 30, db: Session = Depends(get_db)):
    """Export violation log as CSV (streaming)."""
    days = max(1, min(days, 366))
    cutoff = int(time.time()) - (days * 86400)
    rows = db.execute(
        text(
            """
            SELECT id, content_type, original_content,
                   violations_found, action_taken,
                   datetime(checked_at, 'unixepoch', 'localtime')
            FROM violation_log
            WHERE checked_at >= :cutoff
            ORDER BY checked_at DESC
            """
        ),
        {"cutoff": cutoff},
    ).fetchall()

    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(
            [
                "ID",
                "Loại",
                "Nội dung gốc",
                "Vi phạm",
                "Hành động",
                "Thời gian",
            ]
        )
        yield "\ufeff" + buf.getvalue()
        for r in rows:
            violations = ""
            try:
                viols = json.loads(r[3]) if r[3] else []
                if isinstance(viols, list):
                    violations = "; ".join(
                        str(v.get("evidence", "")) for v in viols if isinstance(v, dict)
                    )
            except (json.JSONDecodeError, TypeError):
                pass
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(
                [
                    r[0],
                    r[1],
                    (r[2] or "")[:500],
                    violations,
                    r[4],
                    r[5],
                ]
            )
            yield buf.getvalue()

    filename = f"violations_{days}days.csv"
    return StreamingResponse(
        generate(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@router.get("/allowlist")
def list_allowlist(db: Session = Depends(get_db)):
    rows = (
        db.query(ComplianceAllowlist)
        .order_by(ComplianceAllowlist.phrase)
        .all()
    )
    return [
        {
            "id": r.id,
            "phrase": r.phrase,
            "reason": getattr(r, "reason", None),
            "is_active": bool(r.is_active),
            "created_at": r.created_at,
        }
        for r in rows
    ]


@router.post("/allowlist")
def add_allowlist(payload: dict, db: Session = Depends(get_db)):
    phrase = (payload.get("phrase") or "").strip().lower()
    reason = (payload.get("reason") or "").strip() or None
    if not phrase:
        return JSONResponse(
            {"error": "Phrase không được để trống."},
            status_code=400,
        )
    now = int(time.time())
    row = ComplianceAllowlist(
        phrase=phrase,
        reason=reason,
        is_active=True,
        source="manual",
        created_at=now,
    )
    db.add(row)
    try:
        db.commit()
        invalidate_keyword_cache()
        return JSONResponse({"success": True})
    except IntegrityError:
        db.rollback()
        return JSONResponse(
            {"error": f"Phrase '{phrase}' đã tồn tại."},
            status_code=409,
        )
    except Exception as e:
        db.rollback()
        logger.exception("add_allowlist failed")
        return JSONResponse({"error": str(e)}, status_code=500)


@router.delete("/allowlist/{item_id}")
def delete_allowlist(item_id: int, db: Session = Depends(get_db)):
    row = (
        db.query(ComplianceAllowlist)
        .filter(ComplianceAllowlist.id == item_id)
        .first()
    )
    if not row:
        return JSONResponse({"error": "Không tìm thấy."}, status_code=404)
    db.delete(row)
    db.commit()
    invalidate_keyword_cache()
    return JSONResponse({"success": True})


@router.get("/account-stats")
def get_account_stats(days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(days, 366))
    cutoff = int(time.time()) - (days * 86400)
    rows = db.execute(
        text(
            """
            SELECT
                vl.affiliate_id,
                MAX(COALESCE(al.keyword, '')) AS kw,
                COUNT(*) AS total,
                SUM(CASE WHEN vl.action_taken = 'VIOLATION' THEN 1 ELSE 0 END) AS blocked
            FROM violation_log vl
            LEFT JOIN affiliate_links al ON vl.affiliate_id = al.id
            WHERE vl.checked_at >= :cutoff
              AND vl.affiliate_id IS NOT NULL
            GROUP BY vl.affiliate_id
            ORDER BY total DESC
            LIMIT 20
            """
        ),
        {"cutoff": cutoff},
    ).fetchall()

    out = []
    for r in rows:
        aff_id, kw, total, blocked = r[0], r[1], int(r[2] or 0), int(r[3] or 0)
        label = (kw or "").strip() or f"ID #{aff_id}"
        out.append(
            {
                "affiliate_id": aff_id,
                "keyword": label,
                "total": total,
                "blocked": blocked,
                "block_rate": round(blocked / total * 100) if total > 0 else 0,
            }
        )
    return out
