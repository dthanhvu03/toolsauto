"""PLAN-064: lưu thêm dữ liệu sản phẩm AddLiveTag và đưa vào thống kê."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from cashback_bot.admin_stats import _insight, collect
from cashback_bot.product_data import quote_from_payload
from tests.test_cashback_bot import FakeClient, payload, repo, service

NOW = datetime(2026, 10, 21, 8, 8, tzinfo=timezone.utc)
EXTRA = {
    "catName": "Quần dài",
    "shopName": "Mộc Studio.",
    "sellerComFinal": "12450",
    "shopeeComFinal": "17430",
    "totalRatePercent": "12",
    "isXtra": "True",
    "isCapped": "False",
}


def test_doc_truong_them_tu_payload():
    quote = quote_from_payload(payload(**EXTRA), NOW, 3)
    assert quote.category == "Quần dài"
    assert quote.shop_name == "Mộc Studio."
    assert (quote.seller_commission_vnd, quote.shopee_commission_vnd) == (12_450, 17_430)
    assert quote.commission_rate_bps == 1_200
    assert (quote.is_xtra, quote.is_capped) == (True, False)


def test_truong_them_thieu_hay_sai_van_bao_gia():
    garbled = {
        "catName": "None",
        "shopName": "",
        "sellerComFinal": "abc",
        "totalRatePercent": "nhiều",
        "isXtra": "maybe",
    }
    quote = quote_from_payload(payload(**garbled), NOW, 3)
    assert quote.commission_vnd == 20_000
    assert quote.category is None and quote.shop_name is None
    assert quote.seller_commission_vnd is None and quote.commission_rate_bps is None
    assert quote.is_xtra is None and quote.is_capped is None
    plain = quote_from_payload(payload(), NOW, 3)
    assert plain.category is None


def test_link_moi_luu_truong_them(tmp_path):
    bot = service(tmp_path, FakeClient(payload(**EXTRA)))
    reply = bot.handle_text(111, "buyer", "https://shopee.vn/product/9/8", update_id=1, now=NOW)
    assert "Hoàn dự kiến" in reply.text
    row = sqlite3.connect(tmp_path / "cashback.sqlite").execute(
        """
        SELECT cat_name, shop_name, seller_commission_vnd, shopee_commission_vnd,
               commission_rate_bps, is_xtra, is_capped
        FROM link_requests
        """
    ).fetchone()
    assert row == ("Quần dài", "Mộc Studio.", 12_450, 17_430, 1_200, 1, 0)


def test_thong_ke_hoa_hong_theo_nguon(tmp_path):
    store = repo(tmp_path)
    with store.connect() as conn:
        conn.execute(
            "INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at) "
            "VALUES (1, 'an', '2026-10-01T00:00:00Z', '2026-10-01T00:00:00Z')"
        )
        rows = [
            ("Quần dài", "Mộc", 12_000, 18_000, 1_200, 1, 0),
            ("Quần dài", "Mộc", 6_000, 4_000, 800, 0, 1),
            ("Mực in", "HP", None, 9_000, 1_000, 1, 0),
            (None, None, None, None, None, None, None),  # link cũ chưa có dữ liệu
        ]
        for index, (cat, shop, seller, shopee, rate, xtra, capped) in enumerate(rows):
            conn.execute(
                """
                INSERT INTO link_requests (
                    telegram_user_id, original_url, link_status, created_at, item_id, product_name,
                    estimated_commission, estimated_cashback, cat_name, shop_name,
                    seller_commission_vnd, shopee_commission_vnd, commission_rate_bps, is_xtra, is_capped
                ) VALUES (1, 'u', 'created', '2026-10-21T07:00:00Z', ?, 'x', 10000, 7000, ?, ?, ?, ?, ?, ?, ?)
                """,
                (index, cat, shop, seller, shopee, rate, xtra, capped),
            )
        stats = collect(conn, "today", NOW)
    insight = stats.insight
    assert insight.detailed == 3
    assert (insight.seller_commission_vnd, insight.shopee_commission_vnd) == (18_000, 31_000)
    assert insight.avg_rate_bps == 1_000
    assert (insight.xtra, insight.capped) == (2, 1)
    assert insight.top_categories == [("Quần dài", 2), ("Mực in", 1)]
    assert insight.top_shops == [("Mộc", 2), ("HP", 1)]

    from cashback_bot.admin_policy import AdminPanel

    panel = AdminPanel(str(tmp_path / "cashback.sqlite"), frozenset({7}), 70)
    text = panel.handle_callback(7, "c:st:today:more", "private", NOW).text
    assert "Hoa hồng theo nguồn</b> · 3/4 link có dữ liệu" in text
    assert "Người bán: <b>18.000đ</b> · Shopee/Xtra: <b>31.000đ</b>" in text
    assert "Tỷ lệ trung bình: <b>10%</b> · Xtra: 2 link · Chạm trần: 1 link" in text
    assert "Ngành hỏi nhiều: Quần dài (2), Mực in (1)" in text
    assert len(text) < 3500


def test_chua_co_link_co_du_lieu(tmp_path):
    repo(tmp_path)
    from cashback_bot.admin_policy import AdminPanel

    panel = AdminPanel(str(tmp_path / "cashback.sqlite"), frozenset({7}), 70)
    text = panel.handle_callback(7, "c:st:7d:more", "private", NOW).text
    assert "0/0 link có dữ liệu" in text
    assert "Link tạo từ bản này trở đi" in text


def test_db_cu_chua_co_cot_thi_an_muc(tmp_path):
    conn = sqlite3.connect(tmp_path / "old.sqlite")
    conn.execute("CREATE TABLE link_requests (id INTEGER PRIMARY KEY, link_status TEXT, created_at TEXT)")
    assert _insight(conn, "") is None
