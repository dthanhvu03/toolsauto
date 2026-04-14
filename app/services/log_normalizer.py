from typing import Any, Dict

from app.schemas.log import CanonicalLogEvent

class LogNormalizer:
    """
    Responsible for converting raw logs from various sources (files, databases)
    into a unified CanonicalLogEvent.
    """

    @staticmethod
    def normalize_domain_row(row_dict: Dict[str, Any]) -> CanonicalLogEvent:
        """
        Takes a raw dictionary returned from LogQueryService and converts it.
        """
        return CanonicalLogEvent(
            timestamp=row_dict.get("timestamp"),
            source=row_dict.get("source", "unknown"),
            source_type="domain",
            level=row_dict.get("level"),
            event_type=row_dict.get("event_type"),
            job_id=row_dict.get("job_id"),
            actor=row_dict.get("actor"),
            message=row_dict.get("message", ""),
            metadata=row_dict.get("metadata")
        )
