import json
import logging
from datetime import datetime, timezone
import app.config as config
from app.constants import JobType
try:
    import zoneinfo
    tz = zoneinfo.ZoneInfo(config.TIMEZONE)
except Exception:
    import datetime as dt_fallback
    tz = dt_fallback.timezone.utc

logger = logging.getLogger("n8n.tracer")

def _now_iso() -> str:
    return datetime.now(tz).isoformat()

def _get_canonical_nodes(platform: str, job_type: str, workflow_steps: list[str]) -> list[str]:
    """Generates a cohesive ordered list of nodes based on job type and active steps."""
    nodes = []
    
    # 1. Base initialization phase (always happens)
    nodes.append("login")
    nodes.append("switch_profile")
    
    # 2. Pre-publish actions from workflow
    if "pre_scan" in workflow_steps:
        nodes.append("pre_scan")
    if "feed_browse" in workflow_steps:
        nodes.append("feed_browse")
        
    # 3. Publish phase
    if job_type.upper() == JobType.POST:
        nodes.append("post_content")
    else:
        nodes.append("type_comment")
        nodes.append("submit_comment")
        
    # 4. Verification phase
    nodes.append("post_verify")
    return nodes

def _update_state_in_db(job_id: int, transform_fn) -> None:
    """Helper to cleanly and safely open a short transaction to modify the current tracer state."""
    from app.database.core import SessionLocal
    from app.database.models import SystemState
    try:
        with SessionLocal() as db:
            state = db.query(SystemState).filter(SystemState.id == 1).first()
            if not state:
                return
            
            # Verify we are actively tracing this job
            if state.engagement_status != 'JOB_EXECUTION' or not state.engagement_detail:
                return
            
            data = json.loads(state.engagement_detail)
            if data.get("job_id") != job_id:
                return  # Safety guard: Mismatched job, do not overwrite trace
                
            # Predict changes
            new_data = transform_fn(data)
            if new_data:
                state.engagement_detail = json.dumps(new_data, ensure_ascii=False)
                db.commit()
    except Exception as e:
        logger.error(f"[Tracer] DB update failed for job {job_id}: {e}")

def start_job_trace(job_id: int, platform: str, job_type: str, workflow_steps: list[str]) -> None:
    """Initialize a brand new trace session for a job."""
    from app.database.core import SessionLocal
    from app.database.models import SystemState
    
    node_names = _get_canonical_nodes(platform, job_type, workflow_steps)
    nodes_payload = [{"name": n, "state": "pending"} for n in node_names]
    
    payload = {
        "job_id": job_id,
        "platform": platform,
        "job_type": job_type,
        "status": "running",
        "nodes": nodes_payload,
        "active_node": None,
        "active_index": -1,
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
        "error": None
    }
    
    try:
        with SessionLocal() as db:
            state = db.query(SystemState).filter(SystemState.id == 1).first()
            if state:
                state.engagement_status = 'JOB_EXECUTION'
                state.engagement_detail = json.dumps(payload, ensure_ascii=False)
                db.commit()
    except Exception as e:
        logger.error(f"[Tracer] Failed to start trace for job {job_id}: {e}")

def update_active_node(job_id: int, node_name: str) -> None:
    """Moves execution trace to the next node immediately."""
    def transform(data):
        # 1. Mark all previous nodes as done, assuming linear execution
        found = False
        new_idx = -1
        
        for i, n in enumerate(data["nodes"]):
            if n["name"] == node_name:
                found = True
                new_idx = i
                break
                
        if not found:
            # If the adapter reports an unregistered node, append it dynamically
            data["nodes"].append({"name": node_name, "state": "active"})
            new_idx = len(data["nodes"]) - 1
            
        # Update states sequentially
        for i, n in enumerate(data["nodes"]):
            if i < new_idx:
                data["nodes"][i]["state"] = "done"
            elif i == new_idx:
                data["nodes"][i]["state"] = "active"
            else:
                data["nodes"][i]["state"] = "pending"
                
        data["active_node"] = node_name
        data["active_index"] = new_idx
        data["updated_at"] = _now_iso()
        return data

    _update_state_in_db(job_id, transform)

def fail_job_trace(job_id: int, node_name: str, error_message: str) -> None:
    """Records a failure state precisely at the breaking node."""
    def transform(data):
        # Default fallback if active node didn't match perfectly
        target_node = node_name or data.get("active_node")
        
        for n in data.get("nodes", []):
            if n["state"] == "active" or n["name"] == target_node:
                n["state"] = "failed"
                
        data["status"] = "failed"
        data["error"] = error_message
        data["updated_at"] = _now_iso()
        return data
        
    _update_state_in_db(job_id, transform)

def finish_job_trace(job_id: int, status: str = "completed", error: str = None) -> None:
    """Marks trace as fully finished. If completed, marks the last node as done."""
    def transform(data):
        data["status"] = status
        data["error"] = error
        data["updated_at"] = _now_iso()
        
        if status == "completed":
            for n in data.get("nodes", []):
                n["state"] = "done"
        elif status == "failed":
            # Just mark currently active as failed if not done via fail_job_trace
            for n in data.get("nodes", []):
                if n["state"] == "active":
                    n["state"] = "failed"
        return data

    _update_state_in_db(job_id, transform)

def clear_trace() -> None:
    """Completely purges the UI tracer. Call only when worker is truly idle."""
    from app.database.core import SessionLocal
    from app.database.models import SystemState
    try:
        with SessionLocal() as db:
            state = db.query(SystemState).filter(SystemState.id == 1).first()
            if state and state.engagement_status == 'JOB_EXECUTION':
                state.engagement_status = None
                state.engagement_detail = None
                db.commit()
    except Exception as e:
        logger.error(f"[Tracer] DB flush failed: {e}")
