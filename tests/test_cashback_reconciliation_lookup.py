"""PLAN-081 Phương án A: tra lại đơn qua bot đang chờ đã ra khung 30 ngày bằng khung hẹp quanh giờ mua.

Shopee giả lọc đúng theo purchase_time_s/e như endpoint thật (đã thử nguồn 2026-10-24: đơn 30,9 ngày vẫn trả về).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cashback_bot import reconciliation
from cashback_bot.config import AutoSyncConfig
from cashback_bot.shopee_client import ACCESS_DENIED, ShopeeApiError
from cashback_bot.sync_scheduler import snapshot
from tests.test_cashback_auto_sync import Clock, FakeShopee, _admin, _coord, _order, _ready_bot
from tests.test_cashback_wallet import ADMIN, _callback, _link

REAL = datetime.now(timezone.utc).replace(microsecond=0)
LOOKUP = AutoSyncConfig(reconcile_lookup=True, reconcile_lookup_max=10)


class WindowShopee(FakeShopee):
    """Lọc đơn theo khung giờ mua; ghi lại từng khung được hỏi."""

    def __init__(self, *args, filtered: bool = True, **kwargs):
        super().__init__(*args, **kwargs)
        self.filtered = filtered
        self.windows: list[tuple[int, int]] = []

    def fetch_conversions(self, start_time, end_time, page_no=1, page_size=100):
        self.windows.append((start_time, end_time))
        rows = self.conversions
        if self.filtered:
            rows = [r for r in rows if start_time <= r["purchase_time"] <= end_time]
        return self._page("conv", rows, page_no, page_size)


def _ts(moment: datetime) -> int:
    return int(moment.timestamp())


def _narrow(shopee: WindowShopee) -> list[tuple[int, int]]:
    return [w for w in shopee.windows if w[1] - w[0] <= 120]


def _setup(tmp_path, ages: dict[str, int], notifier=None):
    """Đơn qua bot có giờ mua REAL − tuổi (ngày); ghi một lần (Shopee giả không lọc), rồi đánh giá theo giờ thật."""
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    orders = {cid: _order(cid, sub, purchase=_ts(REAL - timedelta(days=age))) for cid, age in ages.items()}
    _coord(bot.repo, WindowShopee(list(orders.values()), filtered=False), cfg=AutoSyncConfig(), clock=Clock(REAL)).run("manual")
    reconciliation.evaluate(bot.repo, REAL, admin_notifier=notifier)
    return bot, sub, orders


def _row(bot, cid):
    with bot.repo.connect() as conn:
        return conn.execute(
            "SELECT r.tracking_status, r.reason, r.last_attempt_result, c.last_seen_source FROM conversion_reconciliation r "
            "JOIN shopee_conversions c ON c.conversion_id = r.conversion_id WHERE r.conversion_id = ?", (cid,)
        ).fetchone()


def test_tat_co_thi_khong_tra_them(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"old": 35})
    shopee = WindowShopee(list(orders.values()))
    _coord(bot.repo, shopee, cfg=AutoSyncConfig(), clock=Clock(REAL)).run("manual")
    assert _narrow(shopee) == [] and _row(bot, "old")[0] == "OUTSIDE_WINDOW_UNVERIFIED"


def test_bat_co_tra_khung_hep_dung_don_va_van_quan_sat_duoc(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"old": 35})
    assert _row(bot, "old")[0] == "OUTSIDE_WINDOW_UNVERIFIED"
    customer_before = _count(bot, "audience = 'customer'")
    shopee = WindowShopee(list(orders.values()))
    result = _coord(bot.repo, shopee, cfg=LOOKUP, clock=Clock(REAL)).run("manual")
    purchase = orders["old"]["purchase_time"]
    assert _narrow(shopee) == [(purchase - 60, purchase + 60)]
    assert result.status == "success"
    assert tuple(_row(bot, "old")) == ("OBSERVED_RECENTLY", "seen_outside_window", "seen", "report_list_narrow")
    assert _count(bot, "audience = 'customer'") == customer_before, "dữ liệu không đổi: không có tin khách"


def test_moi_don_toi_da_mot_lan_moi_ngay(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"old": 35})
    shopee = WindowShopee(list(orders.values()))
    clock = Clock(REAL)
    coordinator = _coord(bot.repo, shopee, cfg=LOOKUP, clock=clock)
    coordinator.run("manual")
    coordinator.run("manual")
    assert len(_narrow(shopee)) == 1
    clock.advance(days=1)
    coordinator.run("manual")
    assert len(_narrow(shopee)) == 2


def test_tra_ra_ket_luan_that_thi_doi_soat_qua_luong_cu(tmp_path):
    notifier_bot, sub, orders = _setup(tmp_path, {"old": 35})
    notifier = _admin(notifier_bot.repo)
    fraud = _order("old", sub, purchase=orders["old"]["purchase_time"], fraud=True)
    shopee = WindowShopee([fraud])
    _coord(notifier_bot.repo, shopee, cfg=LOOKUP, clock=Clock(REAL), notifier=notifier).run("manual")
    assert _row(notifier_bot, "old")[:2] == ("RECONCILED", "shopee_data")
    assert _count(notifier_bot, "event_key = 'recon:old:RECONCILED'") == 1
    updates = _count(notifier_bot, "audience = 'customer' AND category = 'order_update'")
    assert updates == 1, "tin cập nhật cho khách đi qua đúng luồng PLAN-079, một lần"
    with notifier_bot.repo.connect() as conn:
        assert conn.execute("SELECT validation_status FROM shopee_conversions WHERE conversion_id = 'old'").fetchone()[0] == "FRAUD"


def test_shopee_khong_tra_thi_ghi_lan_tra_khong_doi_gi(tmp_path):
    bot, _sub, _orders = _setup(tmp_path, {"old": 35})
    shopee = WindowShopee([])
    _coord(bot.repo, shopee, cfg=LOOKUP, clock=Clock(REAL)).run("manual")
    assert len(_narrow(shopee)) == 1
    assert tuple(_row(bot, "old")) == ("OUTSIDE_WINDOW_UNVERIFIED", "outside_30d_window", "not_returned", "report_list_30d")


def test_tran_so_don_moi_luot(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"a": 31, "b": 33, "c": 40})
    shopee = WindowShopee(list(orders.values()))
    coordinator = _coord(bot.repo, shopee, cfg=AutoSyncConfig(reconcile_lookup=True, reconcile_lookup_max=2), clock=Clock(REAL))
    coordinator.run("manual")
    assert len(_narrow(shopee)) == 2
    coordinator.run("manual")
    assert len(_narrow(shopee)) == 3, "lượt sau tra nốt đơn còn lại, không tra lại đơn đã tra hôm nay"


def test_loi_phien_khi_tra_dung_luot_va_ghi_lan_tra(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"old": 35})
    shopee = WindowShopee(list(orders.values()))
    original = shopee.fetch_conversions

    def denied(start_time, end_time, page_no=1, page_size=100):
        if end_time - start_time <= 120:
            raise ShopeeApiError("HTTP 403", 403, category=ACCESS_DENIED)
        return original(start_time, end_time, page_no, page_size)

    shopee.fetch_conversions = denied
    result = _coord(bot.repo, shopee, cfg=LOOKUP, clock=Clock(REAL)).run("manual")
    assert result.category == ACCESS_DENIED and snapshot(bot.repo)["needs_auth_since"]
    assert _row(bot, "old")[2] == "error:ACCESS_DENIED"


def test_don_trong_khung_va_qua_180_ngay_khong_tra(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"new": 10, "ancient": 200})
    shopee = WindowShopee(list(orders.values()))
    _coord(bot.repo, shopee, cfg=LOOKUP, clock=Clock(REAL)).run("manual")
    assert _narrow(shopee) == []
    assert reconciliation.lookup_targets(bot.repo, REAL, 10) == []


def test_tra_lai_khong_doi_tien_khong_tao_available(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"old": 35})
    bot.refresh_wallet(REAL)
    with bot.repo.connect() as conn:
        before = [tuple(r) for r in conn.execute("SELECT conversion_id, status, cashback_vnd FROM cashback_entries")]
    _coord(bot.repo, WindowShopee(list(orders.values())), cfg=LOOKUP, clock=Clock(REAL)).run("manual")
    bot.refresh_wallet(REAL)
    with bot.repo.connect() as conn:
        after = [tuple(r) for r in conn.execute("SELECT conversion_id, status, cashback_vnd FROM cashback_entries")]
        payouts = conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0]
    assert after == before and payouts == 0 and all(status != "available" for _c, status, _v in after)


def test_man_admin_hien_lan_tra(tmp_path):
    bot, _sub, orders = _setup(tmp_path, {"old": 35})
    _coord(bot.repo, WindowShopee([]), cfg=LOOKUP, clock=Clock(REAL)).run("manual")
    text = _callback(bot, ADMIN, "c:rc:home").text
    assert "lần tra Shopee gần nhất" in text and "Shopee không trả đơn này" in text


def _count(bot, where: str) -> int:
    with bot.repo.connect() as conn:
        return conn.execute(f"SELECT COUNT(*) FROM admin_notifications WHERE {where}").fetchone()[0]
