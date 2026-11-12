"""PLAN-169: kéo khách sang món hoàn cao. C — thẻ link món có XTRA nhắc mua đúng món, đúng shop. Không gọi mạng."""

from __future__ import annotations

from datetime import timedelta

from cashback_bot import deals, upsell
from cashback_bot.admin.handlers.deals import DealsAdmin, history_line
from cashback_bot.messages import XTRA_HINT, render_success
from tests.test_cashback_bot import FakeClient, payload, service
from tests.test_cashback_insight import EXTRA, NOW

LINK = "https://shopee.vn/product/9/8"


def test_the_mon_xtra_co_dong_nhac_dung_mon(tmp_path):
    bot = service(tmp_path, FakeClient(payload(**EXTRA)))
    card = bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW).text
    lines = card.split("\n")
    assert XTRA_HINT in lines and lines.index(XTRA_HINT) > lines.index(next(x for x in lines if "Hoàn dự kiến" in x))


def test_dong_hang_sat_so_hoan_va_noi_ro_da_gom():
    """Chủ bot 12/11: dòng hạng phải sát số hoàn, ghi «đã gồm» để khách không cộng hai số."""
    from cashback_bot.messages import rank_card_line
    rank = rank_card_line("GOLD", 2_151, 0)
    assert "đã gồm" in rank and "cộng thêm" not in rank
    lines = render_success("Áo", 179_000, 15_057, "https://shopee.vn/x", rank_line=rank, xtra=True).text.split("\n")
    assert lines[3] == rank and lines[4] == XTRA_HINT


def test_mon_khong_xtra_giu_the_cu(tmp_path):
    bot = service(tmp_path, FakeClient(payload(**{**EXTRA, "sellerComFinal": "0", "isXtra": "False"})))
    assert XTRA_HINT not in bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW).text
    plain = service(tmp_path / "b", FakeClient(payload()))
    assert XTRA_HINT not in plain.handle_text(111, "buyer", LINK, update_id=2, now=NOW).text, "thiếu dữ liệu tách"


def test_khong_hoan_thi_khong_nhac():
    assert not upsell.shows_xtra_note(12_000, 0)
    assert XTRA_HINT not in render_success("Son", 1, 0, "https://shopee.vn/x", xtra=True).text


def test_admin_tat_bat_nhac_dung_mon(tmp_path):
    bot = service(tmp_path, FakeClient(payload(**EXTRA)))
    admin = DealsAdmin(bot.repo)
    page = admin.route(7, "c:dl:xn:off", NOW)
    assert "Đã tắt nhắc mùa" not in page.text and "Đã tắt nhắc mua đúng món." in page.text
    assert ("📌 Bật nhắc đúng món", "c:dl:xn:on") in [b for row in page.inline_keyboard for b in row]
    assert XTRA_HINT not in bot.handle_text(111, "buyer", LINK, update_id=1, now=NOW).text
    admin.route(7, "c:dl:xn:on", NOW)
    assert XTRA_HINT in bot.handle_text(111, "buyer", LINK, update_id=2, now=NOW + timedelta(seconds=1)).text
    assert history_line({}, {"xtra_note": False}).endswith("tắt")


# --- B: deal xếp theo tổng tiết kiệm -------------------------------------------------------------------------------

def _deal(item_id: int, price: int, cashback: int) -> dict:
    return dict(item_id=item_id, shop_id=9, name=f"Món {item_id}", price=price, usual=250_000, lowest_30d=True,
                cashback=cashback, rating=4.8, sold_30d=500, cat="dep")


def test_deal_xep_theo_tong_tiet_kiem_va_nhan_hoan_cao():
    cheap, rich = _deal(1, 200_000, 2_000), _deal(2, 205_000, 15_000)  # rẻ hơn 5k nhưng hoàn ít hơn 13k
    assert sorted([cheap, rich], key=lambda d: upsell.deal_rank(d, True)) == [rich, cheap]
    assert sorted([cheap, rich], key=lambda d: upsell.deal_rank(d, False)) == [cheap, rich], "tắt: như cũ"
    assert upsell.high_cashback(rich) and not upsell.high_cashback(cheap)
    text, _kb = deals.feed_message({"dep": [cheap, rich]}, [], None, by_saving=True)
    assert text.index("Món 2") < text.index("Món 1") and text.count(upsell.HIGH_BADGE) == 1
    old, _kb = deals.feed_message({"dep": [cheap, rich]}, [], None)
    assert upsell.HIGH_BADGE not in old
    built, _kb = deals.message_for(["dep"], {"dep": [rich]}, set(), badge=True)
    assert upsell.HIGH_BADGE in built


def test_kho_deal_va_cong_tac_admin(tmp_path):
    bot = service(tmp_path, FakeClient(payload()))
    seen = deals._stamp(NOW)
    deals._save(bot.repo, deals.POOL_KEY, {str(d["item_id"]): {**d, "seen": seen}
                                          for d in (_deal(1, 200_000, 2_000), _deal(2, 205_000, 15_000))})
    assert [d["item_id"] for d in deals.current_deals(bot.repo, NOW)[0]["dep"]] == [2, 1]
    page = DealsAdmin(bot.repo).route(7, "c:dl:sv:off", NOW)
    assert "theo % rẻ hơn như cũ" in page.text
    assert [d["item_id"] for d in deals.current_deals(bot.repo, NOW)[0]["dep"]] == [1, 2]
    assert history_line({}, {"saving_rank": True}).endswith("bật")
