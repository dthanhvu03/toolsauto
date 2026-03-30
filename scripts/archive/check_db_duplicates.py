#!/usr/bin/env python3
"""
Kiểm tra DB: trùng link TikTok (viral_materials), trùng job (dedupe_key/media_path), job kẹt RUNNING.
Chạy: PYTHONPATH=. python scripts/check_db_duplicates.py [--fix]
  --fix: (optional) reset job RUNNING kẹt về PENDING, xóa bản ghi viral trùng (giữ 1).
"""
import argparse
import os
import sys

# Cho phép chạy từ thư mục gốc project
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text, and_, or_
from sqlalchemy.orm import Session

from app.database.core import SessionLocal
from app.database.models import Job, ViralMaterial


def normalize_video_url(url: str) -> str:
    """Chuẩn hóa URL (bỏ query, rstrip /) — đồng bộ với viral_scan."""
    if not url or not url.strip():
        return url or ""
    return url.strip().split("?")[0].rstrip("/")


def check_duplicate_viral_urls(db: Session) -> list[dict]:
    """Trả về danh sách URL có nhiều hơn 1 bản ghi viral_materials."""
    rows = db.execute(
        text("""
            SELECT url, COUNT(*) AS cnt, GROUP_CONCAT(id) AS ids
            FROM viral_materials
            GROUP BY TRIM(SUBSTR(url, 1, INSTR(url || '?', '?') - 1))
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """)
    ).fetchall()
    return [{"url": r[0], "count": r[1], "ids": r[2]} for r in rows]


def check_duplicate_jobs_by_dedupe(db: Session) -> list[dict]:
    """Job trùng (account_id, dedupe_key) — vi phạm unique index nếu có > 1."""
    rows = db.execute(
        text("""
            SELECT account_id, dedupe_key, COUNT(*) AS cnt, GROUP_CONCAT(id) AS ids
            FROM jobs
            WHERE dedupe_key IS NOT NULL AND dedupe_key != ''
            GROUP BY account_id, dedupe_key
            HAVING COUNT(*) > 1
        """)
    ).fetchall()
    return [
        {"account_id": r[0], "dedupe_key": r[1], "count": r[2], "ids": r[3]}
        for r in rows
    ]


def check_duplicate_jobs_by_media_path(db: Session) -> list[dict]:
    """Job trùng media_path (cùng file được đăng nhiều lần)."""
    rows = db.execute(
        text("""
            SELECT media_path, COUNT(*) AS cnt, GROUP_CONCAT(id) AS ids
            FROM jobs
            WHERE media_path IS NOT NULL AND media_path != ''
            GROUP BY media_path
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """)
    ).fetchall()
    return [{"media_path": r[0], "count": r[1], "ids": r[2]} for r in rows]


def check_stuck_running_jobs(db: Session, older_than_seconds: int = 7200) -> list[Job]:
    """Job status=RUNNING nhưng started_at hoặc last_heartbeat_at quá cũ (mặc định 2h)."""
    import time
    cutoff = int(time.time()) - older_than_seconds
    return (
        db.query(Job)
        .filter(
            Job.status == "RUNNING",
            or_(
                and_(Job.started_at != None, Job.started_at < cutoff),
                and_(Job.last_heartbeat_at != None, Job.last_heartbeat_at < cutoff),
            ),
        )
        .all()
    )


def main():
    parser = argparse.ArgumentParser(description="Check DB for duplicates and stuck jobs")
    parser.add_argument("--fix", action="store_true", help="Apply fixes: remove viral dupes (keep 1), reset stuck RUNNING to PENDING")
    parser.add_argument("--stuck-hours", type=float, default=2.0, help="Consider RUNNING stuck if older than this many hours (default 2)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        stuck_seconds = int(args.stuck_hours * 3600)

        print("=" * 60)
        print("KIỂM TRA DB: TRÙNG LINK TIKTOK / JOB / JOB KẸT RUNNING")
        print("=" * 60)

        # 1) Viral materials trùng URL
        viral_dupes = check_duplicate_viral_urls(db)
        if viral_dupes:
            print(f"\n⚠️  VIRAL_MATERIALS — {len(viral_dupes)} URL bị trùng (nhiều bản ghi):")
            for d in viral_dupes:
                print(f"    URL: {d['url'][:70]}... | Số bản ghi: {d['count']} | ids: {d['ids']}")
            if args.fix:
                for d in viral_dupes:
                    ids = [int(x) for x in d["ids"].split(",")]
                    keep_id = min(ids)  # Giữ bản ghi id nhỏ nhất
                    for vid in ids:
                        if vid == keep_id:
                            continue
                        mat = db.query(ViralMaterial).filter(ViralMaterial.id == vid).first()
                        if mat:
                            db.delete(mat)
                            print(f"    [FIX] Đã xóa viral_materials id={vid}")
                db.commit()
                print("    Đã commit xóa bản trùng viral.")
        else:
            print("\n✅ VIRAL_MATERIALS — Không có URL trùng.")

        # 2) Job trùng (account_id, dedupe_key)
        job_dedupe_dupes = check_duplicate_jobs_by_dedupe(db)
        if job_dedupe_dupes:
            print(f"\n⚠️  JOBS — {len(job_dedupe_dupes)} cặp (account_id, dedupe_key) trùng:")
            for d in job_dedupe_dupes:
                print(f"    account_id={d['account_id']} dedupe_key={d['dedupe_key'][:30]}... | cnt={d['count']} | ids: {d['ids']}")
            print("    (Không tự động fix — cần xử lý tay hoặc xóa job dư.)")
        else:
            print("\n✅ JOBS (dedupe_key) — Không có trùng.")

        # 3) Job trùng media_path
        media_dupes = check_duplicate_jobs_by_media_path(db)
        if media_dupes:
            print(f"\n⚠️  JOBS — {len(media_dupes)} media_path bị dùng cho nhiều job:")
            for d in media_dupes[:15]:
                path = d["media_path"]
                if len(path) > 55:
                    path = path[:52] + "..."
                print(f"    {path} | cnt={d['count']} | ids: {d['ids']}")
            if len(media_dupes) > 15:
                print(f"    ... và {len(media_dupes) - 15} nhóm khác.")
            print("    (Có thể do reup cùng file nhiều lần — không tự xóa.)")
        else:
            print("\n✅ JOBS (media_path) — Không có trùng.")

        # 4) Job kẹt RUNNING
        stuck = check_stuck_running_jobs(db, older_than_seconds=stuck_seconds)
        if stuck:
            print(f"\n⚠️  JOBS — {len(stuck)} job RUNNING nhưng quá cũ (> {args.stuck_hours}h):")
            for j in stuck:
                print(f"    Job #{j.id} account_id={j.account_id} started_at={j.started_at} heartbeat={j.last_heartbeat_at}")
            if args.fix:
                for j in stuck:
                    j.status = "PENDING"
                    j.started_at = None
                    j.last_heartbeat_at = None
                    j.locked_at = None
                    print(f"    [FIX] Job #{j.id} → PENDING")
                db.commit()
                print("    Đã reset job kẹt về PENDING.")
        else:
            print(f"\n✅ JOBS (RUNNING) — Không có job kẹt (> {args.stuck_hours}h).")

        print("\n" + "=" * 60)
        if args.fix and (viral_dupes or stuck):
            print("Đã áp dụng --fix. Chạy lại không --fix để xác nhận sạch.")
        print("Kết thúc.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
