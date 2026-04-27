"""
Compliance-related Pydantic schemas.
Moved from app/routers/compliance.py per PLAN-027 Phase 1 (Schema Centralization).
"""
from typing import Optional

from pydantic import BaseModel


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
