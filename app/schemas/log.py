from datetime import datetime
from typing import Optional, Dict, Any, Union

from pydantic import BaseModel, Field

class CanonicalLogEvent(BaseModel):
    """
    Unified representation of a log event across all sources (System or Domain).
    This serves as the core schema for LogService v2 MVP.
    """
    timestamp: Union[int, float, str, datetime]
    source: str
    source_type: str = Field(description='"system" or "domain"')
    level: Optional[str] = None
    event_type: Optional[str] = None
    job_id: Optional[int] = None
    actor: Optional[str] = None
    message: str
    hint: Optional[str] = None
    message_raw: Optional[str] = None
    metadata: Union[str, Dict[str, Any], None] = None
    # Unix seconds for reliable client formatting (avoid parseInt on ISO strings).
    ts_unix: Optional[int] = None
