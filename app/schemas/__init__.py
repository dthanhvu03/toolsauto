"""
Centralized Pydantic schemas for ToolsAuto.
All request/response models should live here, organized by domain.
"""
from app.schemas.log import CanonicalLogEvent
from app.schemas.compliance import KeywordCreateBody, KeywordUpdateBody, TestCheckBody
from app.schemas.affiliates import (
    BatchItem,
    BatchImportRequest,
    AIGenerateRequest,
    ComplianceTextRequest,
)

__all__ = [
    # Log
    "CanonicalLogEvent",
    # Compliance
    "KeywordCreateBody",
    "KeywordUpdateBody",
    "TestCheckBody",
    # Affiliates
    "BatchItem",
    "BatchImportRequest",
    "AIGenerateRequest",
    "ComplianceTextRequest",
]
