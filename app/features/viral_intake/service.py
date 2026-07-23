import logging
import os
import re
from glob import glob
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

import app.config as config
from app.core.database.models import Account, Job, ViralMaterial
from app.core.queue.worker import WorkerService
from app.features.viral_intake.scan import get_default_min_views, run_tiktok_competitor_scan

logger = logging.getLogger(__name__)

_REUP_ID_RE = re.compile(r"viral_(\d+)_", re.IGNORECASE)


class ViralService:
    VIRAL_TABLE_LIMIT = 500

    @staticmethod
    def find_reup_path(material_id: int, platform: str | None = None) -> Optional[str]:
        """Locate anti-dupe output viral_{id}*_reup.mp4 under REUP_DIR (single-item)."""
        reup_base = str(config.REUP_DIR)
        plat = platform or "tiktok"
        patterns = [
            os.path.join(reup_base, plat, f"viral_{material_id}_*_reup.mp4"),
            os.path.join(reup_base, plat, f"viral_{material_id}_reup.mp4"),
            os.path.join(reup_base, "**", f"viral_{material_id}_*_reup.mp4"),
        ]
        hits: list[str] = []
        for pat in patterns:
            hits.extend(glob(pat, recursive=True))
        hits = [h for h in hits if os.path.isfile(h) and os.path.getsize(h) > 0]
        if hits:
            hits.sort(key=os.path.getmtime, reverse=True)
            return hits[0]

        try:
            from app.core.database.core import SessionLocal
            from app.core.storage_paths import resolve_media_path

            with SessionLocal() as db:
                needle = f"viral_{material_id}_"
                job = (
                    db.query(Job)
                    .filter(Job.media_path.isnot(None), Job.media_path.contains(needle))
                    .order_by(Job.id.desc())
                    .first()
                )
                if job and job.media_path and "_reup" in (job.media_path or "").replace("\\", "/"):
                    resolved = resolve_media_path(job.media_path)
                    if resolved and os.path.isfile(resolved):
                        return resolved
        except Exception as e:
            logger.debug("[VIRAL] reup job lookup failed: %s", e)
        return None

    @staticmethod
    def _index_reup_ids_from_disk() -> Set[int]:
        """One-pass filesystem index: material ids that have a non-empty _reup.mp4."""
        found: Set[int] = set()
        reup_base = str(config.REUP_DIR)
        if not os.path.isdir(reup_base):
            return found
        for root, _dirs, files in os.walk(reup_base):
            for name in files:
                if "_reup" not in name.lower() or not name.lower().endswith(".mp4"):
                    continue
                m = _REUP_ID_RE.search(name)
                if not m:
                    continue
                path = os.path.join(root, name)
                try:
                    if os.path.getsize(path) > 0:
                        found.add(int(m.group(1)))
                except OSError:
                    continue
        return found

    @staticmethod
    def _index_reup_ids_from_jobs(db: Session, candidate_ids: Set[int]) -> Set[int]:
        """Batch Job lookup for remaining ids (media_path contains viral_{id}_ and _reup)."""
        if not candidate_ids:
            return set()
        from app.core.storage_paths import resolve_media_path

        found: Set[int] = set()
        # Limit scan: only jobs whose path mentions viral_ and _reup
        rows = (
            db.query(Job.media_path)
            .filter(
                Job.media_path.isnot(None),
                Job.media_path.contains("viral_"),
                Job.media_path.contains("_reup"),
            )
            .order_by(Job.id.desc())
            .limit(2000)
            .all()
        )
        for (media_path,) in rows:
            if not media_path:
                continue
            m = _REUP_ID_RE.search(os.path.basename(media_path.replace("\\", "/")))
            if not m:
                m = _REUP_ID_RE.search(media_path.replace("\\", "/"))
            if not m:
                continue
            mid = int(m.group(1))
            if mid not in candidate_ids or mid in found:
                continue
            resolved = resolve_media_path(media_path)
            if resolved and os.path.isfile(resolved) and os.path.getsize(resolved) > 0:
                found.add(mid)
        return found

    @staticmethod
    def batch_reup_by_id(db: Session, materials: List[ViralMaterial]) -> Dict[int, bool]:
        """Build reup presence map without per-row glob/SessionLocal."""
        candidates = {m.id for m in materials if m.status != "NEW"}
        if not candidates:
            return {}
        on_disk = ViralService._index_reup_ids_from_disk()
        present = candidates & on_disk
        missing = candidates - present
        if missing:
            present |= ViralService._index_reup_ids_from_jobs(db, missing)
        return {mid: True for mid in present}

    @staticmethod
    def get_viral_materials(db: Session, limit: int = 500) -> List[ViralMaterial]:
        return (
            db.query(ViralMaterial)
            .order_by(ViralMaterial.views.desc())
            .limit(limit)
            .all()
        )

    @staticmethod
    def get_viral_table_data(db: Session) -> Dict[str, Any]:
        materials = ViralService.get_viral_materials(db, ViralService.VIRAL_TABLE_LIMIT)
        total_count = db.query(ViralMaterial).count()
        accounts = {acc.id: acc.name for acc in db.query(Account).all()}
        reup_by_id = ViralService.batch_reup_by_id(db, materials)

        return {
            "materials": materials,
            "total_count": total_count,
            "accounts": accounts,
            "reup_by_id": reup_by_id,
        }

    @staticmethod
    def force_scan(db: Session) -> Tuple[int, int, str]:
        try:
            total_found, num_channels = run_tiktok_competitor_scan(db)
            if num_channels == 0:
                msg = "Không có kênh TikTok đối thủ nào trong cấu hình account."
            elif total_found > 0:
                msg = f"✅ Đã quét thủ công: {total_found} video mới từ {num_channels} kênh."
            else:
                default_min = get_default_min_views(db)
                msg = f"Đã quét {num_channels} kênh. 0 video đạt ngưỡng {default_min:,} views."
            return total_found, num_channels, msg
        except Exception as e:
            msg = f"❌ Lỗi quét: {str(e)[:120]}"
            return 0, 0, msg

    @staticmethod
    def save_settings(db: Session, viral_min_views: int, viral_max_videos_per_channel: int) -> Dict[str, int]:
        vmin = max(500, min(10_000_000, int(viral_min_views)))
        vmax_raw = int(viral_max_videos_per_channel) if viral_max_videos_per_channel is not None else 50
        vmax = max(0, min(500, vmax_raw))

        state = WorkerService.get_or_create_state(db)
        state.viral_min_views = vmin
        state.viral_max_videos_per_channel = vmax
        db.commit()
        return {"min_views": vmin, "max_videos": vmax}

    @staticmethod
    def delete_material(db: Session, material_id: int):
        material = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
        if material:
            db.delete(material)
            db.commit()
