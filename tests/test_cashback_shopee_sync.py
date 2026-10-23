"""Unit tests for PLAN-065: Shopee Affiliate Cookie Sync & Attribution."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cashback_bot.admin_policy import AdminPanel
from cashback_bot.admin_stats import collect
from cashback_bot.db import TrackingRepository
from cashback_bot.shopee_client import (
    ShopeeAffiliateClient,
    ShopeeApiError,
)
from cashback_bot.shopee_cookie import (
    cookies_to_header,
    load_cookies,
    parse_cookies,
    save_cookies,
)
from cashback_bot.shopee_sync import ShopeeSyncEngine, parse_shopee_money_vnd

ADMIN_ID = 9999
USER_ID = 1234
NOW = datetime(2026, 10, 23, 10, 0, 0, tzinfo=timezone.utc)


def _setup_repo(tmp_path: Path) -> TrackingRepository:
    db_file = tmp_path / "cashback.sqlite"
    repo = TrackingRepository(str(db_file))
    repo.migrate()
    return repo


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
        # Scale 100.000 (POC real data 451.000.000 = 4.510 VND)
        assert parse_shopee_money_vnd(451_000_000) == 4_510
        assert parse_shopee_money_vnd("451000000") == 4_510
        # Already normal VND
        assert parse_shopee_money_vnd(50_000) == 50_000
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
                        "checkout_id": "chk_999",
                        "orders": [
                            {
                                "order_id": "ord_1001",
                                "order_sn": "261023ABC123",
                                "sub_id": "G3lkg1JK",
                                "order_status": "COMPLETED",
                                "gross_commission": 500_000_000,  # 5,000 VND
                                "affiliate_net_commission": 450_000_000,  # 4,500 VND
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
        # Thêm 5 click và 2 đơn
        repo.record_shopee_click("c1", "G3lkg1JK", "2026-10-23T08:00:00Z")
        repo.record_shopee_click("c2", "----", "2026-10-23T08:01:00Z")
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
        assert stats.shopee.total_clicks == 2
        assert stats.shopee.clicks_with_bot_sub_id == 1
        assert stats.shopee.orders_total == 1
        assert stats.shopee.orders_completed == 1
        assert stats.shopee.real_commission_vnd == 9000
