"""Giao diện dòng lệnh CLI cho Threads Growth Agent (A/B Testing & Kéo Khách).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Optional

from app.features.threads.growth.config import (
    DB_PATH,
    DEMO_DB_PATH,
    load_profiles,
    ABVariant,
    TargetBot,
)
from app.features.threads.growth.runner import GrowthRunner
from app.features.threads.growth.scanner import ScannedPost
from app.features.threads.growth.storage import GrowthStorage


def format_table_row(cols: list, widths: list) -> str:
    return " | ".join(f"{str(c):<{w}}"[:w] for c, w in zip(cols, widths))


def cmd_stats(runner: GrowthRunner) -> None:
    stats = runner.get_ab_summary()
    print("\n" + "=" * 65)
    print(" 📊 THỐNG KÊ THỬ NGHIỆM A/B - THREADS GROWTH AGENT")
    print("=" * 65)

    headers = ["Bot Mục Tiêu", "Biến Thể (Variant)", "Chờ duyệt", "Đã duyệt", "Đã đăng", "Từ chối"]
    widths = [18, 22, 10, 10, 10, 10]
    print(format_table_row(headers, widths))
    print("-" * 88)

    for bot_key, variants in stats.items():
        profile = load_profiles()[TargetBot(bot_key)]
        for var_key, counts in variants.items():
            var_enum = ABVariant(var_key)
            var_cfg = profile.variants[var_enum]
            row = [
                profile.handle,
                f"Variant {var_key}: {var_cfg.name[:12]}...",
                counts.get("pending", 0),
                counts.get("approved", 0),
                counts.get("posted", 0),
                counts.get("rejected", 0),
            ]
            print(format_table_row(row, widths))
    print("=" * 65 + "\n")


def cmd_list(storage: GrowthStorage, bot_filter: Optional[str] = None) -> None:
    bot = TargetBot(bot_filter) if bot_filter else None
    posts = storage.get_pending_posts(bot=bot, limit=20)
    print("\n" + "=" * 75)
    print(f" 📋 DANH SÁCH BÀI VIẾT ĐANG CHỜ DUYỆT ({len(posts)} bài)")
    print("=" * 75)

    if not posts:
        print(" Hiện không có bài viết nào đang chờ duyệt.")
        print(" (Chưa có quét Threads thật — thử luồng bằng: python -m app.features.threads.growth.cli demo)\n")
        return

    for p in posts:
        bot_cfg = load_profiles()[TargetBot(p["target_bot"])]
        var_cfg = bot_cfg.variants[ABVariant(p["variant"])]
        print(f"🔹 [ID: {p['id']}] - Tác giả: @{p['author']} (Điểm phù hợp: {p['relevance_score']}%)")
        print(f"   Link bài: {p['post_url']}")
        print(f"   Nội dung: {p['content']}")
        print(f"   🎯 Mục tiêu: {bot_cfg.name} ({bot_cfg.handle})")
        print(f"   🧪 Thử nghiệm A/B: [Biến thể {p['variant']}] - {var_cfg.name}")
        print(f"   🔗 Tracking URL: {var_cfg.tracking_url}")
        print("   💬 Gợi ý phản hồi:")
        print(f"      👉 \"{p['suggested_reply']}\"")
        print(f"   Lệnh thao tác nhanh: approve {p['id']}  |  reject {p['id']}  |  switch {p['id']} {'B' if p['variant'] == 'A' else 'A'}")
        print("-" * 75)
    print()


def cmd_quota(runner: GrowthRunner) -> None:
    q = runner.posting_quota()
    lim = runner.limits
    print(
        f"Đã đăng: {q.posted_last_hour}/{lim.max_replies_per_hour} trong 1 giờ, "
        f"{q.posted_last_day}/{lim.max_replies_per_day} trong 24 giờ"
    )
    if q.allowed:
        print("✅ Được đăng reply tiếp theo.")
    else:
        print(f"⏳ Chưa được đăng: {q.reason} — chờ khoảng {q.wait_sec}s.")


async def cmd_demo(runner: GrowthRunner) -> None:
    """Nạp 4 bài mẫu (bịa, không phải bài Threads thật) vào DB demo riêng để thử bộ lọc & A/B."""
    samples = [
        ScannedPost(
            thread_id="th_shopee_01",
            post_url="https://www.threads.net/@khanhlinh/post/DBx123",
            author="khanhlinh",
            content="Mọi người ơi có ai có mã Shopee 50k cho đơn 300k không cho em xin với, áp mã toàn hết lượt hichic 😭",
            keyword="mã giảm giá shopee",
        ),
        ScannedPost(
            thread_id="th_shopee_02",
            post_url="https://www.threads.net/@duytung/post/DBy456",
            author="duytung",
            content="Đợt này săn sale Shopee với TikTok Shop tốn tiền thật sự, ai biết cách nào mua sắm tiết kiệm bớt không?",
            keyword="săn sale shopee",
        ),
        ScannedPost(
            thread_id="th_ai_01",
            post_url="https://www.threads.net/@techlover/post/DBz789",
            author="techlover",
            content="Có bên nào bán tài khoản ChatGPT Plus uy tín dùng ổn định không mọi người, tự thanh toán bằng thẻ visa toàn bị từ chối.",
            keyword="mua chatgpt plus",
        ),
        ScannedPost(
            thread_id="th_ai_02",
            post_url="https://www.threads.net/@graphic_designer/post/DBw999",
            author="graphic_designer",
            content="Cần mua gấp tài khoản Canva Pro làm bài tập thuyết trình tối nay, ai cấp tự động liền được không?",
            keyword="tài khoản canva pro",
        ),
    ]

    print(f"\n🧪 DEMO — DB riêng: {runner.storage.db_path}")
    print(f"🔍 Đang tiếp nhận & phân tích {len(samples)} bài mẫu...")
    for s in samples:
        pid = await runner.ingest_scanned_post(s)
        if pid:
            post = runner.storage.get_post_by_id(pid)
            print(f"  ✅ Đã tiếp nhận [ID: {pid}] | {post['target_bot']} [Variant {post['variant']}] -> Tác giả: @{s.author}")
        else:
            print(f"  ⏩ Bỏ qua (đã có / không khớp / điểm thấp): {s.thread_id}")

    print("\n✅ Xong. Xem bằng: ... cli --demo list\n")


def main() -> int:
    # Console Windows: in tiếng Việt / emoji không vỡ.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Threads Growth Agent CLI (A/B Testing)")
    parser.add_argument("--demo", action="store_true", help=f"Dùng DB demo ({DEMO_DB_PATH.name}) thay DB thật")
    parser.add_argument("--db", type=Path, default=None, help=f"Đường dẫn DB (mặc định {DB_PATH})")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("scan", help="Quét bài viết mới trên Threads (chưa làm)")
    subparsers.add_parser("demo", help="Nạp 4 bài mẫu vào DB demo để thử luồng")

    list_p = subparsers.add_parser("list", help="Liệt kê danh sách bài viết chờ duyệt")
    list_p.add_argument("--bot", choices=[b.value for b in TargetBot], default=None, help="Lọc theo bot")

    app_p = subparsers.add_parser("approve", help="Duyệt bài viết để chuẩn bị đăng")
    app_p.add_argument("id", type=int, help="ID bài viết")
    app_p.add_argument("--reply", type=str, default=None, help="Sửa câu trả lời trước khi duyệt")

    rej_p = subparsers.add_parser("reject", help="Từ chối bài viết")
    rej_p.add_argument("id", type=int, help="ID bài viết")
    rej_p.add_argument("--reason", type=str, default="user_rejected", help="Lý do từ chối")

    sw_p = subparsers.add_parser("switch", help="Đổi biến thể A/B (AI viết lại câu trả lời)")
    sw_p.add_argument("id", type=int, help="ID bài viết")
    sw_p.add_argument("variant", choices=[v.value for v in ABVariant], help="Biến thể muốn chuyển sang")

    subparsers.add_parser("stats", help="Xem thống kê phân phối A/B testing")
    subparsers.add_parser("quota", help="Xem còn được đăng reply không (giới hạn trên web)")

    args = parser.parse_args()

    if args.command == "scan":
        print("❌ Chưa có quét Threads thật (cần PLAN riêng: trình duyệt + đọc kết quả tìm kiếm).")
        print("   Thử luồng bằng bài mẫu: python -m app.features.threads.growth.cli demo")
        return 2

    use_demo = args.demo or args.command == "demo"
    db_path = args.db or (DEMO_DB_PATH if use_demo else DB_PATH)
    runner = GrowthRunner(storage=GrowthStorage(db_path=db_path))

    if args.command == "demo":
        asyncio.run(cmd_demo(runner))
    elif args.command == "list":
        cmd_list(runner.storage, args.bot)
    elif args.command == "approve":
        res = runner.approve_and_prepare(args.id, args.reply)
        if not res:
            print(f"❌ Không tìm thấy bài ID {args.id}")
            return 1
        print(f"✅ Đã duyệt bài ID {args.id} (Trạng thái: {res['status']})")
        print(f"   Nội dung phản hồi: \"{res['actual_reply']}\"")
        cmd_quota(runner)
    elif args.command == "reject":
        if not runner.reject(args.id, args.reason):
            print(f"❌ Không tìm thấy bài ID {args.id}")
            return 1
        print(f"🚫 Đã từ chối bài ID {args.id}")
    elif args.command == "switch":
        post = asyncio.run(runner.switch_variant(args.id, ABVariant(args.variant)))
        if not post:
            print(f"❌ Không tìm thấy bài ID {args.id}")
            return 1
        print(f"🔄 Đã chuyển bài ID {args.id} sang [Biến thể {args.variant}]")
        print(f"   Câu gợi ý mới: \"{post['suggested_reply']}\"")
        print(f"   ({post['ai_analysis']})")
    elif args.command == "quota":
        cmd_quota(runner)
    else:
        cmd_stats(runner)
    return 0


if __name__ == "__main__":
    sys.exit(main())
