from datetime import datetime
from typing import Optional, Dict, Any, Union

from pydantic import BaseModel, Field

class CanonicalLogEvent(BaseModel):
    """
    Unified representation of a log event across all sources (System or Domain).
    This serves as the core schema for LogService v2 MVP.
    """
    timestamp: Union[str, datetime]
    source: str
    source_type: str = Field(description='"system" or "domain"')
    level: Optional[str] = None
    event_type: Optional[str] = None
    job_id: Optional[int] = None
    actor: Optional[str] = None
    message: str
    metadata: Union[str, Dict[str, Any], None] = None
