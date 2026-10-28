"""PLAN-098 bước A: đối soát chéo đơn Shopee với API AddLiveTag. Chỉ đọc, không ghi sổ đơn."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
import requests

from cashback_bot import addlivetag_orders as alt
from cashback_bot.admin_ui import shopee_text
from tests.test_cashback_wallet import _bot, _link, _order

NOW = datetime(2026, 10, 28, 3, 0, tzinfo=timezone.utc)  # 10:00 28/10 giờ VN
BOUGHT = int(datetime(2026, 10, 21, 9, 0, tzinfo=timezone.utc).timestamp())  # như PURCHASE của _order


def _row(order_sn, sub_id, commission=10_000, status="completed", bought=BOUGHT, mcn=0):
    return {"order_sn": order_sn, "utm": f"{sub_id}----", "sub_id1": sub_id, "commission": commission,
            "mcn_fee": mcn, "status_code": status, "status": "Hoàn thành", "purchase_time": bought}


class FakeClient:
    def __init__(self, rows=None, error=None):
        self.rows, self.error, self.calls = rows or [], error, 0

    def fetch_items(self, start, end):
        self.calls += 1
        if self.error:
            raise alt.AltError(self.error)
        return self.rows


def _seed(tmp_path):
    bot = _bot(tmp_path)
    sub = _link(bot)
    for cid, status in (("o1", "COMPLETED"), ("o2", "COMPLETED"), ("o3", "COMPLETED"), ("o4", "PENDING")):
        _order(bot, sub, status=status, cid=cid)
    return bot, sub


def test_doi_soat_khop_lech_va_thieu(tmp_path):
    bot, sub = _seed(tmp_path)
    fresh = int(NOW.timestamp()) - 3600
    rows = [
        _row("SN-o1", sub, 6_000) | {"item_id": 1}, _row("SN-o1", sub, 4_500, mcn=500),  # 2 món, trừ phí MCN → khớp
        _row("SN-o2", sub, 8_000),  # lệch hoa hồng
        _row("SN-o3", sub, 0, status="cancelled"),  # lệch huỷ
        _row("SN-new", sub),  # bot chưa có
        _row("SN-fresh", sub, bought=fresh),  # mới mua 1 giờ: chưa báo
        _row("SN-other", "99999999"),  # không phải link bot
    ]
    result = alt.run(bot.repo, FakeClient(rows), NOW)
    assert (result.compared, result.matched) == (3, 1)
    assert result.commission_mismatch == ["SN-o2: bot 10.000đ · AddLiveTag 8.000đ"]
    assert result.cancel_mismatch == ["SN-o3"] and result.missing_in_bot == ["SN-new"]
    assert result.alt_lagging == 1, "SN-o4 bot có, AddLiveTag chưa có, mua đã quá 3 ngày"
    text = alt.report_text(result)
    assert "lệch 3 đơn" in text and "<code>SN-new</code>" in text and "Khớp 1/3" in text
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM shopee_conversions").fetchone()[0] == 4, "không ghi sổ đơn"


def test_lech_nho_duoi_nguong_van_khop(tmp_path):
    bot, sub = _seed(tmp_path)
    rows = [_row("SN-o1", sub, 10_099), _row("SN-o2", sub, 9_900), _row("SN-o3", sub, 10_001)]
    result = alt.run(bot.repo, FakeClient(rows), NOW)
    assert result.matched == 3 and result.problems == 0, "lệch dưới 100đ không báo"


def test_moi_ngay_mot_lan_tu_9_gio_va_bao_admin_khi_lech(tmp_path):
    bot, sub = _seed(tmp_path)
    notifier = MagicMock()
    client = FakeClient([_row("SN-o2", sub, 1_000)])
    early = datetime(2026, 10, 28, 1, 0, tzinfo=timezone.utc)  # 08:00 giờ VN
    assert alt.maybe_start(bot.repo, client, notifier, now=early) is None
    alt.maybe_start(bot.repo, client, notifier, now=NOW).join(5)
    assert alt.maybe_start(bot.repo, client, notifier, now=NOW) is None and client.calls == 1
    day, body = notifier.notify_alt_crosscheck.call_args.args
    assert day == "2026-10-28" and "Lệch hoa hồng" in body
    line = alt.status_line(bot.repo)
    assert line.startswith("🔁 Đối soát AddLiveTag 28/10: khớp 0/1 · ⚠️ lệch 1")


def test_khong_lech_thi_khong_nhan_admin(tmp_path):
    bot, sub = _seed(tmp_path)
    notifier = MagicMock()
    rows = [_row(f"SN-o{i}", sub) for i in (1, 2, 3)]
    alt.maybe_start(bot.repo, FakeClient(rows), notifier, now=NOW).join(5)
    notifier.notify_alt_crosscheck.assert_not_called()
    assert alt.status_line(bot.repo) == "🔁 Đối soát AddLiveTag 28/10: khớp 3/3 · AddLiveTag chưa có 1 đơn"


def test_loi_api_chi_ghi_trang_thai(tmp_path):
    bot, _sub = _seed(tmp_path)
    notifier = MagicMock()
    alt.maybe_start(bot.repo, FakeClient(error="auth"), notifier, now=NOW).join(5)
    notifier.notify_alt_crosscheck.assert_not_called()
    assert "chưa đọc được (auth)" in alt.status_line(bot.repo)
    assert json.loads(bot.repo.get_state(alt.RESULT_KEY))["error"] == "auth"


def _response(status=200, payload=None):
    response = MagicMock(status_code=status)
    response.json.return_value = payload
    return response


def test_client_di_het_trang_va_map_loi(monkeypatch):
    pages = [{"ok": True, "meta": {"total": 3}, "data": [{"order_sn": "a"}, {"order_sn": "b"}]},
             {"ok": True, "meta": {"total": 3}, "data": [{"order_sn": "c"}]}]
    calls = []

    def fake_get(url, params, headers, timeout):
        calls.append(params)
        assert headers == {"X-API-Key": "k"} and params["type"] == "items" and params["source"] == "shopee"
        return _response(payload=pages[params["page"] - 1])

    monkeypatch.setattr(alt.requests, "get", fake_get)
    client = alt.AltOrdersClient("k", sleep=lambda _s: None)
    assert [r["order_sn"] for r in client.fetch_items(NOW, NOW)] == ["a", "b", "c"] and len(calls) == 2
    for status, kind in ((401, "auth"), (429, "rate_limited"), (500, "http_error")):
        monkeypatch.setattr(alt.requests, "get", lambda *a, status=status, **k: _response(status))
        with pytest.raises(alt.AltError) as caught:
            client.fetch_items(NOW, NOW)
        assert caught.value.kind == kind
    monkeypatch.setattr(alt.requests, "get", lambda *a, **k: _response(payload={"ok": False}))
    with pytest.raises(alt.AltError, match="not_ok"):
        client.fetch_items(NOW, NOW)

    def timeout(*a, **k):
        raise requests.Timeout()

    monkeypatch.setattr(alt.requests, "get", timeout)
    with pytest.raises(alt.AltError, match="timeout"):
        client.fetch_items(NOW, NOW)


def test_man_shopee_affiliate_co_dong_doi_soat():
    text = shopee_text(status="connected", account_name="a", last_sync="x", total_clicks=0, total_orders=0,
                       matched_orders=0, crosscheck="🔁 Đối soát AddLiveTag 28/10: khớp 3/3")
    assert "• 🔁 Đối soát AddLiveTag 28/10: khớp 3/3" in text
