"""PLAN-081 Gate B (Phương án B): theo dõi đơn qua bot đang chờ khi ra khỏi khung đồng bộ 30 ngày.

Không gọi Shopee thật, không đổi tiền, không gửi tin khách. Shopee, Telegram, đồng hồ đều giả lập.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cashback_bot import reconciliation
from cashback_bot.config import AutoSyncConfig
from cashback_bot.shopee_client import ShopeeApiError
from cashback_bot.sync_scheduler import snapshot
from tests.test_cashback_auto_sync import ON, Clock, FakeShopee, _admin, _coord, _order, _ready_bot
from tests.test_cashback_wallet import ADMIN, USER, _callback, _link

NOW = datetime(2026, 12, 1, 3, 0, tzinfo=timezone.utc)


def _ts(moment: datetime) -> int:
    return int(moment.timestamp())


def _tracking(repo):
    with repo.connect() as conn:
        return {r["conversion_id"]: (r["tracking_status"], r["reason"], r["missed_runs"])
                for r in conn.execute("SELECT * FROM conversion_reconciliation")}


def _events_count(repo, sql_where="1=1"):
    with repo.connect() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM admin_notifications WHERE {sql_where}").fetchone()[0]


def _seed(bot, ages: dict[str, timedelta], sub: str, notifier=None):
    """Ghi đơn qua một lượt đồng bộ giả (để có last_seen), giờ mua = NOW − tuổi."""
    shopee = FakeShopee([_order(cid, sub, purchase=_ts(NOW - age)) for cid, age in ages.items()])
    coordinator = _coord(bot.repo, shopee, cfg=AutoSyncConfig(), clock=Clock(NOW), notifier=notifier)
    coordinator.run("manual")
    return coordinator, shopee


# --- Tuổi đơn (1–7, 23) -------------------------------------------------------------------------------


def test_01_07_nhan_theo_tuoi_dung_bien_giay(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    ages = {
        "d19": timedelta(days=19, hours=23), "d20": timedelta(days=20),
        "d29": timedelta(days=30) - timedelta(seconds=1), "d30": timedelta(days=30), "d31": timedelta(days=31),
        "d35": timedelta(days=35), "d45": timedelta(days=45), "d60": timedelta(days=60), "d90": timedelta(days=90),
    }
    _seed(bot, ages, sub)
    reconciliation.evaluate(bot.repo, NOW)
    status = {cid: value[0] for cid, value in _tracking(bot.repo).items()}
    assert status == {
        "d19": "OBSERVED_RECENTLY", "d20": "APPROACHING_WINDOW", "d29": "APPROACHING_WINDOW",
        "d30": "OUTSIDE_WINDOW_UNVERIFIED", "d31": "OUTSIDE_WINDOW_UNVERIFIED", "d35": "OUTSIDE_WINDOW_UNVERIFIED",
        "d45": "RECONCILIATION_REQUIRED", "d60": "RECONCILIATION_REQUIRED", "d90": "RECONCILIATION_REQUIRED",
    }


def test_08_mua_cu_shopee_bao_muon_tuoi_tinh_theo_gio_mua(tmp_path):
    bot = _ready_bot(tmp_path)
    _seed(bot, {"late": timedelta(days=28)}, _link(bot))  # lần đầu bot thấy khi đơn đã 28 ngày
    reconciliation.evaluate(bot.repo, NOW)
    assert _tracking(bot.repo)["late"][0] == "APPROACHING_WINDOW"


def test_21_khong_co_gio_mua(tmp_path):
    bot = _ready_bot(tmp_path)
    shopee = FakeShopee([_order("nopt", _link(bot), purchase=0)])
    _coord(bot.repo, shopee, cfg=AutoSyncConfig()).run("manual")
    reconciliation.evaluate(bot.repo, NOW)
    assert _tracking(bot.repo)["nopt"][:2] == ("RECONCILIATION_REQUIRED", "no_purchase_time")


# --- Lượt đồng bộ: vắng mặt, PARTIAL, cùng lượt (13–15, 19, 24, 25) ----------------------------------


def test_24_25_vang_trong_khung_hai_luot_thanh_cong_thi_can_doi_soat(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([_order("o1", sub)])  # mua gần đây, trong khung
    coordinator = _coord(bot.repo, shopee, cfg=AutoSyncConfig())
    coordinator.run("manual")
    assert _tracking(bot.repo)["o1"] == ("OBSERVED_RECENTLY", "seen", 0)
    coordinator.run("manual")  # vẫn thấy, không đổi
    assert _tracking(bot.repo)["o1"][2] == 0
    shopee.conversions = []
    coordinator.run("manual")
    assert _tracking(bot.repo)["o1"] == ("OBSERVED_RECENTLY", "seen", 1)
    coordinator.run("manual")
    assert _tracking(bot.repo)["o1"] == ("RECONCILIATION_REQUIRED", "missing_in_window", 2)
    shopee.conversions = [_order("o1", sub)]
    coordinator.run("manual")
    assert _tracking(bot.repo)["o1"] == ("OBSERVED_RECENTLY", "seen", 0), "thấy lại thì về bình thường"


def test_13_14_15_luot_partial_hoac_loi_khong_tinh_vang(tmp_path, monkeypatch):
    from cashback_bot import shopee_sync

    monkeypatch.setattr(shopee_sync, "PAGE_SIZE", 1)
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([_order("a", sub), _order("b", sub)])
    coordinator = _coord(bot.repo, shopee, cfg=AutoSyncConfig())
    coordinator.run("manual")
    shopee.errors[("conv", 2)] = ShopeeApiError("HTTP 400", 400)  # trang 2 lỗi: đơn b không đọc được
    assert coordinator.run("manual").status == "partial"
    shopee.check_status = lambda: __import__("cashback_bot.shopee_client", fromlist=["x"]).ShopeeStatusResult(
        ok=False, status_code=502, error_message="502", category="TRANSIENT_SERVER_ERROR")
    coordinator.run("manual")
    assert {cid: v[2] for cid, v in _tracking(bot.repo).items()} == {"a": 0, "b": 0}


def test_19_danh_gia_lai_cung_luot_khong_dem_hai_lan(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([_order("o1", sub)])
    coordinator = _coord(bot.repo, shopee, cfg=AutoSyncConfig())
    coordinator.run("manual")
    shopee.conversions = []
    result = coordinator.run("manual")
    for _ in range(3):
        reconciliation.evaluate(bot.repo, NOW - timedelta(days=30), run_id=result.run_id,
                                window_start=result.stats["window_start"], run_success=True)
    assert _tracking(bot.repo)["o1"][2] == 1


# --- Kết luận thật, đối soát (9–12) ----------------------------------------------------------------


def test_09_12_don_ngoai_khung_co_du_lieu_that_thi_doi_soat_va_bao_admin_mot_lan(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    notifier = _admin(bot.repo)
    coordinator, shopee = _seed(bot, {"old": timedelta(days=35)}, sub, notifier=notifier)  # lượt có notifier như production
    reconciliation.evaluate(bot.repo, NOW, admin_notifier=notifier)
    assert _tracking(bot.repo)["old"][0] == "OUTSIDE_WINDOW_UNVERIFIED"
    shopee.conversions = [_order("old", sub, purchase=_ts(NOW - timedelta(days=35)), fraud=True)]  # Shopee có kết luận
    coordinator.run("manual")
    reconciliation.evaluate(bot.repo, NOW, admin_notifier=notifier)
    assert _tracking(bot.repo)["old"][:2] == ("RECONCILED", "shopee_data")
    assert _events_count(bot.repo, "event_key = 'recon:old:RECONCILED'") == 1
    reconciliation.evaluate(bot.repo, NOW, admin_notifier=notifier)
    assert _events_count(bot.repo, "event_key = 'recon:old:RECONCILED'") == 1


def test_don_da_co_ket_luan_tu_dau_khong_vao_danh_sach(tmp_path):
    bot = _ready_bot(tmp_path)
    shopee = FakeShopee([_order("f", _link(bot), fraud=True)])
    _coord(bot.repo, shopee, cfg=AutoSyncConfig()).run("manual")
    reconciliation.evaluate(bot.repo, NOW)
    assert _tracking(bot.repo) == {}


# --- An toàn: tiền, tin khách, ví, payout, lịch (27–31) --------------------------------------------------


def test_27_31_chi_doi_nhan_khong_doi_tien_khong_tin_khach_khong_doi_lich(tmp_path):
    bot = _ready_bot(tmp_path, auto_sync=ON)
    sub = _link(bot)
    _seed(bot, {"x": timedelta(days=50)}, sub)
    bot.refresh_wallet(NOW)
    with bot.repo.connect() as conn:
        before = [tuple(r) for r in conn.execute(
            "SELECT conversion_id, validation_status, settlement_status, order_status, net_commission_vnd FROM shopee_conversions")]
        entries = [tuple(r) for r in conn.execute("SELECT conversion_id, status, cashback_vnd FROM cashback_entries")]
    customer_before = _events_count(bot.repo, "audience = 'customer'")
    clock = Clock()
    coordinator = _coord(bot.repo, FakeShopee(), cfg=ON, clock=clock)
    due = snapshot(bot.repo)["next_due_at"]
    reconciliation.evaluate(bot.repo, NOW, admin_notifier=_admin(bot.repo))
    with bot.repo.connect() as conn:
        after = [tuple(r) for r in conn.execute(
            "SELECT conversion_id, validation_status, settlement_status, order_status, net_commission_vnd FROM shopee_conversions")]
        entries_after = [tuple(r) for r in conn.execute("SELECT conversion_id, status, cashback_vnd FROM cashback_entries")]
        payouts = conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0]
    assert _tracking(bot.repo)["x"][0] == "RECONCILIATION_REQUIRED"
    assert after == before and entries_after == entries and payouts == 0
    assert all(status != "available" for _cid, status, _v in entries_after)
    assert _events_count(bot.repo, "audience = 'customer'") == customer_before, "không có tin khách"
    assert snapshot(bot.repo)["next_due_at"] == due and coordinator.cfg.interval_minutes == 120


def test_vi_va_payout_khong_doc_bang_theo_doi():
    root = Path(__file__).resolve().parents[1] / "cashback_bot"
    for name in ("wallet.py", "payouts.py", "payout_gate.py", "payout_readiness.py", "settlement.py"):
        path = root / name
        if path.exists():
            assert "conversion_reconciliation" not in path.read_text(encoding="utf-8"), name


def test_su_kien_theo_doi_chi_them(tmp_path):
    bot = _ready_bot(tmp_path)
    _seed(bot, {"x": timedelta(days=31)}, _link(bot))
    reconciliation.evaluate(bot.repo, NOW)
    with bot.repo.connect() as conn:
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("UPDATE conversion_reconciliation_events SET reason = 'x'")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM conversion_reconciliation_events")


# --- Cảnh báo admin (26), UTC / giờ VN (23) ----------------------------------------------------------


def test_26_23_tin_tong_hop_toi_da_moi_ngay_theo_gio_vn(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    notifier = _admin(bot.repo)
    _seed(bot, {"a": timedelta(days=21)}, sub)
    reconciliation.evaluate(bot.repo, NOW, admin_notifier=notifier)
    digests = lambda: _events_count(bot.repo, "event_type = 'RECON_DIGEST'")  # noqa: E731
    assert digests() == 1
    reconciliation.evaluate(bot.repo, NOW + timedelta(hours=2), admin_notifier=notifier)
    assert digests() == 1, "cùng danh sách: không gửi lại"
    reconciliation.evaluate(bot.repo, NOW + timedelta(days=10), admin_notifier=notifier)  # a ra khung: danh sách đổi
    assert digests() == 2
    with bot.repo.connect() as conn:
        key = conn.execute("SELECT event_key FROM admin_notifications WHERE event_type = 'RECON_DIGEST' ORDER BY id").fetchone()[0]
    assert key.startswith("recon_digest:2026-12-01:"), "ngày theo giờ VN"
    late = NOW.replace(hour=17, minute=30)  # 00:30 giờ VN ngày 02/12
    with bot.repo.connect() as conn:
        conn.execute("DELETE FROM bot_state WHERE key = ?", (reconciliation.DIGEST_KEY,))
    reconciliation.evaluate(bot.repo, late + timedelta(days=10), admin_notifier=notifier)
    with bot.repo.connect() as conn:
        last = conn.execute("SELECT event_key FROM admin_notifications WHERE event_type = 'RECON_DIGEST' ORDER BY id DESC").fetchone()[0]
    assert last.startswith("recon_digest:2026-12-12:")


def test_can_doi_soat_bao_rieng_mot_lan(tmp_path):
    bot = _ready_bot(tmp_path)
    notifier = _admin(bot.repo)
    _seed(bot, {"r": timedelta(days=46)}, _link(bot), notifier=notifier)
    for _ in range(3):
        reconciliation.evaluate(bot.repo, NOW, admin_notifier=notifier)
    assert _events_count(bot.repo, "event_key = 'recon:r:RECONCILIATION_REQUIRED'") == 1
    with bot.repo.connect() as conn:
        text = conn.execute("SELECT message_html FROM admin_notifications WHERE event_key = 'recon:r:RECONCILIATION_REQUIRED'").fetchone()[0]
    assert "không tự kết luận" in text and "từ chối" in text


# --- Dữ liệu cũ: last_seen (22) -----------------------------------------------------------------------


def test_22_last_seen_dong_cu_lay_tu_updated_at_co_danh_dau(tmp_path):
    bot = _ready_bot(tmp_path)
    _seed(bot, {"old": timedelta(days=3)}, _link(bot))
    with bot.repo.connect() as conn:
        seen = conn.execute("SELECT last_seen_at, last_seen_run_id, last_seen_source FROM shopee_conversions").fetchone()
        assert seen["last_seen_source"] == "report_list_30d" and seen["last_seen_run_id"] == 1
        conn.execute("UPDATE shopee_conversions SET last_seen_at = NULL, last_seen_run_id = NULL, last_seen_source = NULL, "
                     "updated_at = '2026-10-23T11:45:16Z'")
    bot.repo.migrate()
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT last_seen_at, last_seen_source FROM shopee_conversions").fetchone()
    assert tuple(row) == ("2026-10-23T11:45:16Z", "backfill_updated_at")


def test_ghi_tay_khong_phai_thay_trong_nguon(tmp_path):
    bot = _ready_bot(tmp_path)
    bot.repo.record_shopee_conversion("m1", None, "SN", "PENDING", "", "2026-10-21T09:00:00Z", 1000, 1000)
    with bot.repo.connect() as conn:
        row = conn.execute("SELECT last_seen_source FROM shopee_conversions WHERE conversion_id = 'm1'").fetchone()
    assert row[0] == "backfill_updated_at" or row[0] is None
    assert row[0] != "report_list_30d"


# --- Màn admin ------------------------------------------------------------------------------------------


def test_man_admin_don_can_doi_soat(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    _seed(bot, {"req": timedelta(days=50), "new": timedelta(days=2)}, sub)
    reconciliation.evaluate(bot.repo, NOW)
    screen = _callback(bot, ADMIN, "c:rc:home")
    assert "Đơn cần đối soát" in screen.text and "🔴 Cần đối soát" in screen.text and "lần cuối bot thấy" in screen.text
    assert "không tự kết luận Shopee đã duyệt, từ chối hay huỷ" in screen.text
    buttons = [d for row in screen.inline_keyboard for _l, d in row]
    assert buttons == ["c:sm:home", "c:menu:shopee"], "chỉ đọc, không có nút đổi trạng thái"
    assert "c:rc:home" in str(_callback(bot, ADMIN, "c:menu:shopee").inline_keyboard)
    assert "chỉ dành cho quản trị" in _callback(bot, USER, "c:rc:home").text
    assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:rc:x").text


def test_man_admin_trong(tmp_path):
    bot = _ready_bot(tmp_path)
    assert "Chưa có đơn qua bot nào đang chờ" in _callback(bot, ADMIN, "c:rc:home").text
