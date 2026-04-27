import math
import logging
from typing import Optional, List, Tuple, Dict, Literal
from app.schemas.log import CanonicalLogEvent
from app.services.log_normalizer import LogNormalizer
from sqlalchemy.orm import Session
from sqlalchemy import text

logger = logging.getLogger(__name__)

# ─── Source Registry ─────────────────────────────────────────────────────────
# Maps source_name → SQL subquery that returns the canonical 9-column shape:
#   timestamp, source, level, event_type, job_id, actor, message, metadata, _id
#
# Add new sources at startup by calling LogQueryService.register_source().
# Built-in sources are pre-populated below.

_SOURCE_REGISTRY: Dict[str, str] = {
    "job_events": """
        SELECT
            ts            AS timestamp,
            'job_events'  AS source,
            level         AS level,
            'job_event'   AS event_type,
            job_id        AS job_id,
            CAST(NULL AS TEXT) AS actor,
            message       AS message,
            CAST(meta_json AS TEXT) AS metadata,
            id            AS _id
        FROM job_events
    """,
    "violation_log": """
        SELECT
            checked_at                                                    AS timestamp,
            'violation_log'                                               AS source,
            action_taken                                                  AS level,
            'compliance_violation'                                        AS event_type,
            job_id                                                        AS job_id,
            CAST(NULL AS TEXT)                                            AS actor,
            'Compliance violation: ' || COALESCE(content_type, 'unknown') AS message,
            CAST(violations_found AS TEXT)                              AS metadata,
            id                                                            AS _id
        FROM violation_log
    """,
    "audit_logs": """
        SELECT
            created_at                 AS timestamp,
            'audit_logs'               AS source,
            'INFO'                     AS level,
            action                     AS event_type,
            NULL                       AS job_id,
            CAST(user_id AS TEXT)      AS actor,
            'Audit action: ' || action AS message,
            CAST(details AS TEXT)       AS metadata,
            id                         AS _id
        FROM audit_logs
    """,
    "runtime_settings_audit": """
        SELECT
            ts                                                         AS timestamp,
            'runtime_settings_audit'                                   AS source,
            'INFO'                                                     AS level,
            action                                                     AS event_type,
            NULL                                                       AS job_id,
            CAST(updated_by AS TEXT)                                  AS actor,
            action || ' on key ' || key                                AS message,
            ('old_value=' || COALESCE(old_value, '') || '; new_value=' || COALESCE(new_value, '')) AS metadata,
            id                                                         AS _id
        FROM runtime_settings_audit
    """,
}


def _normalize_category(value: Optional[str]) -> Literal["user", "tech", "all"]:
    if not value:
        return "all"
    normalized = value.strip().lower()
    if normalized in {"user", "tech", "all"}:
        return normalized
    return "all"


def _tech_heuristic_sql() -> str:
    return (
        "("
        "LOWER(COALESCE(message, '')) LIKE '%python traceback%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%psycopg2%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%sqlalchemy%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%playwright%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%pydantic%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%typeerror%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%valueerror%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%attributeerror%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%connection refused%' OR "
        "LOWER(COALESCE(message, '')) LIKE '%timeout%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%python traceback%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%psycopg2%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%sqlalchemy%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%playwright%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%pydantic%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%typeerror%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%valueerror%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%attributeerror%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%connection refused%' OR "
        "LOWER(COALESCE(metadata, '')) LIKE '%timeout%'"
        ")"
    )

class LogQueryService:
    @staticmethod
    def register_source(name: str, subquery_sql: str) -> None:
        """
        Register a new log source at runtime.

        Args:
            name:          Unique source identifier (e.g. "telegram_events")
            subquery_sql:  SQL SELECT returning columns in canonical order:
                           timestamp, source, level, event_type, job_id,
                           actor, message, metadata, _id

        Example:
            LogQueryService.register_source("telegram_events", '''
                SELECT ts, 'telegram_events', level, event_type,
                       NULL, NULL, message, NULL, id
                FROM telegram_events
            ''')
        """
        if name in _SOURCE_REGISTRY:
            logger.warning("Overwriting existing log source: %s", name)
        _SOURCE_REGISTRY[name] = subquery_sql
        logger.info("Registered log source: %s", name)

    @staticmethod
    def list_sources() -> List[str]:
        """Return names of all registered log sources."""
        return list(_SOURCE_REGISTRY.keys())
    @staticmethod
    def get_domain_events(
        db: Session,
        source: Optional[str] = None,
        level: Optional[str] = None,
        job_id: Optional[int] = None,
        q: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
        category: str = "all",
    ) -> Tuple[List[CanonicalLogEvent], int, int]:
        per_page = max(10, min(200, int(per_page)))
        page = max(1, int(page))
        category = _normalize_category(category)

        # Validate source against registry — prevents unexpected/injected values
        if source and source not in _SOURCE_REGISTRY:
            logger.warning("Invalid source filter requested: %s", source)
            return [], 0, 1

        # Select subqueries from registry
        queries = [
            sql for name, sql in _SOURCE_REGISTRY.items()
            if not source or name == source
        ]

        if not queries:
            return [], 0, 1

        union_query = " UNION ALL ".join(queries)

        # Outer query to apply filters globally over the UNION
        params: Dict[str, object] = {}
        outer_where = []

        tech_heuristic = _tech_heuristic_sql()
        if category == "user":
            outer_where.append(
                "((UPPER(COALESCE(level, '')) = 'INFO' "
                "OR source IN ('audit_logs', 'violation_log', 'runtime_settings_audit')) "
                f"AND NOT {tech_heuristic})"
            )
        elif category == "tech":
            outer_where.append(
                "(UPPER(COALESCE(level, '')) IN ('ERROR', 'WARNING', 'WARN', 'FATAL', 'CRITICAL') "
                f"OR {tech_heuristic})"
            )

        if level:
            outer_where.append("level LIKE :level")
            params["level"] = f"%{level}%"
            
        if job_id is not None:
            # Note: audit logs have NULL job_id, they will be filtered out organically here
            outer_where.append("job_id = :job_id")
            params["job_id"] = job_id
            
        if q:
            q_search = f"%{q}%"
            outer_where.append("(message LIKE :q OR event_type LIKE :q OR metadata LIKE :q)")
            params["q"] = q_search
            
        where_sql = ""
        if outer_where:
            where_sql = " WHERE " + " AND ".join(outer_where)
            
        count_sql = f"SELECT COUNT(*) FROM ({union_query}) as combined {where_sql}"
        total_rows = db.execute(text(count_sql), params).scalar() or 0
        total_pages = max(1, math.ceil(total_rows / per_page))
        page = min(page, total_pages)
        
        data_sql = f"""
            SELECT * FROM ({union_query}) as combined
            {where_sql}
            ORDER BY timestamp DESC, _id DESC
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = per_page
        params["offset"] = (page - 1) * per_page
        
        rows = db.execute(text(data_sql), params).fetchall()
        
        # Format response using Event Normalizer
        results = []
        for r in rows:
            raw_dict = {
                "timestamp": r[0],
                "source": r[1],
                "level": r[2],
                "event_type": r[3],
                "job_id": r[4],
                "actor": r[5],
                "message": r[6],
                "metadata": r[7],
            }
            results.append(LogNormalizer.normalize_domain_row(raw_dict, category=category))
            
        return results, total_rows, total_pages
