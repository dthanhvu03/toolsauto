from dataclasses import dataclass
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
from app.database.models import Job

@dataclass
class PublishResult:
    """Standardized result container for all adapters."""
    ok: bool
    is_fatal: bool = False
    error_code: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    artifacts: Optional[Dict[str, str]] = None
    external_post_id: Optional[str] = None


class AdapterInterface(ABC):
    """Base interface that all platform adapters must implement."""
    
    @abstractmethod
    def open_session(self, profile_path: str) -> bool:
        """Initialize browser/session for the account using its isolated profile directory."""
        pass
        
    @abstractmethod
    def publish(self, job: Job) -> PublishResult:
        """Execute the automation for this job."""
        pass
        
    @abstractmethod
    def check_published_state(self, job: Job) -> PublishResult:
        """
        Verify if the post exists on the platform timeline/feed. 
        Returns an ok=True PublishResult if the footprint is found.
        """
        pass
        
    @abstractmethod
    def close_session(self):
        """Mandatory cleanup. Must close browsers/connections safely."""
        pass
