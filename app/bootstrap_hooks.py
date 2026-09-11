"""Register cross-feature hooks from composition root (ADR-007)."""
from __future__ import annotations

import random
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.core import feature_hooks
from app.core.notifier.service import NotifierService
from app.core.account import get_discovery_keywords
from app.core.database.models import Account, DiscoveredChannel


def register_feature_hooks() -> None:
    from app.features.viral_intake.processor import ViralProcessorService
    from app.features.viral_intake.scan import get_default_min_views, run_tiktok_competitor_scan
    from app.features.viral_intake.discovery_scraper import DiscoveryScraper
    from app.features.viral_intake.sources import SourceService
    from app.features.viral_intake.service import ViralService
    from app.features.telegram_bot.poller import TelegramPoller

    def viral_process_all(db: Session):
        return ViralProcessorService().process_all(db)

    def viral_tiktok_scan(db: Session):
        return run_tiktok_competitor_scan(db)

    def viral_scan_sources(db: Session) -> dict:
        return SourceService.scan_all(db)

    def viral_min_views(db: Session):
        return get_default_min_views(db)

    def viral_add_link(db: Session, url: str) -> dict:
        """
        ADR-034 — Owner dán link vào chat Telegram: kênh ⇒ nguồn tự quét, video ⇒ material.

        Phải đi qua hook chứ không cho `telegram_bot` import thẳng `viral_intake`:
        import-linter chặn feature này gọi feature kia (ADR-007). Đây cũng là cách
        `/discovery` đang làm.
        """
        if SourceService.detect_channel(url):
            ok, msg, source_id = SourceService.add_source(db, url)
            return {"kind": "source", "ok": ok, "msg": msg, "id": source_id}
        ok, msg, material_id = ViralService.add_material_from_url(db, url)
        return {"kind": "material", "ok": ok, "msg": msg, "id": material_id}

    def viral_add_source_from_material(db: Session, material_id: int) -> dict:
        """
        ADR-034 + ADR-028 — biến video đã dán thành nguồn kênh, dò `channel_id` từ chính nó.

        Kênh TikTok không liệt kê được bằng ``@handle`` thì đây là đường DUY NHẤT để thêm nó,
        mà lúc đó Owner đang ở trong chat chứ không ở web.
        """
        from app.core.database.models import ViralMaterial

        mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
        if not mat or not mat.url:
            return {"ok": False, "msg": f"Không tìm thấy material #{material_id}"}
        ok, msg, source_id = SourceService.add_source(db, mat.url)
        return {"ok": ok, "msg": msg, "id": source_id}

    def viral_sources_summary(db: Session) -> list[dict]:
        """ADR-037 — nguồn cho `/nguon` trong Telegram. Trả dict thuần: `telegram_bot` không
        được import model của feature khác (ADR-007)."""
        out = []
        for s in SourceService.list_sources(db):
            out.append({
                "id": s.id, "platform": s.platform, "handle": s.handle or s.url,
                "min_views": s.min_views, "max_videos": s.max_videos,
                "enabled": bool(s.enabled), "last_scanned_at": s.last_scanned_at,
                "last_found": s.last_found, "last_error": s.last_error,
            })
        return out

    def viral_scan_source(db: Session, source_id: int) -> dict:
        src = next((s for s in SourceService.list_sources(db) if s.id == source_id), None)
        if src is None:
            return {"ok": False, "msg": f"Không tìm thấy nguồn #{source_id}"}
        found, skipped, error = SourceService.scan_source(db, src)
        if error:
            return {"ok": False, "msg": f"Quét lỗi: {error}"}
        return {"ok": True, "msg": f"Tìm thấy {found} video mới, bỏ qua {skipped}."}

    def viral_toggle_source(db: Session, source_id: int) -> dict:
        src = next((s for s in SourceService.list_sources(db) if s.id == source_id), None)
        if src is None:
            return {"ok": False, "msg": f"Không tìm thấy nguồn #{source_id}"}
        moi = not bool(src.enabled)
        SourceService.set_enabled(db, source_id, moi)
        return {"ok": True, "msg": f"Nguồn #{source_id} nay {'BẬT' if moi else 'TẮT'}.", "enabled": moi}

    def viral_list_materials(db: Session, status: str, limit: int = 10) -> list[dict]:
        """ADR-037 — material theo trạng thái cho `/moi` và `/sansang`."""
        from app.core.database.models import ViralMaterial

        rows = (
            db.query(ViralMaterial)
            .filter(ViralMaterial.status == status)
            # ADR-042: đã đăng thì xếp theo lúc đăng — cái vừa đăng nằm trên, đúng thứ Owner tìm.
            .order_by(*((ViralMaterial.posted_at.desc().nullslast(),) if status == "POSTED" else ()), ViralMaterial.id.desc())
            .limit(max(1, min(int(limit), 25)))
            .all()
        )
        return [{
            "id": m.id, "platform": m.platform, "title": m.title, "views": m.views,
            "url": m.url, "clip_start_sec": m.clip_start_sec, "clip_length_sec": m.clip_length_sec,
            "parent_material_id": m.parent_material_id, "part_index": m.part_index, "part_total": m.part_total,
            "posted_at": m.posted_at,
        } for m in rows]

    def viral_fetch_original(db: Session, url: str) -> dict:
        """ADR-043 — tải bản gốc về máy, không reup. Chậm (tải cả file) — gọi từ luồng nền."""
        from app.features.viral_intake.fetch import fetch_original

        return fetch_original(db, url)

    def viral_mark_posted(db: Session, material_id: int) -> dict:
        """ADR-042 — Owner bấm Đã đăng trên Telegram."""
        ok, msg = ViralService.mark_posted(db, material_id)
        return {"ok": ok, "msg": msg}

    def viral_unmark_posted(db: Session, material_id: int) -> dict:
        ok, msg = ViralService.unmark_posted(db, material_id)
        return {"ok": ok, "msg": msg}

    def viral_propose_split(db: Session, material_id: int, n: int) -> dict:
        """ADR-041 — tính kế hoạch chia N phần (chậm: Whisper) — gọi từ luồng nền."""
        from app.features.viral_intake.split import describe_plan, propose_split

        res = propose_split(db, material_id, n)
        if res.get("ok"):
            res["text"] = describe_plan(material_id, res["plan"])
            res.pop("plan", None)  # dataclass không đi qua ranh giới hook
        return res

    def viral_apply_split(db: Session, material_id: int) -> dict:
        """ADR-041 — tạo các phần con theo kế hoạch đã lưu. Trả child_ids để xử lý lần lượt."""
        from app.features.viral_intake.split import apply_split

        return apply_split(db, material_id)

    def viral_set_clip(db: Session, material_id: int, start: int, length=None) -> dict:
        ok, msg = ViralService.set_clip_start(db, material_id, start, length)
        return {"ok": ok, "msg": msg}

    def viral_material_frames(db: Session, material_id: int) -> dict:
        """ADR-037 — ảnh lưới 4×3 + mốc giây của từng khung, để dựng nút trong chat."""
        frames = ViralService.list_source_frames(material_id)
        return {"frames": frames, "sheet": ViralService.build_frame_sheet(material_id) if frames else None}

    def viral_resend_material(db: Session, material_id: int) -> dict:
        """ADR-037 — bắn lại video + caption cho một material đã sẵn sàng."""
        from app.core.database.models import ViralMaterial

        mat = db.query(ViralMaterial).filter(ViralMaterial.id == material_id).first()
        if not mat:
            return {"ok": False, "msg": f"Không tìm thấy material #{material_id}"}
        path = ViralService.find_reup_path(mat.id, mat.platform)
        if not path:
            return {"ok": False, "msg": f"Material #{material_id} chưa có file đã xử lý."}
        src = ViralService.find_source_path(mat.id, mat.platform)
        NotifierService.notify_material_ready(
            mat, path,
            drive_path=None,
            source_duration=ViralService.probe_duration(src) if src else None,
        )
        return {"ok": True, "msg": f"Đã gửi lại #{material_id}."}

    def viral_process_one(db: Session, material_id: int):
        """ADR-034 — xử lý đúng một material (tải + cắt + caption), dùng cho link dán ở chat."""
        return ViralService.process_material(db, material_id)

    def viral_force_discovery(db: Session) -> Tuple[List[DiscoveredChannel], List[str], int]:
        scraper = DiscoveryScraper()
        total_found = 0
        scan_log: List[str] = []
        accounts = db.query(Account).filter(Account.is_active == True).all()  # noqa: E712
        for acc in accounts:
            keywords = get_discovery_keywords(acc)
            if not keywords:
                continue
            selected = random.sample(keywords, min(2, len(keywords)))
            for kw in selected:
                try:
                    found = scraper.discover_for_keyword(kw, acc.id, db)
                    total_found += found
                    scan_log.append(f"✅ '{acc.name}' / kw='{kw}': {found} kênh mới")
                except Exception as e:
                    scan_log.append(f"❌ '{acc.name}' / kw='{kw}': lỗi {str(e)[:80]}")
        return total_found, scan_log

    def viral_discover_keyword(keyword: str, account_id: int, db: Session) -> int:
        return DiscoveryScraper().discover_for_keyword(keyword, account_id, db)

    def telegram_make_poller(token: str, chat_id: str):
        return TelegramPoller(token, chat_id)

    def facebook_strategic_boost(db: Session):
        from app.core.strategic import PageStrategicService

        return PageStrategicService.run_auto_boost(db)

    feature_hooks.register("viral.process_all", viral_process_all)
    feature_hooks.register("viral.tiktok_scan", viral_tiktok_scan)
    feature_hooks.register("viral.scan_sources", viral_scan_sources)
    feature_hooks.register("viral.min_views", viral_min_views)
    feature_hooks.register("viral.add_link", viral_add_link)
    feature_hooks.register("viral.add_source_from_material", viral_add_source_from_material)
    feature_hooks.register("viral.process_one", viral_process_one)
    feature_hooks.register("viral.sources_summary", viral_sources_summary)
    feature_hooks.register("viral.scan_source", viral_scan_source)
    feature_hooks.register("viral.toggle_source", viral_toggle_source)
    feature_hooks.register("viral.list_materials", viral_list_materials)
    feature_hooks.register("viral.set_clip", viral_set_clip)
    feature_hooks.register("viral.material_frames", viral_material_frames)
    feature_hooks.register("viral.resend_material", viral_resend_material)
    feature_hooks.register("viral.fetch_original", viral_fetch_original)
    feature_hooks.register("viral.mark_posted", viral_mark_posted)
    feature_hooks.register("viral.unmark_posted", viral_unmark_posted)
    feature_hooks.register("viral.propose_split", viral_propose_split)
    feature_hooks.register("viral.apply_split", viral_apply_split)
    feature_hooks.register("viral.force_discovery", viral_force_discovery)
    feature_hooks.register("viral.discover_keyword", viral_discover_keyword)
    feature_hooks.register("telegram.make_poller", telegram_make_poller)
    feature_hooks.register("facebook.strategic_boost", facebook_strategic_boost)
