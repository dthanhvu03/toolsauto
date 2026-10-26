"""Rà soát 2026-10-26, đợt 5 (phần nhỏ): tách việc định kỳ, khoá sổ ví ở tầng DB, migrate có khoá, backup đủ bảng tiền."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from cashback_bot import poller
from cashback_bot.backup import REQUIRED_TABLES, run_scheduled_backup
from cashback_bot.db import TrackingRepository


def _repo(tmp_path) -> TrackingRepository:
    repo = TrackingRepository(str(tmp_path / "cashback.sqlite"))
    repo.migrate()
    return repo


def _insert_entry(conn, cid: str, commission: int, cashback: int, status: str = "pending") -> None:
    conn.execute(
        "INSERT INTO cashback_entries (conversion_id, telegram_user_id, commission_vnd, cashback_vnd, fee_vnd, tax_vnd, "
        "policy_label, status, created_at, updated_at) VALUES (?, 1, ?, ?, 0, 0, 'v1.1:70', ?, 'x', 'x')",
        (cid, commission, cashback, status),
    )


def test_viec_dinh_ky_loi_khong_chan_viec_sau(monkeypatch):
    ran: list[str] = []
    poller._periodic_failed.clear()

    def broken():
        raise RuntimeError("hỏng")

    poller._periodic("hong", broken)
    poller._periodic("backup", lambda: ran.append("backup"))
    assert ran == ["backup"] and "hong" in poller._periodic_failed
    first = poller._periodic_failed["hong"]
    poller._periodic("hong", broken)
    assert poller._periodic_failed["hong"] == first, "lỗi lặp lại trong 10 phút không báo thêm"


def test_so_vi_phan_khach_khong_vuot_hoa_hong_va_khoan_vao_vi_khong_sua_duoc(tmp_path):
    repo = _repo(tmp_path)
    with repo.connect() as conn:
        _insert_entry(conn, "ok", 10_000, 7_000)
        _insert_entry(conn, "ok:clawback:1", -3_000, -2_100)
        with pytest.raises(sqlite3.IntegrityError, match="cashback above commission"):
            _insert_entry(conn, "qua", 10_000, 12_000)
        with pytest.raises(sqlite3.IntegrityError, match="cashback above commission"):
            conn.execute("UPDATE cashback_entries SET cashback_vnd = 20000 WHERE conversion_id = 'ok'")
        # Khoá «available» cần kỳ đối soát (financial_lock); ở đây chỉ thử khoá số tiền nên tắt tạm các trigger đó.
        for name in ("financial_lock_entry_update", "financial_lock_v2_entry_update", "financial_lock_platform_entry_update"):
            conn.execute(f"DROP TRIGGER IF EXISTS {name}")
        conn.execute("UPDATE cashback_entries SET status = 'available' WHERE conversion_id = 'ok'")
        conn.execute("UPDATE cashback_entries SET cashback_vnd = 7000, status = 'cancelled' WHERE conversion_id = 'ok'")
        conn.execute("UPDATE cashback_entries SET status = 'available' WHERE conversion_id = 'ok'")
        with pytest.raises(sqlite3.IntegrityError, match="frozen"):
            conn.execute("UPDATE cashback_entries SET cashback_vnd = 5000 WHERE conversion_id = 'ok'")


def test_hai_tien_trinh_migrate_cung_luc(tmp_path):
    path = str(tmp_path / "cashback.sqlite")
    errors: list[BaseException] = []

    def run():
        try:
            TrackingRepository(path).migrate()
        except BaseException as exc:  # noqa: BLE001 - gom lỗi của luồng để assert
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    assert errors == []
    with sqlite3.connect(path) as conn:
        assert "platform" in {row[1] for row in conn.execute("PRAGMA table_info(shopee_conversions)")}


def test_backup_kiem_ca_bang_tien(tmp_path):
    assert {"cashback_entries", "cashback_payouts", "payout_events", "shopee_conversions"} <= set(REQUIRED_TABLES)
    repo = _repo(tmp_path)
    check = run_scheduled_backup(Path(repo.path), tmp_path / "backups", keep=3)
    assert check.tables >= len(REQUIRED_TABLES)
