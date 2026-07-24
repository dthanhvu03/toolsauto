"""Content-hash helpers for cross-account media publish guard (PLAN-041)."""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from app.constants import JobStatus
from app.core.database.models import Job

# DONE forever + in-flight; FAILED/CANCELLED do not block recreate.
BLOCKING_JOB_STATUSES: tuple[str, ...] = (
    JobStatus.PENDING,
    JobStatus.RUNNING,
    JobStatus.DONE,
    JobStatus.DRAFT,
    JobStatus.AI_PROCESSING,
    JobStatus.AWAITING_STYLE,
)

_CHUNK = 1024 * 1024


def sha256_file(path: str | Path) -> str | None:
    """Return hex sha256 of file bytes, or None if missing/unreadable."""
    file_path = Path(path)
    if not file_path.is_file():
        return None
    digest = hashlib.sha256()
    try:
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(_CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def find_blocking_job_by_content_hash(
    db: Session,
    *,
    platform: str,
    content_hash: str,
    exclude_job_id: int | None = None,
) -> Job | None:
    if not content_hash or not platform:
        return None
    q = db.query(Job).filter(
        Job.platform == platform,
        Job.content_hash == content_hash,
        Job.status.in_(BLOCKING_JOB_STATUSES),
    )
    if exclude_job_id is not None:
        q = q.filter(Job.id != exclude_job_id)
    return q.order_by(Job.id.asc()).first()


def find_blocking_job_by_viral_material(
    db: Session,
    *,
    viral_material_id: int,
    exclude_job_id: int | None = None,
) -> Job | None:
    if not viral_material_id:
        return None
    q = db.query(Job).filter(
        Job.viral_material_id == viral_material_id,
        Job.status.in_(BLOCKING_JOB_STATUSES),
    )
    if exclude_job_id is not None:
        q = q.filter(Job.id != exclude_job_id)
    return q.order_by(Job.id.asc()).first()


def assert_media_not_blocked(
    db: Session,
    *,
    platform: str,
    content_hash: str | None = None,
    viral_material_id: int | None = None,
    exclude_job_id: int | None = None,
) -> None:
    """Raise ValueError if an active/DONE job already owns this media."""
    if viral_material_id:
        existing = find_blocking_job_by_viral_material(
            db,
            viral_material_id=viral_material_id,
            exclude_job_id=exclude_job_id,
        )
        if existing:
            raise ValueError(
                f"Cross-account guard: viral_material_id={viral_material_id} already has "
                f"job #{existing.id} (account={existing.account_id}, status={existing.status})."
            )
    if content_hash:
        existing = find_blocking_job_by_content_hash(
            db,
            platform=platform,
            content_hash=content_hash,
            exclude_job_id=exclude_job_id,
        )
        if existing:
            raise ValueError(
                f"Cross-account guard: same media hash already used by job #{existing.id} "
                f"(account={existing.account_id}, platform={existing.platform}, "
                f"status={existing.status})."
            )


def blocking_status_sql_list(statuses: Iterable[str] = BLOCKING_JOB_STATUSES) -> str:
    return ", ".join(f"'{s}'" for s in statuses)
