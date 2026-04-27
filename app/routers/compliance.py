"""
Keyword blacklist management + violation analytics.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.database.core import get_db
from app.schemas.compliance import KeywordCreateBody, KeywordUpdateBody, TestCheckBody
from app.services import compliance_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/compliance", tags=["compliance"])

@router.get("/", response_class=HTMLResponse)
def compliance_page(request: Request):
    return compliance_service.compliance_page(request)

@router.get("/keywords")
def list_keywords(
    category: str = "",
    severity: str = "",
    search: str = "",
    db: Session = Depends(get_db),
):
    return compliance_service.list_keywords(category, severity, search, db)

@router.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    return compliance_service.get_categories(db)

@router.get("/keywords/sample-csv")
def download_sample_csv(db: Session = Depends(get_db)):
    return compliance_service.download_sample_csv(db)

@router.post("/keywords")
def add_keyword(payload: KeywordCreateBody, db: Session = Depends(get_db)):
    return compliance_service.add_keyword(payload, db)

@router.post("/keywords/bulk-import")
async def bulk_import_keywords(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    return await compliance_service.bulk_import_keywords(file, db)

@router.put("/keywords/{keyword_id}")
def update_keyword(
    keyword_id: int,
    payload: KeywordUpdateBody,
    db: Session = Depends(get_db),
):
    return compliance_service.update_keyword(keyword_id, payload, db)

@router.delete("/keywords/{keyword_id}")
def delete_keyword(keyword_id: int, db: Session = Depends(get_db)):
    return compliance_service.delete_keyword(keyword_id, db)

@router.patch("/keywords/{keyword_id}/toggle")
def toggle_keyword(keyword_id: int, db: Session = Depends(get_db)):
    return compliance_service.toggle_keyword(keyword_id, db)

@router.get("/analytics")
def get_analytics(days: int = 30, db: Session = Depends(get_db)):
    return compliance_service.get_analytics(days, db)

@router.get("/violations")
def get_violations(
    days: int = 30,
    action: str = "",
    page: int = 1,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    return compliance_service.get_violations(days, action, page, limit, db)

@router.get("/violations/{viol_id}")
def get_violation_detail(viol_id: int, db: Session = Depends(get_db)):
    return compliance_service.get_violation_detail(viol_id, db)

@router.post("/test-check")
def test_check(payload: TestCheckBody):
    return compliance_service.test_check(payload)

@router.post("/ai-suggest-keywords")
def ai_suggest_keywords(db: Session = Depends(get_db)):
    return compliance_service.ai_suggest_keywords(db)

@router.get("/export-keywords")
def export_keywords(db: Session = Depends(get_db)):
    return compliance_service.export_keywords(db)

@router.get("/export-violations")
def export_violations(days: int = 30, db: Session = Depends(get_db)):
    return compliance_service.export_violations(days, db)

@router.get("/allowlist")
def list_allowlist(db: Session = Depends(get_db)):
    return compliance_service.list_allowlist(db)

@router.post("/allowlist")
def add_allowlist(payload: dict, db: Session = Depends(get_db)):
    return compliance_service.add_allowlist(payload, db)

@router.delete("/allowlist/{item_id}")
def delete_allowlist(item_id: int, db: Session = Depends(get_db)):
    return compliance_service.delete_allowlist(item_id, db)

@router.get("/account-stats")
def get_account_stats(days: int = 30, db: Session = Depends(get_db)):
    return compliance_service.get_account_stats(days, db)

