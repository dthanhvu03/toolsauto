import logging
from typing import Any, Dict, List, Tuple
from sqlalchemy.orm import Session
from app.database.models import ViralMaterial, Account
from app.services.worker import WorkerService
from app.services.viral_scan import run_tiktok_competitor_scan, get_default_min_views

logger = logging.getLogger(__name__)

class ViralService:
    VIRAL_TABLE_LIMIT = 500

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
        
        return {
            "materials": materials,
            "total_count": total_count,
            "accounts": accounts,
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
