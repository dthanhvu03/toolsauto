"""PLAN-084: rớt mạng khi nhận tin Telegram gộp thành một tin, không báo "Lỗi bot" mỗi phút."""

from __future__ import annotations

from unittest.mock import MagicMock

from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.db import TrackingRepository
from cashback_bot.poller import NET_ALERT_AFTER_SEC, NET_STILL_DOWN_SEC, _net_failed, _net_recovered

ADMIN = 999
T0 = 1_792_890_705.0  # 2026-10-25 01:11:45Z = 08:11 giờ VN


def _setup(tmp_path):
    repo = TrackingRepository(str(tmp_path / "net.sqlite"))
    repo.migrate()
    return repo, AdminNotifier(repo, MagicMock(), enabled=True, chat_id=ADMIN)


def _events(repo):
    with repo.connect() as conn:
        return conn.execute("SELECT event_type, message_html FROM admin_notifications ORDER BY id").fetchall()


def test_rot_mang_ngan_khong_bao_admin(tmp_path):
    repo, admin = _setup(tmp_path)
    _net_failed(repo, admin, now=T0)
    _net_failed(repo, admin, now=T0 + 41)
    _net_recovered(repo, admin, now=T0 + NET_ALERT_AFTER_SEC - 1)
    assert _events(repo) == []
    _net_recovered(repo, admin, now=T0 + 500)
    assert _events(repo) == [], "đã hồi thì lần nhận tin sau không báo lại"


def test_mat_ket_noi_4_phut_bao_mot_tin_khi_ket_noi_lai(tmp_path):
    repo, admin = _setup(tmp_path)
    for step in range(0, 241, 45):
        _net_failed(repo, admin, now=T0 + step)
    assert _events(repo) == []
    _net_recovered(repo, admin, now=T0 + 290)
    rows = _events(repo)
    assert [row[0] for row in rows] == ["NET_UP"]
    assert "Mất kết nối 08:11–08:16 · 25/10 (5 phút)" in rows[0][1] and "Zalo" in rows[0][1]


def test_mat_ket_noi_lau_bao_dang_mat_mot_lan_roi_bao_ket_noi_lai(tmp_path):
    repo, admin = _setup(tmp_path)
    for step in range(0, NET_STILL_DOWN_SEC + 300, 30):
        _net_failed(repo, admin, now=T0 + step)
    _net_recovered(repo, admin, now=T0 + 700)
    rows = _events(repo)
    assert [row[0] for row in rows] == ["NET_DOWN", "NET_UP"]
    assert "từ 08:11 · 25/10" in rows[0][1] and "(12 phút)" in rows[1][1]


def test_khoi_dong_lai_giua_luc_mat_mang_van_bao_dung_mot_lan(tmp_path):
    repo, admin = _setup(tmp_path)
    _net_failed(repo, admin, now=T0)
    admin = AdminNotifier(repo, MagicMock(), enabled=True, chat_id=ADMIN)
    _net_failed(repo, admin, now=T0 + 90)
    _net_recovered(repo, admin, now=T0 + 120)
    _net_recovered(repo, admin, now=T0 + 150)
    assert [row[0] for row in _events(repo)] == ["NET_UP"]


def test_loi_bot_khong_co_update_va_user_thi_bo_khoi_chi_tiet(tmp_path):
    repo, admin = _setup(tmp_path)
    admin.notify_request_failed(error_type="poll_loop_failed", status="POLL_ERROR")
    admin.notify_request_failed(error_type="zalo_update_failed", update_id=-5, telegram_user_id=-1)
    first, second = (row[1] for row in _events(repo))
    assert "blockquote" not in first and "Update" not in first
    assert "Tin Zalo <code>#5</code>" in second and "Zalo <code>#1</code>" in second
