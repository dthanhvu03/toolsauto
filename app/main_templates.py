from fastapi.templating import Jinja2Templates
from zoneinfo import ZoneInfo
from app.config import TIMEZONE
import time
import os

from app.services.video_protector import EVIDENCE_FILE
import json
import logging

logger = logging.getLogger(__name__)

# Shared templates instance for routers
templates = Jinja2Templates(directory="app/templates")

def format_time(ts):
    if not ts: return "-"
    from datetime import datetime, timezone
    dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(TIMEZONE)).strftime('%H:%M:%S %d/%m/%Y')

def date_only(ts):
    if not ts: return ""
    from datetime import datetime, timezone
    dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(TIMEZONE)).strftime('%Y-%m-%d')

def time_only(ts):
    if not ts: return ""
    from datetime import datetime, timezone
    dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt_utc.astimezone(ZoneInfo(TIMEZONE)).strftime('%H:%M')

templates.env.filters["format_time"] = format_time
templates.env.filters["date_only"] = date_only
templates.env.filters["time_only"] = time_only
templates.env.globals["now"] = time.time  

_evidence_cache = {"mtime": 0, "data": {}}

def get_job_evidence(job):
    if not EVIDENCE_FILE.exists():
        return None
        
    mtime = EVIDENCE_FILE.stat().st_mtime
    if mtime > _evidence_cache["mtime"]:
        try:
            with open(EVIDENCE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _evidence_cache["data"] = {entry.get("filename"): entry for entry in data}
                _evidence_cache["mtime"] = mtime
        except Exception as e:
            logger.error(f"Failed to read evidence cache: {e}")
            return None
            
    path = job.processed_media_path or job.media_path
    if not path:
        return None
        
    filename = os.path.basename(path)
    return _evidence_cache["data"].get(filename)

templates.env.globals["get_job_evidence"] = get_job_evidence
