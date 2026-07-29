import logging
import os
import re
import shutil
import subprocess
from glob import glob
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import func
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
    def reup_thumb_path(material_id: int) -> str:
        """Cached jpeg path for table thumbnail (one frame from _reup)."""
        thumb_dir = str(config.THUMB_DIR)
        os.makedirs(thumb_dir, exist_ok=True)
        return os.path.join(thumb_dir, f"viral_{material_id}_reup.jpg")

    @staticmethod
    def ensure_reup_thumbnail(
        material_id: int,
        platform: str | None = None,
        video_path: str | None = None,
    ) -> Optional[str]:
        """Extract 1 frame (~1s) from reup mp4 → small jpeg. Cache if newer than video."""
        out = ViralService.reup_thumb_path(material_id)
        src = video_path or ViralService.find_reup_path(material_id, platform)
        if not src or not os.path.isfile(src):
            return out if os.path.isfile(out) and os.path.getsize(out) > 0 else None

        try:
            if os.path.isfile(out) and os.path.getsize(out) > 0:
                if os.path.getmtime(out) >= os.path.getmtime(src):
                    return out
        except OSError:
            pass

        ffmpeg = ViralService.resolve_ffmpeg()
        if not ffmpeg:
            logger.warning("[VIRAL] ensure_reup_thumbnail: ffmpeg missing for #%s", material_id)
            return None

        tmp = out + ".tmp.jpg"
        try:
            cmd = [
                ffmpeg,
                "-y",
                "-ss",
                "1",
                "-i",
                src,
                "-frames:v",
                "1",
                "-vf",
                "scale=160:-2",
                "-q:v",
                "5",
                tmp,
            ]
            subprocess.run(cmd, capture_output=True, timeout=20, check=False)
            if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
                os.replace(tmp, out)
                return out
        except Exception as e:
            logger.debug("[VIRAL] thumb extract failed #%s: %s", material_id, e)
        finally:
            try:
                if os.path.isfile(tmp):
                    os.remove(tmp)
            except OSError:
                pass
        return out if os.path.isfile(out) and os.path.getsize(out) > 0 else None

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
    def batch_jobs_by_material(
        db: Session, material_ids: Set[int]
    ) -> Dict[int, Dict[str, Any]]:
        """Latest job snapshot per viral_material_id (id, status, affiliate flag)."""
        if not material_ids:
            return {}
        rows = (
            db.query(Job)
            .filter(Job.viral_material_id.in_(material_ids))
            .order_by(Job.id.desc())
            .all()
        )
        out: Dict[int, Dict[str, Any]] = {}
        for job in rows:
            mid = job.viral_material_id
            if mid is None or mid in out:
                continue
            out[mid] = {
                "job_id": job.id,
                "job_status": job.status,
                "has_affiliate": bool(job.affiliate_url or job.auto_comment_text),
            }
        return out

    @staticmethod
    def pipeline_banner(db: Session) -> Dict[str, Any]:
        """UI hint when NEW exists but no viral-linked jobs yet (local Web-only)."""
        from app.constants import ViralStatus

        counts = dict(
            db.query(ViralMaterial.status, func.count(ViralMaterial.id))
            .group_by(ViralMaterial.status)
            .all()
        )
        new_count = int(counts.get(ViralStatus.NEW, 0) or 0)
        processing_count = int(counts.get(ViralStatus.PROCESSING, 0) or 0)
        failed_count = int(counts.get(ViralStatus.FAILED, 0) or 0)
        drafted_count = int(counts.get(ViralStatus.DRAFTED, 0) or 0)
        jobs_viral = (
            db.query(Job)
            .filter(Job.viral_material_id.isnot(None))
            .count()
        )
        return {
            "status_counts": {
                "NEW": new_count,
                "PROCESSING": processing_count,
                "DRAFTED": drafted_count,
                "FAILED": failed_count,
            },
            "new_count": new_count,
            "processing_count": processing_count,
            "failed_count": failed_count,
            "drafted_count": drafted_count,
            "jobs_viral": jobs_viral,
            "show_worker_banner": new_count > 0 and jobs_viral == 0,
            "ffmpeg_ok": ViralService.ffmpeg_available(),
        }

    @staticmethod
    def _winget_links_dir() -> Optional[str]:
        local = os.environ.get("LOCALAPPDATA") or ""
        if not local:
            return None
        path = os.path.join(local, "Microsoft", "WinGet", "Links")
        return path if os.path.isdir(path) else None

    @staticmethod
    def _ensure_ffmpeg_on_path() -> None:
        """If winget installed ffmpeg but shell PATH stale, prepend Links for this process."""
        links = ViralService._winget_links_dir()
        if not links:
            return
        path_env = os.environ.get("PATH") or ""
        if links.lower() in path_env.lower():
            return
        os.environ["PATH"] = links + os.pathsep + path_env

    @staticmethod
    def resolve_ffmpeg() -> Optional[str]:
        ViralService._ensure_ffmpeg_on_path()
        found = shutil.which("ffmpeg")
        if found:
            return found
        links = ViralService._winget_links_dir()
        if links:
            candidate = os.path.join(links, "ffmpeg.exe")
            if os.path.isfile(candidate):
                return candidate
        return None

    @staticmethod
    def resolve_ffprobe() -> Optional[str]:
        ViralService._ensure_ffmpeg_on_path()
        found = shutil.which("ffprobe")
        if found:
            return found
        links = ViralService._winget_links_dir()
        if links:
            candidate = os.path.join(links, "ffprobe.exe")
            if os.path.isfile(candidate):
                return candidate
        return None

    @staticmethod
    def ffmpeg_available() -> bool:
        """True if ffprobe/ffmpeg resolvable (PATH or WinGet Links on Windows)."""
        return bool(ViralService.resolve_ffprobe() or ViralService.resolve_ffmpeg())

    @staticmethod
    def process_material(db: Session, material_id: int) -> Tuple[bool, str]:
        """Download + reup + queue one NEW/REUP/FAILED material (manual Smart bridge)."""
        from app.constants import ViralStatus
        from app.features.viral_intake.processor import ViralProcessorService

        mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
        if not mat:
            return False, f"Không tìm thấy material #{material_id}."
        if mat.status == ViralStatus.PROCESSING:
            return False, f"#{material_id} đang xử lý (PROCESSING) — đợi xong hoặc chờ recover stale."
        if mat.status not in (ViralStatus.NEW, ViralStatus.REUP, ViralStatus.FAILED):
            return False, f"#{material_id} trạng thái={mat.status} — chỉ xử lý NEW/REUP/FAILED."

        if not ViralService.ffmpeg_available():
            return (
                False,
                "Thiếu ffmpeg/ffprobe trên PATH — cài rồi thử lại (reup cần ffprobe).",
            )

        ViralProcessorService().download_and_queue(db, material_id)
        db.refresh(mat)
        tries = int(getattr(mat, "process_tries", 0) or 0)
        if mat.status == ViralStatus.DRAFTED:
            job = (
                db.query(Job)
                .filter(Job.viral_material_id == material_id)
                .order_by(Job.id.desc())
                .first()
            )
            jid = f" → Job #{job.id} ({job.status})" if job else ""
            return True, f"✅ #{material_id} đã tạo job{jid} (lần thử={tries})"
        if mat.status == ViralStatus.FAILED:
            err = (mat.last_error or "không rõ")[:100]
            return False, f"❌ #{material_id} lỗi (FAILED, lần thử={tries}): {err}"
        return True, f"#{material_id} xong — trạng thái={mat.status} lần thử={tries}"

    @staticmethod
    def process_new_batch(db: Session, limit: int = 3) -> Tuple[int, int, str]:
        """Process up to ``limit`` NEW materials (views desc)."""
        from app.constants import ViralStatus

        if not ViralService.ffmpeg_available():
            return 0, 0, "Thiếu ffmpeg/ffprobe trên PATH — không thể reup. Cài rồi thử lại."

        limit = max(1, min(10, int(limit or 3)))
        mats = (
            db.query(ViralMaterial)
            .filter(ViralMaterial.status == ViralStatus.NEW)
            .order_by(ViralMaterial.views.desc())
            .limit(limit)
            .all()
        )
        if not mats:
            return 0, 0, "Không còn video mới (NEW) để xử lý."

        ok = 0
        fail = 0
        notes: list[str] = []
        for mat in mats:
            success, msg = ViralService.process_material(db, mat.id)
            notes.append(msg)
            if success:
                ok += 1
            else:
                fail += 1
        summary = f"Đã xử lý {ok + fail}/{len(mats)} (thành công={ok}, lỗi={fail})."
        detail = " | ".join(notes[:3])
        return ok, fail, f"{summary} {detail}"[:280]

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
        except FileNotFoundError as e:
            msg = f"❌ Lỗi quét: {str(e)[:160]}"
            return 0, 0, msg
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

    @staticmethod
    def reprocess_reup(
        db: Session,
        material_id: int,
        preset: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Re-run anti-dupe on the latest _reup file, keeping old output if new pass fails."""
        material = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
        if not material:
            return False, "Không tìm thấy viral material."

        source_path = ViralService.find_reup_path(material.id, material.platform)
        if not source_path or not os.path.isfile(source_path):
            return False, "Chưa có file _reup để chạy lại."

        from app.features.viral_intake.reup_config import resolve_preset
        from app.features.viral_intake.reup_processor import ReupProcessor
        from app.features.viral_intake.reup_variants import record_reup_variant

        niches: list[str] = []
        if material.target_page and material.scraped_by_account_id:
            try:
                from app.core.strategic import PageStrategicService
                niches = PageStrategicService._lookup_page_niches(
                    db, material.scraped_by_account_id, material.target_page,
                ) or []
            except Exception:
                niches = []
        resolved_preset = resolve_preset(
            page_url=material.target_page,
            niches=niches,
            explicit=preset,
            material_id=material.id,
        )

        work_path = f"{source_path}.reprocess-src.mp4"
        try:
            shutil.copy2(source_path, work_path)
        except OSError as e:
            return False, f"Không thể chuẩn bị file để chạy lại reup: {e}"

        try:
            result = ReupProcessor.process(
                input_path=work_path,
                platform=material.platform or "unknown",
                output_dir=os.path.dirname(source_path),
                preset=resolved_preset,
                force=True,
                output_path=source_path,
                page_url=material.target_page,
                niches=niches,
                account_id=material.scraped_by_account_id,
            )
            if not result.success or not result.output_path:
                return False, result.error or "Chạy lại anti-dupe thất bại."

            try:
                record_reup_variant(
                    material_id=material.id,
                    preset=resolved_preset,
                    platform=material.platform,
                    target_page=material.target_page,
                    metrics=result.metrics,
                    source="reprocess",
                )
            except Exception:
                pass

            material.last_error = None
            db.commit()
            return True, f"Đã chạy lại anti-dupe (preset={resolved_preset})."
        finally:
            try:
                if os.path.exists(work_path):
                    os.remove(work_path)
            except OSError:
                pass
