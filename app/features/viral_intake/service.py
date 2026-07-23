import logging
import os
from glob import glob
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

import app.config as config
from app.core.database.models import Account, Job, ViralMaterial
from app.core.queue.worker import WorkerService
from app.features.viral_intake.scan import get_default_min_views, run_tiktok_competitor_scan

logger = logging.getLogger(__name__)


class ViralService:
    VIRAL_TABLE_LIMIT = 500

    @staticmethod
    def find_reup_path(material_id: int, platform: str | None = None) -> Optional[str]:
        """Locate anti-dupe output viral_{id}*_reup.mp4 under REUP_DIR."""
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
        reup_by_id: Dict[int, bool] = {}
        for mat in materials:
            if mat.status == "NEW":
                continue
            path = ViralService.find_reup_path(mat.id, mat.platform)
            if path:
                reup_by_id[mat.id] = True

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
