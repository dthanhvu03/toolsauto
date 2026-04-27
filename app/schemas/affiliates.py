"""
Affiliate-related Pydantic schemas.
Moved from app/routers/affiliates.py per PLAN-027 Phase 1 (Schema Centralization).
"""
from typing import List, Optional

from pydantic import BaseModel


class BatchItem(BaseModel):
    keyword: str
    affiliate_url: str
    comment: Optional[str] = None
    commission_rate: Optional[float] = None


class BatchImportRequest(BaseModel):
    items: List[BatchItem]


class AIGenerateRequest(BaseModel):
    product_name: str
    category: str
    price: str
    commission_rate: float


class ComplianceTextRequest(BaseModel):
    text: str
