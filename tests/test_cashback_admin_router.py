"""PLAN-110: AdminRouter giữ đúng luật dọn trạng thái chờ và thứ tự xử lý chữ của AdminPanel cũ."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from cashback_bot import admin_policy, admin_ui
from cashback_bot.admin import panel as panel_module
from cashback_bot.admin.base import BaseAdminHandler
from cashback_bot.admin.router import AdminRouter
from cashback_bot.admin_policy import AdminPanel
from cashback_bot.messages import BotReply

ADMIN = 7
NOW = datetime(2026, 10, 31, 3, 0, tzinfo=timezone.utc)


def _panel(tmp_path) -> AdminPanel:
    return AdminPanel(str(tmp_path / "cb.sqlite"), frozenset({ADMIN}), 70)


def _fill(panel: AdminPanel) -> None:
    later = NOW + timedelta(minutes=5)
    panel._sim_waiting[ADMIN] = later
    panel._support_waiting[ADMIN] = ("reply", 1)
    panel._wallet_waiting[ADMIN] = ("mv", 1)
    panel._insights_waiting[ADMIN] = ("cost", later)
    panel._retention_waiting[ADMIN] = ("links", later)
    panel._cookie_parts[ADMIN] = ("SPC_EC=", NOW)


def _kept(panel: AdminPanel) -> set[str]:
    waits = {
        "sim": panel._sim_waiting, "support": panel._support_waiting, "wallet": panel._wallet_waiting,
        "insights": panel._insights_waiting, "retention": panel._retention_waiting, "cookie": panel._cookie_parts,
    }
    return {name for name, wait in waits.items() if ADMIN in wait}


@pytest.mark.parametrize(("data", "kept"), [
    ("c:menu:home", set()),
    ("c:shopee:auth", {"cookie"}),
    ("c:sim:input", {"sim"}),
    ("c:sim:50000", set()),
    ("c:hp:home", {"support"}),
    ("c:wl:mv:3", {"wallet"}),
    ("c:wl:vb:3", {"wallet"}),
    ("c:wl:list", set()),
    ("c:menu:wallet", set()),
    ("c:in:cost", {"insights"}),
    ("c:in:f", {"insights"}),
    ("c:in:t:links", {"insights"}),
    ("c:in:m:30d", set()),
    ("c:rt:e:links", {"retention"}),
    ("c:rt:home", set()),
])
def test_bam_nut_chi_giu_trang_thai_cho_dung_luat_cu(tmp_path, data, kept):
    panel = _panel(tmp_path)
    _fill(panel)
    panel._router.clear_states(ADMIN, data)
    assert _kept(panel) == kept


def test_thu_tu_hoi_chu_giu_nhu_truoc(tmp_path):
    names = [handler.name for handler in _panel(tmp_path)._router.handlers]
    assert names[:7] == ["shopee", "simulation", "support", "wallet", "retention", "insights", "policy"]


def test_cho_mo_phong_va_cho_ho_tro_thi_mo_phong_nhan_chu_truoc(tmp_path):
    panel = _panel(tmp_path)
    panel._sim_waiting[ADMIN] = NOW + timedelta(minutes=5)
    panel._support_waiting[ADMIN] = ("reply", 1)
    reply = panel.consume_text(ADMIN, "150k", NOW)
    assert reply is not None and "150.000" in reply.text
    assert ADMIN not in panel._sim_waiting and ADMIN in panel._support_waiting


def test_nut_la_van_bao_het_hieu_luc(tmp_path):
    panel = _panel(tmp_path)
    for data in ("c:zz:1", "c:sim:7", "c:shopee:x", "c:st:year", "c:rs:bad", "c:menu:nope"):
        reply = panel.handle_callback(ADMIN, data, "private", NOW)
        assert reply.text == "Nút này không còn hiệu lực.", data


class _Fake(BaseAdminHandler):
    def __init__(self, name, prefixes=(), exact=()):
        self.name, self.callback_prefixes, self.callback_exact = name, prefixes, exact

    def route(self, user_id, data, now):
        return BotReply(self.name)


def test_dang_ky_trung_callback_thi_bao_loi():
    router = AdminRouter()
    router.register(_Fake("a", prefixes=("c:in:",)))
    with pytest.raises(ValueError):
        router.register(_Fake("b", exact=("c:in:f",)))
    router.register(_Fake("c", exact=("c:menu:wallet",)))
    assert router.dispatch_callback(ADMIN, "c:menu:wallet", NOW).text == "c"
    assert router.dispatch_callback(ADMIN, "c:menu:walletx", NOW) is None


def test_replace_dung_lai_router_tro_panel_moi(tmp_path):
    panel = _panel(tmp_path)
    other = replace(panel, tiktok_configured=True)
    assert other._router is not panel._router
    assert other._router.handlers[0].panel is other
    # Trạng thái chờ (RAM) vẫn dùng chung như trước khi có router.
    assert other._sim_waiting is panel._sim_waiting


def test_ten_cu_van_import_duoc():
    assert admin_policy is panel_module
    assert admin_policy.SIM_AMOUNTS == (10_000, 50_000, 100_000, 500_000)
    assert admin_policy.parse_sim_amount("1,5tr") == 1_500_000
    assert admin_ui.MENU_KEYBOARD and admin_ui.payout_text and admin_ui.GLOSSARY
