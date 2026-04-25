from sqlalchemy.orm import Session
from app.database.models import SystemState, now_ts
from typing import Optional
from app.constants import JobStatus



class WorkerService:
    @staticmethod
    def get_or_create_state(db: Session) -> SystemState:
        """Gets the singleton system state row (id=1). Creates if not exists."""
        state = db.query(SystemState).filter(SystemState.id == 1).first()
        if not state:
            state = SystemState(
                id=1,
                worker_status=JobStatus.RUNNING,
                safe_mode=False
            )
            db.add(state)
            try:
                db.commit()
                db.refresh(state)
            except Exception:
                db.rollback()
                state = db.query(SystemState).filter(SystemState.id == 1).first()
        return state

    @staticmethod
    def update_heartbeat(db: Session, current_job_id: Optional[int]):
        """Cheap update for worker heartbeat with silent retries for locking."""
        import sqlalchemy.exc
        import time as _time
        for attempt in range(3):
            try:
                db.query(SystemState).filter(SystemState.id == 1).update(
                    {
                        "heartbeat_at": int(_time.time()),
                        "current_job_id": current_job_id,
                        "updated_at": int(_time.time())
                    }
                )
                db.commit()
                break
            except sqlalchemy.exc.OperationalError:
                db.rollback()
                if attempt < 2:
                    _time.sleep(0.5 * (attempt + 1))
                continue
            except Exception:
                db.rollback()
                break

    @staticmethod
    def set_status(db: Session, status: str) -> SystemState:
        """Sets the worker status (RUNNING / PAUSED)."""
        state = WorkerService.get_or_create_state(db)
        state.worker_status = status
        db.commit()
        db.refresh(state)
        return state

    @staticmethod
    def toggle_safe_mode(db: Session) -> SystemState:
        """Toggles the safe mode boolean."""
        state = WorkerService.get_or_create_state(db)
        state.safe_mode = not state.safe_mode
        db.commit()
        db.refresh(state)
        return state

    @staticmethod
    def set_command(db: Session, command: str) -> SystemState:
        """Sets a pending command for the worker to act upon (e.g. REQUEST_EXIT)."""
        state = WorkerService.get_or_create_state(db)
        state.pending_command = command
        db.commit()
        db.refresh(state)
        return state

    @staticmethod
    def clear_command(db: Session):
        """Clears the pending command."""
        db.query(SystemState).filter(SystemState.id == 1).update(
            {"pending_command": None, "updated_at": now_ts()}
        )
        db.commit()
