import asyncio
import json
import logging
import time
from sqlalchemy import create_engine, text
from app.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Dedicated engine for audit to ensure it's independent of the main app session
# Using a separate connection pool/engine for non-blocking writes
audit_engine = create_engine(DATABASE_URL)

async def _write_audit_log(user_id: int, action: str, ip_address: str, details: dict):
    """
    Internal async worker to write the audit log.
    """
    try:
        with audit_engine.connect() as conn:
            query = text("""
                INSERT INTO audit_logs (user_id, action, details, ip_address, created_at)
                VALUES (:user_id, :action, :details, :ip, :ts)
            """)
            conn.execute(query, {
                "user_id": user_id,
                "action": action,
                "details": json.dumps(details),
                "ip": ip_address,
                "ts": int(time.time())
            })
            conn.commit()
    except Exception as e:
        logger.error(f"[AUDIT_LOG_ERROR] Could not write audit log: {e}")

def audit_log(user_id: int, action: str, ip_address: str, **details):
    """
    Public non-blocking interface to log DB explorer activities.
    """
    # Fire and forget
    asyncio.create_task(_write_audit_log(user_id, action, ip_address, details))
