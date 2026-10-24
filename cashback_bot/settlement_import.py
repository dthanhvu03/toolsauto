"""Công cụ quản trị nhập chứng từ đối soát (PLAN-075). Chạy trên máy chủ, không qua Telegram.

    python -m cashback_bot.settlement_import new-batch --period 2026-10 [--payment-ref REF]
    python -m cashback_bot.settlement_import import --batch 1 --file statement.json [--replaces 3]
    python -m cashback_bot.settlement_import show --batch 1

Chỉ nhận định dạng chuẩn `cashback_settlement_v1` (xem settlement.py). File Shopee thật cần parser riêng
khi có mẫu. Không in nội dung chứng từ hay số tài khoản ra màn hình.
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
from pathlib import Path

from cashback_bot.config import ConfigError, load_settings
from cashback_bot.db import TrackingRepository
from cashback_bot.redact import RedactingFormatter
from cashback_bot.settlement import MAX_BYTES, EvidenceError, SettlementEngine

LOG_FORMAT = "%(asctime)s [Cashback] %(levelname)s %(message)s"


def read_evidence_file(path: Path) -> bytes:
    """Đọc file chứng từ của quản trị viên: phải là file thường, không phải symlink, không quá MAX_BYTES."""
    if path.is_symlink() or not path.is_file():
        raise EvidenceError("not_a_regular_file")
    if path.stat().st_size > MAX_BYTES:
        raise EvidenceError("too_large")
    return path.read_bytes()


def run(argv: list[str] | None, repo: TrackingRepository, actor: str | None = None) -> dict:
    parser = argparse.ArgumentParser(prog="cashback_bot.settlement_import")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new-batch")
    new.add_argument("--period", required=True)
    new.add_argument("--payment-ref")
    imp = sub.add_parser("import")
    imp.add_argument("--batch", type=int, required=True)
    imp.add_argument("--file", type=Path, required=True)
    imp.add_argument("--replaces", type=int)
    show = sub.add_parser("show")
    show.add_argument("--batch", type=int, required=True)
    args = parser.parse_args(argv)

    engine = SettlementEngine(repo)
    who = actor or f"cli:{getpass.getuser()}"
    if args.command == "new-batch":
        return {"batch_id": engine.create_batch(args.period, who, args.payment_ref)}
    if args.command == "import":
        evidence_id = engine.import_document(args.batch, read_evidence_file(args.file), who, replaces=args.replaces)
        result = engine.evaluate(args.batch)
        return {"evidence_id": evidence_id, "status": result.status, "discrepancies": [d.code for d in result.discrepancies]}
    result = engine.evaluate(args.batch)
    return {
        "batch_id": args.batch,
        "status": result.status,
        "discrepancies": [d.code for d in result.discrepancies],
        "bot_vnd": result.bot_vnd,
        "non_bot_vnd": result.non_bot_vnd,
        "unknown_vnd": result.unknown_vnd,
        "unallocated_vnd": result.unallocated_vnd,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(RedactingFormatter(LOG_FORMAT))
    try:
        settings = load_settings(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    except ConfigError as exc:
        raise SystemExit(str(exc)) from exc
    repo = TrackingRepository(settings.db_path)
    repo.migrate()
    try:
        print(json.dumps(run(None, repo), ensure_ascii=False))
    except EvidenceError as exc:
        raise SystemExit(f"Từ chối: {exc.code}") from exc


if __name__ == "__main__":
    main()
