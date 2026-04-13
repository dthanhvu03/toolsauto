from typing import Optional, Tuple, List, Dict
from sqlalchemy.orm import Session
from fastapi.responses import PlainTextResponse, StreamingResponse

from app.services.log_query_service import LogQueryService
from app.services.log_service import LogService
from app.schemas.log import CanonicalLogEvent

class LogQueryFacade:
    """
    LogService v2 MVP - Facade Pattern.
    This acts as the single entry point for the UI/Router to fetch logs.
    It delegates to SystemLogProvider (LogService) or DomainEventProvider (LogQueryService),
    keeping the router lean and preparing the architecture for multiple backend implementations.
    """

    @staticmethod
    def get_system_tail(proc: str, kind: str, lines: int) -> PlainTextResponse:
        """
        Retrieves the tail of PM2/system logs.
        """
        return LogService.plain_tail_response(proc=proc, kind=kind, lines=lines)

    @staticmethod
    def stream_system_logs(proc: str, kind: str, level: str, q: str) -> StreamingResponse:
        """
        Establishes an SSE stream for real-time PM2 logs.
        """
        return LogService.sse_log_stream(proc=proc, kind=kind, level=level, q=q)

    @staticmethod
    def query_domain_events(
        db: Session,
        source: Optional[str] = None,
        level: Optional[str] = None,
        job_id: Optional[int] = None,
        q: Optional[str] = None,
        page: int = 1,
        per_page: int = 50
    ) -> Tuple[List[CanonicalLogEvent], int, int]:
        """
        Queries structured domain events from the database.
        Returns a tuple of (Normalized Canonical Events, Total rows, Total pages).
        """
        return LogQueryService.get_domain_events(
            db=db,
            source=source,
            level=level,
            job_id=job_id,
            q=q,
            page=page,
            per_page=per_page
        )

    @staticmethod
    def list_system_sources() -> List[str]:
        """
        Returns a list of all identified PM2 system log processes.
        """
        return ["ALL", *list(LogService.PM2_LOG_MAP.keys())]
