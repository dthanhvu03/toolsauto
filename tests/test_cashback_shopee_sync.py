"""Unit tests for PLAN-065: Shopee Affiliate Cookie Sync & Attribution."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.admin_policy import AdminPanel
from cashback_bot.admin_stats import collect
from cashback_bot.db import TrackingRepository
from cashback_bot.shopee_client import (
    ShopeeAffiliateClient,
    ShopeeApiError,
    ShopeeStatusResult,
)
from cashback_bot.shopee_cookie import (
    cookies_to_header,
    load_cookies,
    parse_cookies,
    save_cookies,
)
from cashback_bot.shopee_sync import BotOrder, ShopeeSyncEngine, parse_shopee_money_vnd

ADMIN_ID = 9999
USER_ID = 1234
NOW = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)


def _setup_repo(tmp_path: Path) -> TrackingRepository:
    db_file = tmp_path / "cashback.sqlite"
    repo = TrackingRepository(str(db_file))
    repo.migrate()
    return repo


def _insert_link(repo: TrackingRepository, sub_id: str, update_id: int = 1) -> None:
    with repo.connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO telegram_users (telegram_user_id, username, created_at, last_seen_at) "
            "VALUES (?, 'khach_hang', '2026-10-23T08:00:00Z', '2026-10-23T08:00:00Z')",
            (USER_ID,),
        )
        conn.execute(
            """
            INSERT INTO link_requests (
                telegram_update_id, telegram_user_id, original_url, sub_id, affiliate_url,
                item_id, product_name, price_vnd, estimated_commission,
                estimated_cashback, cashback_rate_percent, link_status, created_at
            ) VALUES (?, ?, 'https://shopee.vn/product/111', ?, 'https://shope.ee/xxx', 111, 'Sản phẩm thử',
                      100000, 10000, 7000, 70, 'created', '2026-10-23T08:00:00Z')
            """,
            (update_id, USER_ID, sub_id),
        )


def _status(ok: bool, auth_failed: bool = False, error: str = "") -> ShopeeStatusResult:
    return ShopeeStatusResult(ok=ok, status_code=200, username="shop_owner", error_message=error, auth_failed=auth_failed)


class TestShopeeCookie:
    def test_parse_j2team_json_array(self):
        raw = json.dumps([
            {"domain": ".shopee.vn", "name": "SPC_EC", "value": "sec_token_123"},
            {"domain": ".shopee.vn", "name": "SPC_F", "value": "fp_456"},
        ])
        cookies = parse_cookies(raw)
        assert cookies["SPC_EC"] == "sec_token_123"
        assert cookies["SPC_F"] == "fp_456"

    def test_parse_json_dict_with_cookies_key(self):
        raw = json.dumps({
            "cookies": [
                {"name": "SPC_U", "value": "user_789"},
                {"name": "shopee_token", "value": "tok_abc"},
            ]
        })
        cookies = parse_cookies(raw)
        assert cookies["SPC_U"] == "user_789"
        assert cookies["shopee_token"] == "tok_abc"

    def test_parse_header_string(self):
        raw = "SPC_EC=sec_token_123; SPC_F=fp_456; SPC_U=user_789"
        cookies = parse_cookies(raw)
        assert cookies["SPC_EC"] == "sec_token_123"
        assert cookies["SPC_F"] == "fp_456"
        assert cookies["SPC_U"] == "user_789"

    def test_parse_empty_or_invalid_raises_value_error(self):
        with pytest.raises(ValueError):
            parse_cookies("")
        with pytest.raises(ValueError):
            parse_cookies("   ")
        with pytest.raises(ValueError):
            parse_cookies("not-a-cookie")

    def test_save_and_load_cookies_with_chmod_0600(self, tmp_path):
        target = tmp_path / "shopee_cookies.json"
        data = {"SPC_EC": "secret123", "SPC_F": "fp999"}
        saved_path = save_cookies(data, target)
        assert saved_path.exists()

        # Check chmod 0600 on POSIX
        mode = stat.S_IMODE(os.stat(saved_path).st_mode)
        assert mode == 0o600

        loaded = load_cookies(target)
        assert loaded == data

    def test_cookies_to_header(self):
        data = {"A": "1", "B": "2"}
        header = cookies_to_header(data)
        assert "A=1" in header
        assert "B=2" in header


class TestShopeeClient:
    @patch("requests.get")
    def test_check_status_success(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"code": 0, "data": {"allow_to_login": True, "username": "affiliate_boss"}}
        mock_get.return_value = mock_resp

        client = ShopeeAffiliateClient({"SPC_EC": "valid"})
        res = client.check_status()
        assert res.ok is True
        assert res.allow_to_login is True
        assert res.username == "affiliate_boss"

    @patch("requests.get")
    def test_check_status_expired(self, mock_get):
        mock_resp = MagicMock(status_code=401)
        mock_get.return_value = mock_resp

        client = ShopeeAffiliateClient({"SPC_EC": "expired"})
        res = client.check_status()
        assert res.ok is False
        assert "Cookie hết hạn" in res.error_message

    @patch("requests.get")
    def test_check_status_not_allowed(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"code": 0, "data": {"allow_to_login": False}}
        mock_get.return_value = mock_resp

        client = ShopeeAffiliateClient({"SPC_EC": "frozen"})
        res = client.check_status()
        assert res.ok is False
        assert "không được phép đăng nhập" in res.error_message

    @patch("requests.get")
    def test_fetch_clicks_success(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"code": 0, "data": {"list": [{"sub_id": "ABC12345", "click_time": "2026-10-23T08:00:00Z"}]}}
        mock_get.return_value = mock_resp

        client = ShopeeAffiliateClient({"SPC_EC": "valid"})
        payload = client.fetch_clicks(0, 100)
        assert len(payload["data"]["list"]) == 1

    @patch("requests.get")
    def test_fetch_conversions_expired_raises(self, mock_get):
        mock_resp = MagicMock(status_code=401)
        mock_get.return_value = mock_resp

        client = ShopeeAffiliateClient({"SPC_EC": "expired"})
        with pytest.raises(ShopeeApiError) as exc:
            client.fetch_conversions(0, 100)
        assert "Cookie hết hạn" in str(exc.value)


class TestShopeeSyncAndReconciliation:
    def test_parse_shopee_money_vnd(self):
        # Luôn chia 100.000; response thật: item_price 39.900.000.000 = 399.000 đ
        assert parse_shopee_money_vnd(39_900_000_000) == 399_000
        assert parse_shopee_money_vnd(451_000_000) == 4_510
        assert parse_shopee_money_vnd("451000000") == 4_510
        # Số nhỏ cũng chia, không đoán theo ngưỡng
        assert parse_shopee_money_vnd(50_000_000) == 500
        assert parse_shopee_money_vnd("0") == 0
        assert parse_shopee_money_vnd(None) is None

    def test_sync_matches_sub_id_and_notifies_admin(self, tmp_path):
        repo = _setup_repo(tmp_path)
        # Tạo link request với sub_id = G3lkg1JK cho user 1234
        with repo.connect() as conn:
            conn.execute(
                "INSERT INTO telegram_users (telegram_user_id, username, created_at, last_seen_at) VALUES (?, 'khach_hang', '2026-10-23T08:00:00Z', '2026-10-23T08:00:00Z')",
                (USER_ID,),
            )
            conn.execute(
                """
                INSERT INTO link_requests (
                    telegram_update_id, telegram_user_id, original_url, sub_id, affiliate_url,
                    item_id, product_name, price_vnd, estimated_commission,
                    estimated_cashback, cashback_rate_percent, link_status, created_at
                ) VALUES (1, ?, 'https://shopee.vn/product/111', 'G3lkg1JK', 'https://shope.ee/xxx', 111, 'Sản phẩm thử', 100000, 10000, 7000, 70, 'created', '2026-10-23T08:00:00Z')
                """,
                (USER_ID,),
            )

        admin_notifier = MagicMock()
        engine = ShopeeSyncEngine(repo, admin_notifier=admin_notifier)

        # Mock client
        mock_client = MagicMock()
        mock_client.check_status.return_value = MagicMock(ok=True, username="shop_owner", error_message="")
        mock_client.fetch_clicks.return_value = {
            "code": 0,
            "data": {
                "list": [
                    {"sub_id": "G3lkg1JK", "click_time": "2026-10-23T08:30:00Z", "click_id": "clk_1"},
                    {"sub_id": "----", "click_time": "2026-10-23T08:31:00Z", "click_id": "clk_2"},
                ]
            },
        }
        mock_client.fetch_conversions.return_value = {
            "code": 0,
            "data": {
                "list": [
                    {
                        # Cấu trúc theo response thật: hoa hồng và utm_content ở cấp checkout.
                        "checkout_id": "chk_999",
                        "purchase_time": 1792742400,
                        "utm_content": "G3lkg1JK----",
                        "gross_commission": 500_000_000,  # 5,000 VND
                        "affiliate_net_commission": "450000000",  # 4,500 VND, Shopee trả chuỗi
                        "orders": [
                            {
                                "order_id": "ord_1001",
                                "order_sn": "261023ABC123",
                                "order_status": "COMPLETED",
                            }
                        ],
                    }
                ]
            },
        }

        res = engine.sync(trigger="manual", client=mock_client)
        assert res.ok is True
        assert res.clicks_synced == 2
        assert res.conversions_synced == 1
        assert res.new_matched_orders == 1

        # Check notification was triggered for admin
        admin_notifier.notify_shopee_new_order.assert_called_once()
        args = admin_notifier.notify_shopee_new_order.call_args[1]
        assert args["order_sn"] == "261023ABC123"
        assert args["sub_id"] == "G3lkg1JK"
        assert args["telegram_user_id"] == USER_ID
        assert args["username"] == "khach_hang"
        assert args["commission_vnd"] == 4_500
        assert args["order_status"] == "COMPLETED"
        assert args["conversion_id"]

        # Check DB records
        with repo.connect() as conn:
            conv = conn.execute("SELECT * FROM shopee_conversions WHERE sub_id = 'G3lkg1JK'").fetchone()
            assert conv is not None
            assert conv["telegram_user_id"] == USER_ID
            assert conv["net_commission_vnd"] == 4_500

            run = conn.execute("SELECT * FROM shopee_sync_runs WHERE id = 1").fetchone()
            assert run["status"] == "success"
            assert run["clicks_synced"] == 2
            assert run["conversions_synced"] == 1
            assert run["new_orders_count"] == 1


class TestShopeeAdminUIAndCookieWorkflow:
    def test_admin_menu_has_shopee_button(self, tmp_path):
        repo = _setup_repo(tmp_path)
        panel = AdminPanel(str(repo.path), frozenset({ADMIN_ID}), displayed_rate_percent=70)
        home = panel.menu(ADMIN_ID, NOW)
        assert home.inline_keyboard is not None
        button_targets = [data for row in home.inline_keyboard for _label, data in row]
        assert "c:menu:shopee" in button_targets

    def test_shopee_screen_render_disconnected_and_connected(self, tmp_path):
        repo = _setup_repo(tmp_path)
        panel = AdminPanel(str(repo.path), frozenset({ADMIN_ID}), displayed_rate_percent=70)

        # 1. Ban đầu: Chưa kết nối
        reply = panel.handle_callback(ADMIN_ID, "c:menu:shopee", "private", NOW)
        assert "CHƯA KẾT NỐI" in reply.text
        assert "🔑 Kết nối Cookie" in [label for row in reply.inline_keyboard for label, _data in row]
        assert "c:cv:home" in [data for row in reply.inline_keyboard for _label, data in row], "duyệt HH không cần cookie"

        # 2. Cập nhật đã kết nối
        repo.update_shopee_cookie_status(status="connected", account_name="shopee_vip")
        reply_connected = panel.handle_callback(ADMIN_ID, "c:menu:shopee", "private", NOW)
        assert "ĐÃ KẾT NỐI" in reply_connected.text
        assert "shopee_vip" in reply_connected.text
        assert "🔄 Đồng bộ ngay" in [label for row in reply_connected.inline_keyboard for label, _data in row]

    @patch("cashback_bot.shopee_client.ShopeeAffiliateClient.check_status")
    def test_admin_paste_cookie_workflow_with_delete_message(self, mock_check, tmp_path):
        repo = _setup_repo(tmp_path)
        mock_check.return_value = MagicMock(ok=True, username="test_account", error_message="")

        panel = AdminPanel(str(repo.path), frozenset({ADMIN_ID}), displayed_rate_percent=70)

        # 1. Bấm nút cập nhật cookie
        prompt_reply = panel.handle_callback(ADMIN_ID, "c:shopee:auth", "private", NOW)
        assert "Cập nhật Cookie Shopee Affiliate" in prompt_reply.text

        # 2. Admin dán JSON cookie vào chat (với message_id = 888)
        cookie_json = json.dumps([{"name": "SPC_EC", "value": "my_secret_token"}])
        result = panel.consume_text(ADMIN_ID, cookie_json, NOW, message_id=888)
        assert result is not None
        assert "Đã kết nối Shopee Affiliate thành công" in result.text
        assert result.delete_message_id == 888  # Đánh dấu xoá tin nhắn chứa cookie!

        # Kiểm tra trạng thái DB đã cập nhật
        status = repo.get_shopee_cookie_status()
        assert status["status"] == "connected"
        assert status["account_name"] == "test_account"

    def test_stats_screen_includes_shopee_reconciliation(self, tmp_path):
        repo = _setup_repo(tmp_path)
        _insert_link(repo, "G3lkg1JK")
        repo.record_shopee_click("c1", "G3lkg1JK", "2026-10-23T08:00:00Z")
        repo.record_shopee_click("c2", "----", "2026-10-23T08:01:00Z")
        # Sub ID không do bot tạo thì không tính là click qua bot.
        repo.record_shopee_click("c3", "khac_bot", "2026-10-23T08:02:00Z")
        repo.record_shopee_conversion(
            conversion_id="ord_1",
            sub_id="G3lkg1JK",
            order_sn="SN_001",
            order_status="COMPLETED",
            conversion_status="VALIDATED",
            purchase_time="2026-10-23T08:30:00Z",
            gross_commission_vnd=10000,
            net_commission_vnd=9000,
        )

        with repo.connect() as conn:
            stats = collect(conn, "today", NOW)

        assert stats.shopee is not None
        assert stats.shopee.total_clicks == 3
        assert stats.shopee.clicks_with_bot_sub_id == 1
        assert stats.shopee.orders_total == 1
        assert stats.shopee.orders_completed == 1
        assert stats.shopee.real_commission_vnd == 9000


class TestShopeeReviewFixes:
    """Hồi quy các lỗi tìm thấy khi review PLAN-065."""

    def test_unexpected_payload_returns_result_instead_of_raising(self, tmp_path):
        repo = _setup_repo(tmp_path)
        client = MagicMock()
        client.check_status.return_value = _status(True)
        # Phần tử lạ trong list không làm sync nổ; client ném lỗi bất ngờ thì trả SyncResult.
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": ["la", 1]}}
        client.fetch_conversions.side_effect = RuntimeError("boom")
        result = ShopeeSyncEngine(repo).sync(client=client)
        assert result.ok is False
        assert repo.get_last_sync_run()["status"] == "failed"

    def test_transient_error_keeps_connected_and_does_not_notify(self, tmp_path):
        repo = _setup_repo(tmp_path)
        repo.update_shopee_cookie_status(status="connected", account_name="shop_owner")
        notifier = MagicMock()
        client = MagicMock()
        client.check_status.return_value = _status(False, error="Lỗi kết nối: ConnectionError")
        result = ShopeeSyncEngine(repo, admin_notifier=notifier).sync(client=client)
        assert result.ok is False
        assert repo.get_shopee_cookie_status()["status"] == "connected"
        notifier.notify_shopee_cookie_expired.assert_not_called()

    def test_auth_failure_marks_expired_and_notifies(self, tmp_path):
        repo = _setup_repo(tmp_path)
        notifier = MagicMock()
        client = MagicMock()
        client.check_status.return_value = _status(False, auth_failed=True, error="HTTP 401")
        ShopeeSyncEngine(repo, admin_notifier=notifier).sync(client=client)
        assert repo.get_shopee_cookie_status()["status"] == "expired"
        notifier.notify_shopee_cookie_expired.assert_called_once()

    @patch("cashback_bot.shopee_client.requests.get")
    def test_network_error_is_not_auth_failure(self, mock_get):
        mock_get.side_effect = requests.ConnectionError()
        result = ShopeeAffiliateClient({"SPC_EC": "x"}).check_status()
        assert result.ok is False
        assert result.auth_failed is False

    def test_pagination_stops_when_page_repeats(self, tmp_path):
        repo = _setup_repo(tmp_path)
        client = MagicMock()
        client.check_status.return_value = _status(True)
        full_page = {"code": 0, "data": {"list": [{"click_id": f"c{i}", "sub_id": None} for i in range(200)]}}
        client.fetch_clicks.return_value = full_page  # Shopee bỏ qua page_no, trả mãi một trang
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": []}}
        result = ShopeeSyncEngine(repo).sync(client=client)
        assert result.clicks_synced == 200
        assert client.fetch_clicks.call_count == 2

    def test_cancel_button_stops_waiting_for_cookie(self, tmp_path):
        repo = _setup_repo(tmp_path)
        panel = AdminPanel(str(repo.path), frozenset({ADMIN_ID}), 70)
        panel.handle_callback(ADMIN_ID, "c:shopee:auth", "private", NOW)
        panel.handle_callback(ADMIN_ID, "c:menu:shopee", "private", NOW)  # ✖️ Hủy
        reply = panel.consume_text(ADMIN_ID, "SPC_EC=abc", NOW, message_id=5)
        assert reply is None or reply.delete_message_id is None

    @patch("cashback_bot.admin_policy.save_cookies")
    @patch("cashback_bot.shopee_client.ShopeeAffiliateClient.check_status")
    def test_split_json_cookie_is_joined_and_every_part_deleted(self, mock_check, mock_save, tmp_path):
        repo = _setup_repo(tmp_path)
        mock_check.return_value = _status(True)
        panel = AdminPanel(str(repo.path), frozenset({ADMIN_ID}), 70)
        panel.handle_callback(ADMIN_ID, "c:shopee:auth", "private", NOW)
        raw = json.dumps({"url": "https://affiliate.shopee.vn", "cookies": [{"name": "SPC_EC", "value": "v" * 50}]})
        first = panel.consume_text(ADMIN_ID, raw[:30], NOW, message_id=10)
        second = panel.consume_text(ADMIN_ID, raw[30:], NOW, message_id=11)
        assert first.delete_message_id == 10
        assert "phần còn lại" in first.text
        assert second.delete_message_id == 11
        assert "thành công" in second.text
        assert mock_save.call_args.args[0] == {"SPC_EC": "v" * 50}
        # Đã xong thì không còn chờ cookie nữa.
        assert panel.consume_text(ADMIN_ID, "10", NOW, message_id=12) is None

    def test_multi_order_checkout_does_not_double_count_commission(self, tmp_path):
        repo = _setup_repo(tmp_path)
        client = MagicMock()
        client.check_status.return_value = _status(True)
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": [{
            "checkout_id": "chk_1",
            "purchase_time": 1792742400,
            "utm_content": "----",
            "gross_commission": 300_000_000,
            "affiliate_net_commission": "300000000",
            "orders": [
                {"order_id": "o1", "order_sn": "SN1", "order_status": "COMPLETED",
                 "items": [{"item_commission": 100_000_000}]},
                {"order_id": "o2", "order_sn": "SN2", "order_status": "COMPLETED",
                 "items": [{"item_commission": 200_000_000}]},
            ],
        }]}}
        ShopeeSyncEngine(repo).sync(client=client)
        with repo.connect() as conn:
            rows = conn.execute(
                "SELECT order_sn, net_commission_vnd, purchase_time FROM shopee_conversions ORDER BY order_sn"
            ).fetchall()
        assert [(r["order_sn"], r["net_commission_vnd"]) for r in rows] == [("SN1", 1_000), ("SN2", 2_000)]
        assert rows[0]["purchase_time"] == "2026-10-23T08:00:00Z"

    def test_gross_commission_includes_shop_part(self, tmp_path):
        # Số thật đơn 261023CC4UWJ0N (2026-10-24): Shopee 2,5% = 5.789, shop 5% = 11.578.
        repo = _setup_repo(tmp_path)
        client = MagicMock()
        client.check_status.return_value = _status(True)
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": [{
            "checkout_id": "chk_1",
            "purchase_time": 1792726165,
            "utm_content": "----",
            "gross_commission": 578_925_000,
            "total_brand_commission": 1_157_850_000,
            "estimated_total_commission": 1_736_775_000,
            "affiliate_net_commission": "1736775000",
            "mcn_management_fee_commission": "0",
            "orders": [{"order_id": "o1", "order_sn": "SN1", "order_status": "UNPAID", "items": [
                {"actual_amount": 23_157_000_000, "qty": 1,
                 "item_commission": 578_925_000, "capped_brand_commission": 1_157_850_000},
            ]}],
        }]}}
        ShopeeSyncEngine(repo).sync(client=client)
        with repo.connect() as conn:
            row = conn.execute("SELECT gross_commission_vnd, net_commission_vnd, gmv_vnd FROM shopee_conversions").fetchone()
        assert (row["gross_commission_vnd"], row["net_commission_vnd"], row["gmv_vnd"]) == (17_368, 17_368, 231_570)

    def test_multi_order_checkout_counts_shop_commission(self, tmp_path):
        repo = _setup_repo(tmp_path)
        client = MagicMock()
        client.check_status.return_value = _status(True)
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": [{
            "checkout_id": "chk_1",
            "purchase_time": 1792742400,
            "utm_content": "----",
            "orders": [
                {"order_id": "o1", "order_sn": "SN1", "order_status": "COMPLETED",
                 "items": [{"item_commission": 578_925_000, "capped_brand_commission": 1_157_850_000}]},
                {"order_id": "o2", "order_sn": "SN2", "order_status": "COMPLETED",
                 "items": [{"item_commission": 137_250_000, "capped_brand_commission": 0}]},
            ],
        }]}}
        ShopeeSyncEngine(repo).sync(client=client)
        with repo.connect() as conn:
            rows = conn.execute("SELECT order_sn, net_commission_vnd FROM shopee_conversions ORDER BY order_sn").fetchall()
        assert [(r["order_sn"], r["net_commission_vnd"]) for r in rows] == [("SN1", 17_368), ("SN2", 1_372)]

    def test_multi_order_checkout_tru_phi_mcn_theo_ti_le(self, tmp_path):
        repo = _setup_repo(tmp_path)
        client = MagicMock()
        client.check_status.return_value = _status(True)
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": [{
            "checkout_id": "chk_1",
            "purchase_time": 1792742400,
            "utm_content": "----",
            "affiliate_net_commission": "270000000",
            "mcn_management_fee_commission": "30000000",
            "orders": [
                {"order_id": "o1", "order_sn": "SN1", "order_status": "COMPLETED",
                 "items": [{"item_commission": 100_000_000}]},
                {"order_id": "o2", "order_sn": "SN2", "order_status": "COMPLETED",
                 "items": [{"item_commission": 200_000_000}]},
            ],
        }]}}
        ShopeeSyncEngine(repo).sync(client=client)
        with repo.connect() as conn:
            rows = conn.execute(
                "SELECT order_sn, gross_commission_vnd, net_commission_vnd FROM shopee_conversions ORDER BY order_sn"
            ).fetchall()
        assert [tuple(r) for r in rows] == [("SN1", 1_000, 900), ("SN2", 2_000, 1_800)]

    def test_sync_result_lists_bot_orders_new_then_updated(self, tmp_path):
        repo = _setup_repo(tmp_path)
        _insert_link(repo, "u3e52GNL")
        client = MagicMock()
        client.check_status.return_value = _status(True)
        client.fetch_clicks.return_value = {"code": 0, "data": {"list": []}}
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": [
            {"checkout_id": "chk_1", "purchase_time": 1792726165, "utm_content": "u3e52GNL----",
             "estimated_total_commission": 1_736_775_000, "affiliate_net_commission": "1736775000",
             "orders": [{"order_id": "o1", "order_sn": "SN1", "order_status": "UNPAID",
                         "items": [{"item_name": "DOPI Kem Nền", "actual_amount": 23_157_000_000, "qty": 1}]}]},
            {"checkout_id": "chk_2", "purchase_time": 1792726165, "utm_content": "----",
             "affiliate_net_commission": "100000000",
             "orders": [{"order_id": "o2", "order_sn": "SN2", "order_status": "PAID", "items": []}]},
        ]}}
        first = ShopeeSyncEngine(repo).sync(client=client)
        assert first.bot_orders == (BotOrder("SN1", "DOPI Kem Nền", 231_570, 17_368, "UNPAID", True, "o1"),)
        assert "qua bot 1 (1 mới, 0 cập nhật)" in first.message
        second = ShopeeSyncEngine(repo).sync(client=client)
        assert [o.is_new for o in second.bot_orders] == [False]
        assert "qua bot 1 (0 mới, 1 cập nhật)" in second.message

    def test_sync_message_shows_commission_per_order(self, tmp_path):
        repo = _setup_repo(tmp_path)
        notifier = AdminNotifier(repo, MagicMock(), enabled=True, chat_id=ADMIN_ID)
        orders = [
            BotOrder("SN_OLD", "Bộ 5 Cọ Trang Điểm", 54_900, 1_372, "PAID", False),
            BotOrder("SN_NEW", "Kem <b>nền</b> " + "x" * 60, 231_570, 17_368, "UNPAID", True),
            BotOrder("SN_DONE", None, None, 5_000, "COMPLETED", False),
            BotOrder("SN_CXL", "Áo", 99_000, 0, "CANCELLED", False),
        ]
        notifier.notify_shopee_sync_result(True, "Đồng bộ xong", orders)
        with repo.connect() as conn:
            html_text = conn.execute("SELECT message_html FROM admin_notifications").fetchone()[0]
        table = html_text.split("<pre>")[1].split("</pre>")[0].split("\n")
        # Cột thẳng hàng: mọi dòng bảng (trừ dòng kẻ) dài bằng nhau tới trước cột TT.
        assert table[0] == "#     Giá     HH Phí/T Khách Biên TT"
        assert table[1] == "1 231.570 17.368     -     -    - ⏳"  # đơn mới lên đầu; chưa có sổ thì "-"
        assert table[2] == "2  54.900  1.372     -     -    - ⏳"
        assert table[3] == "3       -  5.000     -     -    - ✅"
        assert table[4] == "4  99.000      0     -     -    - ❌"
        assert table[6] == "Σ 286.470 23.740     0     0    0"  # không tính đơn huỷ
        after = html_text.split("</pre>\n")[1].split("\n")
        # Tên dài bị cắt, ký tự HTML được escape.
        assert after[0].startswith("1. 🆕 Kem &lt;b&gt;nền&lt;/b&gt; ")
        assert after[0].endswith("… · ⏳ Chờ thanh toán")
        assert after[1] == "2. Bộ 5 Cọ Trang Điểm · ⏳ Chờ duyệt"
        assert after[2] == "3. SN_DONE · ✅ Hoàn thành"
        assert after[3] == "4. Áo · ❌ Đã huỷ"

    def test_paid_and_unpaid_count_as_pending(self, tmp_path):
        repo = _setup_repo(tmp_path)
        for cid, status in (("a", "UNPAID"), ("b", "PAID"), ("c", "COMPLETED"), ("d", "CANCELLED")):
            repo.record_shopee_conversion(
                conversion_id=cid, sub_id=None, order_sn=cid, order_status=status, conversion_status="",
                purchase_time="2026-10-23T08:00:00Z", gross_commission_vnd=1_000, net_commission_vnd=1_000,
            )
        with repo.connect() as conn:
            shopee = collect(conn, "all", NOW).shopee
        assert (shopee.orders_pending, shopee.orders_completed, shopee.orders_cancelled) == (2, 1, 1)

    def test_sync_message_caps_order_list(self, tmp_path):
        repo = _setup_repo(tmp_path)
        notifier = AdminNotifier(repo, MagicMock(), enabled=True, chat_id=ADMIN_ID)
        orders = [BotOrder(f"SN{i}", f"Món {i}", 10_000, 700, "PAID", False) for i in range(13)]
        notifier.notify_shopee_sync_result(True, "Đồng bộ xong", orders)
        with repo.connect() as conn:
            html_text = conn.execute("SELECT message_html FROM admin_notifications").fetchone()[0]
        assert html_text.count(" ⏳\n") + html_text.count(" ⏳</pre>") == 10
        assert "\n10. Món 9 · ⏳ Chờ duyệt" in html_text
        assert "… và 3 đơn khác" in html_text

    def test_endpoint_rejected_is_reported_as_partial(self, tmp_path):
        repo = _setup_repo(tmp_path)
        client = MagicMock()
        client.check_status.return_value = _status(True)
        client.fetch_clicks.side_effect = ShopeeApiError("Shopee HTTP 400", status_code=400)
        client.fetch_conversions.return_value = {"code": 0, "data": {"list": []}}
        result = ShopeeSyncEngine(repo).sync(client=client)
        assert result.ok is False
        assert "click" in result.message
        assert repo.get_last_sync_run()["status"] == "partial"

    @patch("cashback_bot.shopee_client.requests.get")
    def test_client_sends_param_names_shopee_accepts(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"code": 0, "data": {"list": []}})
        client = ShopeeAffiliateClient({"SPC_EC": "x"})
        client.fetch_clicks(1, 2, page_no=3, page_size=100)
        assert mock_get.call_args.kwargs["params"] == {
            "click_time_s": 1, "click_time_e": 2, "page_num": 3, "page_size": 100,
        }
        client.fetch_conversions(1, 2, page_no=3, page_size=100)
        assert mock_get.call_args.kwargs["params"] == {
            "purchase_time_s": 1, "purchase_time_e": 2, "page_num": 3, "page_size": 100, "version": 1,
        }
