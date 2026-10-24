"""PLAN-080: tự đồng bộ Shopee theo lịch, khoá một lượt, lỗi Shopee, phân trang, tích hợp thông báo PLAN-079.

Shopee, Telegram và đồng hồ đều giả lập; không gọi Shopee thật.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import requests

from cashback_bot import shopee_sync
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.config import AutoSyncConfig
from cashback_bot.order_notify import BASELINE_KEY
from cashback_bot.poller import _acquire_single_process_lock
from cashback_bot.shopee_client import (
    ACCESS_DENIED,
    AUTH_EXPIRED,
    CHALLENGE,
    NETWORK_ERROR,
    NETWORK_TIMEOUT,
    PARSE_ERROR,
    RATE_LIMITED,
    TRANSIENT_SERVER_ERROR,
    ShopeeAffiliateClient,
    ShopeeApiError,
    ShopeeStatusResult,
)
from cashback_bot.shopee_sync import SYNC_REQUEST_KEY, ShopeeSyncEngine, SyncResult
from cashback_bot.sync_scheduler import FIRST_RUN_DELAY, SyncCoordinator, busy, derived_status, request_manual, snapshot
from tests.test_cashback_bot import NOW as QUOTE_NOW
from tests.test_cashback_order_notifications import OTHER, _events, _link_for
from tests.test_cashback_wallet import ADMIN, USER, _bot, _buttons, _callback, _link

T0 = datetime(2026, 10, 25, 2, 0, tzinfo=timezone.utc)
ON = AutoSyncConfig(enabled=True, interval_minutes=120, max_runtime_seconds=600, failure_threshold=3)
PURCHASE = int(datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc).timestamp())


class Clock:
    def __init__(self, moment: datetime = T0):
        self.moment = moment

    def __call__(self) -> datetime:
        return self.moment

    def advance(self, **delta) -> None:
        self.moment += timedelta(**delta)


def _status(ok: bool = True, auth_failed: bool = False, category=None, error: str = "") -> ShopeeStatusResult:
    return ShopeeStatusResult(ok=ok, status_code=200, username="ID 1", error_message=error, auth_failed=auth_failed,
                              category=category)


def _order(cid: str, sub: str | None, status: str = "PENDING", commission: int = 10_000, purchase: int = PURCHASE,
           fraud: bool = False) -> dict:
    return {
        "checkout_id": f"chk_{cid}", "purchase_time": purchase, "utm_content": f"{sub or ''}----",
        "estimated_total_commission": commission * 100_000, "affiliate_net_commission": str(commission * 100_000),
        "orders": [{"order_id": cid, "order_sn": f"SN{cid}", "order_status": status, "items": [
            {"is_fraud": 1 if fraud else 0, "fraud_reason": "", "item_name": "Áo", "actual_amount": 25_000_000_000, "qty": 1},
        ]}],
    }


class FakeShopee:
    """Phân trang thật theo page_no / page_size; lỗi theo trang; đếm số lần gọi."""

    def __init__(self, conversions=(), status: ShopeeStatusResult | None = None, errors=None, payloads=None):
        self.conversions = list(conversions)
        self.status = status or _status()
        self.errors = dict(errors or {})  # ("conv" | "click", page_no) -> exception (một lần)
        self.payloads = dict(payloads or {})  # ("conv", page_no) -> payload thô
        self.calls: list[tuple[str, int]] = []
        self.gate: threading.Event | None = None
        self.entered = threading.Event()

    def check_status(self):
        self.calls.append(("status", 0))
        return self.status

    def _page(self, kind, rows, page_no, page_size):
        self.calls.append((kind, page_no))
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(5)
        if (kind, page_no) in self.errors:
            raise self.errors.pop((kind, page_no))
        if (kind, page_no) in self.payloads:
            return self.payloads[(kind, page_no)]
        start = (page_no - 1) * page_size
        return {"code": 0, "data": {"list": rows[start:start + page_size]}}

    def fetch_clicks(self, start_time, end_time, page_no=1, page_size=100):
        return self._page("click", [], page_no, page_size)

    def fetch_conversions(self, start_time, end_time, page_no=1, page_size=100):
        return self._page("conv", self.conversions, page_no, page_size)


def _no_sleep(_seconds):
    return None


class _Engine(ShopeeSyncEngine):
    """Engine thật, không ngủ khi thử lại trang (test nhanh)."""

    def sync(self, **kwargs):
        kwargs.setdefault("sleep", _no_sleep)
        return super().sync(**kwargs)


def _coord(repo, shopee: FakeShopee | None = None, cfg=ON, clock=None, notifier=None, owner=None):
    shopee = shopee or FakeShopee()
    coordinator = SyncCoordinator(repo, notifier, cfg, engine_factory=_Engine, clock=clock or Clock(),
                                  owner=owner, client_factory=lambda: shopee)
    coordinator.start()
    return coordinator


def _ready_bot(tmp_path, **overrides):
    overrides.setdefault("allowed_telegram_ids", frozenset({USER, OTHER}))
    bot = _bot(tmp_path, customer_notifications_enabled=True, **overrides)
    bot.repo.set_state(BASELINE_KEY, "2026-10-01T00:00:00Z")
    bot.repo.update_shopee_cookie_status(status="connected")
    return bot


def _runs(repo):
    with repo.connect() as conn:
        return conn.execute("SELECT * FROM shopee_sync_runs ORDER BY id").fetchall()


def _admin(repo):
    return AdminNotifier(repo, MagicMock(), enabled=True, chat_id=ADMIN)


def _alerts(repo):
    with repo.connect() as conn:
        return [r["event_key"] for r in conn.execute(
            "SELECT event_key FROM admin_notifications WHERE event_type = 'SYNC_INCIDENT' ORDER BY id")]


def _due(coordinator):
    return snapshot(coordinator.repo)["next_due_at"]


# --- Lịch (1–13) ------------------------------------------------------------------------------------


def test_01_tat_thi_khong_chay_va_khong_goi_shopee(tmp_path):
    bot = _ready_bot(tmp_path)
    shopee = FakeShopee()
    coordinator = _coord(bot.repo, shopee, cfg=AutoSyncConfig())
    clock = coordinator.clock
    for _ in range(5):
        clock.advance(hours=3)
        assert coordinator.next_job() is None
    assert shopee.calls == [] and _runs(bot.repo) == []
    assert derived_status(snapshot(bot.repo), AutoSyncConfig(), clock()) == "DISABLED"


def test_02_03_08_bat_thi_lan_dau_sau_5_phut_roi_moi_chu_ky(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock)
    assert _due(coordinator) == (T0 + FIRST_RUN_DELAY).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert coordinator.next_job() is None, "chưa tới giờ"
    clock.advance(minutes=5)
    assert coordinator.next_job() == "auto"
    result = coordinator.run("auto")
    assert result.status == "success" and _runs(bot.repo)[-1]["trigger_type"] == "auto"
    clock.advance(minutes=119)
    assert coordinator.next_job() is None
    clock.advance(minutes=1)
    assert coordinator.next_job() == "auto"


def test_04_11_restart_khong_chay_lai_luot_vua_xong(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock)
    clock.advance(minutes=5)
    coordinator.run("auto")
    restarted = _coord(bot.repo, clock=clock)  # cùng cấu hình
    assert restarted.next_job() is None
    clock.advance(hours=2)
    assert restarted.next_job() == "auto", "tiếp tục đúng lịch sau restart"


def test_05_06_bot_tat_lau_chi_chay_bu_mot_luot(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    shopee = FakeShopee()
    coordinator = _coord(bot.repo, shopee, clock=clock)
    clock.advance(days=3)  # bỏ lỡ hàng chục chu kỳ
    ran = 0
    while coordinator.next_job() == "auto":
        coordinator.run("auto")
        ran += 1
        assert ran < 5
    assert ran == 1
    assert _due(coordinator) == (clock() + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_07_doi_chu_ky_tinh_lai_tu_lan_xong_gan_nhat(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock)
    clock.advance(minutes=5)
    coordinator.run("auto")
    finished = clock()
    longer = _coord(bot.repo, cfg=AutoSyncConfig(enabled=True, interval_minutes=240), clock=clock)
    assert _due(longer) == (finished + timedelta(minutes=240)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_09_bat_sang_tat(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    _coord(bot.repo, clock=clock)
    off = _coord(bot.repo, cfg=AutoSyncConfig(), clock=clock)
    clock.advance(hours=5)
    assert off.next_job() is None and _due(off) is None
    request_manual(bot.repo)
    assert off.next_job() == "manual", "đồng bộ tay vẫn chạy khi tự đồng bộ tắt"


def test_10_bot_dung_giua_luot_restart_ghi_bi_ngat_va_nha_khoa(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock, owner="otherhost:1:x")
    owner, run_id, _ = coordinator._acquire("auto", clock())  # tiến trình cũ đang chạy thì chết
    assert busy(bot.repo, clock()) == (run_id, "auto")
    clock.advance(minutes=11)  # quá max_runtime: khoá hết hạn
    _coord(bot.repo, clock=clock)
    assert busy(bot.repo, clock()) is None
    assert (_runs(bot.repo)[-1]["status"], _runs(bot.repo)[-1]["error_category"]) == ("interrupted", "INTERRUPTED")


def test_10b_khoa_cua_tien_trinh_da_chet_cung_may_thu_hoi_ngay(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock)
    with bot.repo.connect() as conn:
        dead = f"{os.uname().nodename}:999999:dead"
        conn.execute("UPDATE shopee_sync_state SET lease_owner = ?, lease_run_id = 0, lease_expires_at = ? WHERE id = 1",
                     (dead, (clock() + timedelta(minutes=9)).strftime("%Y-%m-%dT%H:%M:%SZ")))
    coordinator.start()
    assert busy(bot.repo, clock()) is None


def test_12_luu_gio_utc(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock(datetime(2026, 10, 25, 23, 30, tzinfo=timezone.utc))
    coordinator = _coord(bot.repo, clock=clock)
    assert _due(coordinator) == "2026-10-25T23:35:00Z"


def test_13_dong_bo_khong_chan_luong_chinh(tmp_path):
    bot = _ready_bot(tmp_path)
    shopee = FakeShopee([_order("o1", None)])
    shopee.gate = threading.Event()
    coordinator = _coord(bot.repo, shopee)
    worker = threading.Thread(target=coordinator.run, args=("manual",))
    worker.start()
    assert shopee.entered.wait(5)
    # Shopee đang «treo»: khách vẫn tạo link và xem /donhang ngay.
    assert bot.handle_text(USER, "u", "https://shopee.vn/product/9/8", update_id=4001, now=QUOTE_NOW).text
    assert bot.handle_text(USER, "u", "/donhang", update_id=4002, now=QUOTE_NOW).text
    shopee.gate.set()
    worker.join(5)
    assert not worker.is_alive()


# --- Khoá một lượt (14–20) --------------------------------------------------------------------------


def test_14_bam_tay_khi_tu_dong_dang_chay(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock, notifier=_admin(bot.repo))
    owner, run_id, _ = coordinator._acquire("auto", clock())
    assert request_manual(bot.repo, clock()) == (run_id, "auto")
    assert bot.repo.get_state(SYNC_REQUEST_KEY) != "1", "không xếp lượt thứ hai"
    reply = _callback(bot, ADMIN, "c:shopee:sync")
    assert f"Mã lượt: #{run_id}" in reply.text and "đang được đồng bộ tự động" in reply.text
    bot.repo.set_state(SYNC_REQUEST_KEY, "1")  # lỡ có cờ (bấm sát lúc lượt bắt đầu)
    assert coordinator.run("manual") is None
    assert len(_runs(bot.repo)) == 1
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_key = ?",
                            (f"sync_busy:{run_id}",)).fetchone()[0] == 1


def test_15_luot_qua_thoi_gian_toi_da_dung_lai(tmp_path, monkeypatch):
    monkeypatch.setattr(shopee_sync, "PAGE_SIZE", 1)
    bot = _ready_bot(tmp_path)
    clock = Clock()
    shopee = FakeShopee([_order(f"o{i}", None) for i in range(5)])
    coordinator = _coord(bot.repo, shopee, clock=clock)
    original = shopee.fetch_conversions

    def slow(**kwargs):
        clock.advance(minutes=6)
        return original(**kwargs)

    shopee.fetch_conversions = slow
    result = coordinator.run("auto")
    assert result.category == "LEASE_LOST"
    assert busy(bot.repo, clock()) is None and _runs(bot.repo)[-1]["status"] == "failed"
    assert len([c for c in shopee.calls if c[0] == "conv"]) < 5, "không đọc tiếp sau khi quá giờ"


def test_16_engine_loi_khong_lam_ket_khoa(tmp_path):
    bot = _ready_bot(tmp_path)
    engine = MagicMock()
    engine.return_value.sync.side_effect = RuntimeError("boom")
    coordinator = SyncCoordinator(bot.repo, None, ON, engine_factory=engine, clock=Clock())
    coordinator.start()
    result = coordinator.run("manual")
    assert result.status == "failed" and busy(bot.repo) is None
    assert _runs(bot.repo)[-1]["status"] == "failed"


def test_17_18_khoa_het_han_luot_cu_khong_ghi_de_luot_moi(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    old = _coord(bot.repo, clock=clock, owner="otherhost:1:old")
    old_owner, old_run, _ = old._acquire("auto", clock())
    clock.advance(minutes=11)
    new = _coord(bot.repo, clock=clock, owner="otherhost:2:new")
    new_owner, new_run, _ = new._acquire("manual", clock())
    assert new_run != old_run and _runs(bot.repo)[0]["status"] == "interrupted"
    assert old._heartbeat(old_owner, old_run) is False
    late = SyncResult(ok=True, message="xong muộn", status="success", run_id=old_run)
    assert old._finish(old_owner, old_run, "auto", late) is False
    assert busy(bot.repo, clock()) == (new_run, "manual"), "khoá vẫn của lượt mới"
    assert _runs(bot.repo)[0]["status"] == "interrupted"


def test_19_hai_tien_trinh_bot(tmp_path):
    path = str(tmp_path / "bot.lock")
    first = _acquire_single_process_lock(path)
    assert first is not None and _acquire_single_process_lock(path) is None


def test_20_hai_luot_cung_luc_chi_mot_lan_goi_shopee(tmp_path):
    bot = _ready_bot(tmp_path)
    shopee = FakeShopee()
    shopee.gate = threading.Event()
    coordinator = _coord(bot.repo, shopee)
    threads = [threading.Thread(target=coordinator.run, args=(trigger,)) for trigger in ("auto", "manual")]
    threads[0].start()
    assert shopee.entered.wait(5)
    threads[1].start()
    threads[1].join(5)
    shopee.gate.set()
    threads[0].join(5)
    assert shopee.calls.count(("status", 0)) == 1 and len(_runs(bot.repo)) == 1


# --- Shopee: dữ liệu, phân trang (21–36) ------------------------------------------------------------


def test_21_22_52_55_khong_doi_khong_bao_don_moi_bao_mot_lan(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([_order("o1", sub)])
    coordinator = _coord(bot.repo, shopee)
    for _ in range(10):
        coordinator.run("auto")
    events = _events(bot)
    assert [(e["event_key"], e["chat_id"]) for e in events] == [("conversion:o1:first_matched", USER)]
    run = _runs(bot.repo)[-1]
    assert (run["conversions_new"], run["conversions_unchanged"], run["notifications_queued"]) == (0, 1, 0)
    assert _runs(bot.repo)[0]["conversions_new"] == 1


def test_23_don_ve_muon_van_bao(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([])
    coordinator = _coord(bot.repo, shopee)
    coordinator.run("auto")
    shopee.conversions = [_order("late", sub, purchase=PURCHASE)]  # mua hôm trước, hôm nay Shopee mới báo
    coordinator.run("auto")
    assert [e["event_key"] for e in _events(bot)] == ["conversion:late:first_matched"]


def test_24_to_29_thay_doi_cua_don_cu(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([_order("o1", sub, status="UNPAID", commission=10_000)])
    coordinator = _coord(bot.repo, shopee)
    coordinator.run("auto")
    steps = [
        _order("o1", sub, status="PAID", commission=10_000),          # đổi PAID
        _order("o1", sub, status="COMPLETED", commission=10_000),     # COMPLETED
        _order("o1", sub, status="COMPLETED", commission=12_000),     # tăng ≥ 10%
        _order("o1", sub, status="COMPLETED", commission=8_000),      # giảm
        _order("o1", sub, status="COMPLETED", commission=8_100),      # dưới ngưỡng: không báo
        _order("o1", sub, status="COMPLETED", commission=0),          # về 0
    ]
    for step in steps:
        shopee.conversions = [step]
        coordinator.run("auto")
    texts = [e["message_html"] for e in _events(bot)][1:]
    assert len(texts) == 5
    assert "đã thanh toán" in texts[0] and "hoàn thành" in texts[1]
    assert "→ <b>8.400đ</b>" in texts[2] and "→ <b>5.600đ</b>" in texts[3] and "→ <b>0đ</b>" in texts[4]


def test_28_29_huy_va_gian_lan(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([_order("a", sub), _order("b", sub)])
    coordinator = _coord(bot.repo, shopee)
    coordinator.run("auto")
    shopee.conversions = [_order("a", sub, status="CANCELLED"), _order("b", sub, fraud=True)]
    coordinator.run("auto")
    updates = [e for e in _events(bot) if e["category"] == "order_update"]
    assert len(updates) == 2 and all("không đủ điều kiện" in e["message_html"].lower() or "huỷ" in e["message_html"]
                                     for e in updates)
    assert all("gian lận" not in e["message_html"] for e in updates)


def test_30_31_khong_sub_id_va_sub_id_la(tmp_path):
    bot = _ready_bot(tmp_path)
    _link(bot)
    coordinator = _coord(bot.repo, FakeShopee([_order("x1", None), _order("x2", "NOTOURS1")]))
    assert coordinator.run("auto").status == "success"
    assert _events(bot) == []


def test_32_nhieu_trang(tmp_path, monkeypatch):
    monkeypatch.setattr(shopee_sync, "PAGE_SIZE", 2)
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    coordinator = _coord(bot.repo, FakeShopee([_order(f"p{i}", sub) for i in range(5)]))
    result = coordinator.run("auto")
    assert result.status == "success" and result.conversions_synced == 5
    run = _runs(bot.repo)[-1]
    assert run["pages_fetched"] == 4 and run["conversions_new"] == 5  # 1 trang click + 3 trang đơn


def test_33_34_36_mot_trang_loi_thanh_partial_giu_phan_da_ghi(tmp_path, monkeypatch):
    monkeypatch.setattr(shopee_sync, "PAGE_SIZE", 2)
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    orders = [_order(f"p{i}", sub) for i in range(5)]
    shopee = FakeShopee(orders)
    coordinator = _coord(bot.repo, shopee)
    coordinator.run("auto")
    error = ShopeeApiError("Shopee HTTP 400", status_code=400)
    shopee.errors[("conv", 2)] = error
    result = coordinator.run("auto")
    assert result.status == "partial" and result.ok is False
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM shopee_conversions").fetchone()[0] == 5, "không xoá đơn vắng mặt"
    run = _runs(bot.repo)[-1]
    assert (run["status"], run["pages_failed"]) == ("partial", 1)
    state = snapshot(bot.repo)
    assert state["last_result"] == "partial" and state["consecutive_failures"] == 1
    assert state["last_success_window_end"] == _runs(bot.repo)[0]["window_end"], "chỉ lượt đủ mới là kỳ thành công"


def test_35_cau_truc_doi_thi_partial_va_bao_admin(tmp_path):
    bot = _ready_bot(tmp_path)
    shopee = FakeShopee(payloads={("conv", 1): {"code": 0, "items": []}})
    coordinator = _coord(bot.repo, shopee, notifier=_admin(bot.repo))
    result = coordinator.run("auto")
    assert (result.status, result.category) == ("partial", PARSE_ERROR)
    assert _alerts(bot.repo) == ["sync_incident:1:open"]


def test_lap_trang_va_cham_tran_so_trang(tmp_path, monkeypatch):
    monkeypatch.setattr(shopee_sync, "PAGE_SIZE", 1)
    monkeypatch.setattr(shopee_sync, "MAX_PAGES", 2)
    bot = _ready_bot(tmp_path)
    coordinator = _coord(bot.repo, FakeShopee([_order(f"p{i}", None) for i in range(3)]))
    result = coordinator.run("auto")
    assert result.status == "partial" and any(p.startswith("TRUNCATED") for p in result.stats["problems"])
    same = {"code": 0, "data": {"list": [_order("z", None)]}}
    shopee = FakeShopee(payloads={("conv", 1): same, ("conv", 2): same})
    assert _coord(bot.repo, shopee).run("manual").stats["problems"] == ["PAGINATION_ANOMALY:page2"]


# --- Cookie, lỗi (37–49) -----------------------------------------------------------------------------


def test_37_38_47_cookie_het_han_dung_tu_dong_bao_mot_lan(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    shopee = FakeShopee(status=_status(False, auth_failed=True, category=AUTH_EXPIRED, error="HTTP 401"))
    coordinator = _coord(bot.repo, shopee, clock=clock, notifier=_admin(bot.repo))
    clock.advance(minutes=5)
    result = coordinator.run("auto")
    assert result.category == AUTH_EXPIRED
    state = snapshot(bot.repo)
    assert state["needs_auth_since"] and state["next_due_at"] is None
    assert derived_status(state, ON, clock()) == "NEEDS_AUTH"
    assert bot.repo.get_shopee_cookie_status()["status"] == "expired"
    for _ in range(10):
        clock.advance(hours=2)
        assert coordinator.next_job() is None, "không gọi lại Shopee khi phiên hỏng"
    assert _alerts(bot.repo) == ["sync_incident:1:open"]
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE event_type = 'COOKIE_EXPIRED'").fetchone()[0] == 0


def test_48_ket_noi_lai_cookie_thi_chay_lai_va_bao_phuc_hoi(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    shopee = FakeShopee(status=_status(False, auth_failed=True, category=AUTH_EXPIRED))
    coordinator = _coord(bot.repo, shopee, clock=clock, notifier=_admin(bot.repo))
    coordinator.run("auto")
    clock.advance(minutes=30)
    with bot.repo.connect() as conn:  # admin dán cookie mới (như _shopee_auth_finish)
        conn.execute("UPDATE shopee_cookies SET status = 'connected', updated_at = ? WHERE id = 1",
                     ((clock() + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
    shopee.status = _status()
    assert coordinator.next_job() == "auto"
    assert coordinator.run("auto").status == "success"
    assert _alerts(bot.repo) == ["sync_incident:1:open", "sync_incident:1:resolved"]
    assert derived_status(snapshot(bot.repo), ON, clock()) == "SCHEDULED"


def test_39_40_403_va_xac_minh_khong_danh_dau_cookie_het_han(tmp_path):
    bot = _ready_bot(tmp_path)
    for category in (ACCESS_DENIED, CHALLENGE):
        shopee = FakeShopee([_order("o1", None)], errors={("click", 1): ShopeeApiError("Shopee HTTP 403", 403, category=category)})
        result = _coord(bot.repo, shopee).run("manual")
        assert result.category == category and snapshot(bot.repo)["needs_auth_since"]
        assert bot.repo.get_shopee_cookie_status()["status"] == "connected"
        assert ("conv", 1) not in shopee.calls, "dừng ngay, không gọi tiếp"


def test_41_429_lui_lich_theo_retry_after(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    shopee = FakeShopee(errors={("click", 1): ShopeeApiError("HTTP 429", 429, category=RATE_LIMITED, retry_after=7200)})
    coordinator = _coord(bot.repo, shopee, clock=clock)
    result = coordinator.run("auto")
    assert result.category == RATE_LIMITED and ("conv", 1) not in shopee.calls
    assert _due(coordinator) == (clock() + timedelta(seconds=7200)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_42_43_44_loi_tam_thu_lai_trong_luot(tmp_path):
    bot = _ready_bot(tmp_path)
    for category in (TRANSIENT_SERVER_ERROR, NETWORK_TIMEOUT, NETWORK_ERROR):
        shopee = FakeShopee(errors={("conv", 1): ShopeeApiError("tạm", 503, category=category)})
        assert _coord(bot.repo, shopee).run("manual").status == "success", "thử lại trang thành công"
        assert shopee.calls.count(("conv", 1)) == 2


def test_45_46_47_gian_cach_nguong_loi_va_nhac_lai(tmp_path):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    shopee = FakeShopee()
    shopee.check_status = lambda: _status(False, category=TRANSIENT_SERVER_ERROR, error="HTTP 502")
    coordinator = _coord(bot.repo, shopee, clock=clock, notifier=_admin(bot.repo))
    gaps = []
    for _ in range(4):
        coordinator.run("auto")
        due = datetime.strptime(_due(coordinator), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        gaps.append(int((due - clock()).total_seconds() // 60))
        clock.moment = due
    assert gaps == [15, 30, 60, 120], "giãn cách, không quá một chu kỳ"
    assert derived_status(snapshot(bot.repo), ON, clock()) == "FAILED"
    assert _alerts(bot.repo) == ["sync_incident:1:open"], "báo khi tới ngưỡng 3, một lần"
    clock.advance(hours=25)
    coordinator.run("auto")
    assert _alerts(bot.repo) == ["sync_incident:1:open", "sync_incident:1:remind:2"]


def test_49_khong_lo_cookie(tmp_path, monkeypatch, caplog):
    bot = _ready_bot(tmp_path)
    secret = "SPC_EC=bi_mat_cookie_123"
    client = ShopeeAffiliateClient({"SPC_EC": "bi_mat_cookie_123"})
    response = MagicMock(status_code=401, text="", headers={})
    monkeypatch.setattr(requests, "get", lambda *a, **k: response)
    coordinator = SyncCoordinator(bot.repo, _admin(bot.repo), ON, engine_factory=_Engine, clock=Clock(),
                                  client_factory=lambda: client)
    coordinator.start()
    coordinator.run("auto")
    with bot.repo.connect() as conn:
        dump = json.dumps([list(r) for t in ("shopee_sync_runs", "shopee_sync_state", "shopee_sync_incidents",
                                             "admin_notifications") for r in conn.execute(f"SELECT * FROM {t}")])
    assert "bi_mat_cookie_123" not in dump and "bi_mat_cookie_123" not in caplog.text and secret not in dump


def test_phan_loai_loi_http():
    from cashback_bot.shopee_client import classify_exception, classify_http

    def resp(code, text="", headers=None):
        return MagicMock(status_code=code, text=text, headers=headers or {})

    assert classify_http(resp(401)) == AUTH_EXPIRED
    assert classify_http(resp(403)) == ACCESS_DENIED
    assert classify_http(resp(403, "<html>Please verify captcha</html>")) == CHALLENGE
    assert classify_http(resp(429)) == RATE_LIMITED
    assert classify_http(resp(502)) == TRANSIENT_SERVER_ERROR
    assert classify_http(resp(200)) is None
    assert classify_exception(requests.Timeout()) == NETWORK_TIMEOUT
    assert classify_exception(requests.ConnectionError()) == NETWORK_ERROR


def test_client_429_doc_retry_after(monkeypatch):
    client = ShopeeAffiliateClient({"a": "b"})
    monkeypatch.setattr(requests, "get", lambda *a, **k: MagicMock(status_code=429, text="", headers={"Retry-After": "90"}))
    try:
        client.fetch_conversions(0, 1)
    except ShopeeApiError as exc:
        assert (exc.category, exc.retry_after) == (RATE_LIMITED, 90)
    else:
        raise AssertionError("phải ném lỗi")


# --- Thông báo khách (50–64) --------------------------------------------------------------------------


def test_51_53_54_link_chia_se_tay_roi_tu_dong_khong_trung(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    other = _link_for(bot, OTHER)
    shopee = FakeShopee([_order("o1", sub), _order("o2", other)])
    coordinator = _coord(bot.repo, shopee)
    coordinator.run("manual")
    coordinator.run("auto")
    coordinator.run("manual")
    events = _events(bot)
    assert sorted((e["event_key"], e["chat_id"]) for e in events) == [
        ("conversion:o1:first_matched", USER), ("conversion:o2:first_matched", OTHER)]


def test_57_khach_tat_thong_bao(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    _callback(bot, USER, "u:n:t:orders")
    _coord(bot.repo, FakeShopee([_order("o1", sub)])).run("auto")
    assert (_events(bot)[0]["status"], _events(bot)[0]["last_error"]) == ("suppressed", "pref_off")


def test_62_lap_lich_khong_doi_moc_plan079(tmp_path):
    bot = _ready_bot(tmp_path)
    before = bot.repo.get_state(BASELINE_KEY)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock)
    clock.advance(minutes=5)
    coordinator.run("auto")
    _coord(bot.repo, cfg=AutoSyncConfig(), clock=clock)
    assert bot.repo.get_state(BASELINE_KEY) == before


def test_khong_co_tin_khach_tu_bo_lap_lich_khi_khong_co_don(tmp_path):
    bot = _ready_bot(tmp_path)
    _coord(bot.repo, FakeShopee()).run("auto")
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM admin_notifications WHERE audience = 'customer'").fetchone()[0] == 0


# --- An toàn tài chính (65–71) ------------------------------------------------------------------------


def test_65_71_dong_bo_tu_dong_khong_tao_tien_rut_duoc(tmp_path):
    bot = _ready_bot(tmp_path)
    sub = _link(bot)
    shopee = FakeShopee([_order("o1", sub, status="COMPLETED")])
    coordinator = _coord(bot.repo, shopee)
    coordinator.run("auto")
    bot.refresh_wallet(datetime(2026, 12, 30, tzinfo=timezone.utc))
    coordinator.run("auto")
    with bot.repo.connect() as conn:
        statuses = {r[0] for r in conn.execute("SELECT status FROM cashback_entries")}
        validation = {tuple(r) for r in conn.execute("SELECT validation_status, settlement_status FROM shopee_conversions")}
        payouts = conn.execute("SELECT COUNT(*) FROM cashback_payouts").fetchone()[0]
        triggers = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")}
    assert "available" not in statuses and payouts == 0
    assert all(v != "APPROVED" and s != "SETTLED" for v, s in validation)
    assert {"financial_lock_entry_insert", "financial_lock_entry_update", "financial_lock_payout_insert",
            "financial_lock_payout_paid", "financial_lock_payout_progress", "payout_paid_needs_evidence"} <= triggers


# --- Màn admin ----------------------------------------------------------------------------------------


def test_man_admin_chua_co_luot_tat_va_lich_su(tmp_path):
    bot = _ready_bot(tmp_path)
    home = _callback(bot, ADMIN, "c:sy:home")
    assert "TẮT" in home.text and "Chưa có lượt chạy." in home.text and "c:shopee:auto:off" not in _buttons(home)
    _coord(bot.repo, FakeShopee([_order("o1", None)]), cfg=AutoSyncConfig()).run("manual")
    home = _callback(bot, ADMIN, "c:sy:home")
    assert "Lần chạy gần nhất: #1" in home.text and "thủ công" in home.text and "Lượt tự động: chưa có lượt chạy" in home.text
    hist = _callback(bot, ADMIN, "c:sy:hist")
    assert "#1" in hist.text and "1 đơn · 1 mới" in hist.text
    assert "không còn hiệu lực" in _callback(bot, ADMIN, "c:sy:xyz").text
    assert "chỉ dành cho quản trị" in _callback(bot, USER, "c:sy:home").text


def test_man_admin_bat_tam_dung_co_audit(tmp_path):
    bot = _ready_bot(tmp_path, auto_sync=ON)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock)
    home = _callback(bot, ADMIN, "c:sy:home")
    assert "BẬT" in home.text and "Chu kỳ: 120 phút" in home.text and "c:shopee:auto:off" in _buttons(home)
    _callback(bot, ADMIN, "c:shopee:auto:off")
    clock.advance(hours=5)
    assert coordinator.next_job() is None and snapshot(bot.repo)["paused"] == 1
    assert "TẠM DỪNG" in _callback(bot, ADMIN, "c:sy:home").text
    request_manual(bot.repo)
    assert coordinator.next_job() == "manual", "tạm dừng không chặn đồng bộ tay"
