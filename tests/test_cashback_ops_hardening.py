"""PLAN-087: rớt mạng không làm mất tin, 400 không phải khách chặn bot, Zalo lỗi giữa chừng, đồng bộ không quay vòng."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import requests
from urllib3.exceptions import MaxRetryError, NewConnectionError, ProtocolError

from cashback_bot import ops_watch, telegram_api, zalo_api
from cashback_bot.admin_notify import AdminNotifier
from cashback_bot.backup import MANUAL, backup_database, latest_backup
from cashback_bot.db import TrackingRepository
from cashback_bot.notify_dispatch import Dispatcher
from cashback_bot.poller import process_updates
from cashback_bot.sync_scheduler import RETRY_BASE, SyncWorker, busy
from cashback_bot.telegram_api import TelegramApi, TelegramDeliveryError, classify_delivery_error, never_sent
from cashback_bot.zalo_api import ZaloApi
from cashback_bot.zalo_bot import ZaloSender
from cashback_bot.zalo_render import ERROR_REPLY, MAX_LEN, flatten
from tests.test_cashback_auto_sync import Clock, _coord, _ready_bot
from tests.test_cashback_bot import FakeClient, payload, service
from tests.test_cashback_order_notifications import FakeTelegram, _events, _flush, _link, _order, _ready
from tests.test_cashback_wallet import USER
from tests.test_cashback_zalo import FakeZalo, _Admin, _channel, _texts, _update
from tests.test_cashback_zalo import NOW as ZALO_NOW

ADMIN_CHAT = 999


def _offline() -> requests.ConnectionError:
    return requests.ConnectionError(MaxRetryError(None, "/sendMessage", reason=NewConnectionError(None, "down")))


def _status(repo, event_key=None):
    with repo.connect() as conn:
        sql = "SELECT status, attempt_count FROM admin_notifications"
        row = conn.execute(sql + (" WHERE event_key = ?" if event_key else " ORDER BY id"),
                           (event_key,) if event_key else ()).fetchone()
    return tuple(row)


def test_phan_loai_loi_chua_ket_noi_va_loi_giua_chung():
    assert never_sent(_offline()) and never_sent(requests.ConnectTimeout())
    assert classify_delivery_error(_offline()) == ("offline", None)
    assert not never_sent(requests.ConnectionError(ProtocolError("Connection aborted.")))
    assert not never_sent(requests.ReadTimeout())
    assert classify_delivery_error(requests.ReadTimeout()) == ("ambiguous", None)


@pytest.mark.parametrize("module, api, chat", [(telegram_api, TelegramApi("t"), 1), (zalo_api, ZaloApi("t"), "z")])
def test_gui_tin_khi_mat_mang_bao_offline(monkeypatch, module, api, chat):
    def down(*args, **kwargs):
        raise _offline()

    monkeypatch.setattr(module.requests, "post", down)
    with pytest.raises(TelegramDeliveryError) as exc:
        api.send_message(chat, "x")
    assert exc.value.kind == "offline"


def test_tin_khach_mat_mang_lau_khong_mat_va_khong_tinh_luot(tmp_path):
    bot = _ready(tmp_path)
    _order(bot, _link(bot), commission=10_000)
    _order(bot, _link(bot), commission=10_000, cid="o2")
    now = datetime.now(timezone.utc)
    telegram = FakeTelegram([TelegramDeliveryError("offline")] * 30)
    for minute in range(30):
        result = _flush(bot, telegram, now + timedelta(minutes=minute))
        assert result.retry == 1 and result.unknown == 0, "dừng vòng gửi sau lỗi mất mạng đầu tiên"
    assert [(e["status"], e["attempt_count"]) for e in _events(bot)] == [("retry", 0), ("pending", 0)]
    assert _flush(bot, telegram, now + timedelta(minutes=31)).sent == 2
    assert [e["status"] for e in _events(bot)] == ["sent", "sent"]


def test_tin_admin_mat_mang_qua_8_phut_van_gui(tmp_path):
    bot = _ready(tmp_path)
    bot.repo.enqueue_admin_event("admin:k", "POLL_ERROR", ADMIN_CHAT, "x")
    telegram = FakeTelegram([TelegramDeliveryError("offline")] * 20)
    dispatcher = Dispatcher(bot.repo, telegram, True, ADMIN_CHAT, True)
    now = datetime.now(timezone.utc)
    for minute in range(20):
        dispatcher.flush(now=now + timedelta(minutes=minute))
    assert _status(bot.repo, "admin:k") == ("retry", 0)
    assert dispatcher.flush(now=now + timedelta(minutes=21)).sent == 1


def test_loi_400_khong_danh_dau_khach_chan_bot(tmp_path):
    bot = _ready(tmp_path)
    mine = _link(bot)
    _order(bot, mine, commission=10_000)
    assert _flush(bot, FakeTelegram([TelegramDeliveryError("permanent", status_code=400)])).failed == 1
    _order(bot, mine, commission=10_000, cid="o2")
    assert _flush(bot, FakeTelegram()).sent == 1, "tin sau vẫn gửi"
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT notify_blocked_at FROM telegram_users WHERE telegram_user_id = ?",
                            (USER,)).fetchone()[0] is None


def test_go_ket_sending_theo_kenh(tmp_path):
    bot = _ready(tmp_path)
    bot.repo.enqueue_admin_event("support:t", "SUPPORT_CUSTOMER", USER, "t")
    bot.repo.enqueue_admin_event("support:z", "SUPPORT_CUSTOMER", -1, "z")
    with bot.repo.connect() as conn:
        ids = [r[0] for r in conn.execute("SELECT id FROM admin_notifications ORDER BY id")]
    assert all(bot.repo.claim_admin_event(i) for i in ids)
    assert bot.repo.recover_sending() == 1
    assert _status(bot.repo, "support:z")[0] == "sending", "bot Telegram khởi động không đụng tin Zalo đang gửi"
    assert bot.repo.recover_sending(channel="zalo") == 1
    assert _status(bot.repo, "support:z")[0] == "unknown"


class _OfflineTelegram:
    def __init__(self, failures: int):
        self.failures = failures
        self.sent = []

    def send_message(self, chat_id, html, reply_markup=None, disable_notification=False):
        if self.failures:
            self.failures -= 1
            raise _offline()
        self.sent.append(chat_id)

    def send_chat_action(self, chat_id, action="typing"):
        pass


class _RecordAdmin:
    def __init__(self):
        self.failed = []

    def flush_pending(self, limit=10):
        pass

    def notify_link_sent(self, update_id):
        pass

    def notify_request_failed(self, **kwargs):
        self.failed.append(kwargs)


def test_tra_loi_khach_mat_mang_khong_tinh_luot_khong_bao_admin(tmp_path):
    current = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    bot = service(tmp_path, FakeClient(payload(last_update=current)), delivery_backoff_sec=0)
    tg, admin = _OfflineTelegram(failures=1), _RecordAdmin()
    update = {"update_id": 40, "message": {"chat": {"type": "private", "id": 111},
                                           "from": {"id": 111, "username": "buyer"},
                                           "text": "https://shopee.vn/product/9/8"}}
    process_updates(bot, tg, bot.repo, [update], admin)
    row = bot.repo.get_outbound(40)
    assert (row["status"], row["attempt_count"], row["last_error"]) == ("retry", 0, "offline")
    assert admin.failed == []


def test_zalo_loi_db_giua_chung_bao_khach_va_admin(tmp_path, monkeypatch):
    bot, channel, zalo = _channel(tmp_path)
    admin = _Admin()
    channel.admin_notifier = admin

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(channel.store, "save_reply", broken)
    channel.handle(_update("hd"), now=ZALO_NOW)
    assert flatten(ERROR_REPLY)[0] in _texts(zalo)
    assert admin.failed and admin.failed[0]["error_type"] == "zalo_update_failed"
    with bot.repo.connect() as conn:
        assert tuple(conn.execute("SELECT status, last_error FROM zalo_inbox").fetchone()) == ("failed", "handler_error")


def test_zalo_tra_loi_mat_mang_khong_tinh_luot(tmp_path):
    bot, channel, zalo = _channel(tmp_path, zalo=FakeZalo(fail=[TelegramDeliveryError("offline")] * 8))
    channel.handle(_update("hd"), now=ZALO_NOW)
    for hour in range(1, 8):
        channel.retry_due(now=ZALO_NOW + timedelta(hours=hour))
    with bot.repo.connect() as conn:
        assert tuple(conn.execute("SELECT status, attempt_count FROM zalo_inbox").fetchone()) == ("retry", 0)
    channel.retry_due(now=ZALO_NOW + timedelta(hours=9))
    with bot.repo.connect() as conn:
        assert conn.execute("SELECT status FROM zalo_inbox").fetchone()[0] == "replied"


class _SecondPartFails(FakeZalo):
    def send_message(self, chat_id, text, styles=None):
        if self.sent:
            raise TelegramDeliveryError("transient", status_code=502)
        return super().send_message(chat_id, text, styles)


def test_zalo_tin_nhieu_phan_loi_giua_chung_khong_gui_lai_phan_dau(tmp_path):
    bot, channel, _zalo = _channel(tmp_path)
    channel.handle(_update("hd"), now=ZALO_NOW)
    zalo = _SecondPartFails()
    bot.repo.enqueue_admin_event("support:z", "SUPPORT_CUSTOMER", -1, ("dòng dài " * 40 + "\n") * (MAX_LEN // 300 + 2))
    dispatcher = Dispatcher(bot.repo, ZaloSender(zalo, channel.store), False, None, False, channel="zalo")
    assert dispatcher.flush().unknown == 1 and len(zalo.sent) == 1
    dispatcher.flush(now=datetime.now(timezone.utc) + timedelta(hours=1))
    assert len(zalo.sent) == 1 and _status(bot.repo, "support:z")[0] == "unknown"


def test_dong_luot_loi_db_nha_khoa_va_hen_lai(tmp_path, monkeypatch):
    bot = _ready_bot(tmp_path)
    clock = Clock()
    coordinator = _coord(bot.repo, clock=clock)

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(coordinator, "_finish", broken)
    with pytest.raises(sqlite3.OperationalError):
        coordinator.run("auto")
    assert busy(bot.repo, clock()) is None
    assert coordinator.next_job(clock()) is None, "không lấy lại việc ngay"
    assert coordinator.next_job(clock() + RETRY_BASE) == "auto"


def test_luong_nen_ban_thi_doi_nhip_khong_quay_vong():
    coordinator = MagicMock()
    coordinator.next_job.return_value = "auto"
    coordinator.run.return_value = None
    worker = SyncWorker(coordinator, tick_seconds=0.05)
    worker.start()
    time.sleep(0.3)
    worker.stop()
    worker.join(timeout=2)
    assert coordinator.run.call_count <= 10


def test_backup_tay_khong_day_mat_ban_tu_dong(tmp_path):
    source = tmp_path / "live.sqlite"
    sqlite3.connect(source).close()
    folder = tmp_path / "backups"
    start = datetime(2026, 10, 25, 1, 0, tzinfo=timezone.utc)
    daily = [backup_database(source, folder, now=start + timedelta(days=i), keep=3) for i in range(3)]
    manual = [backup_database(source, folder, now=start + timedelta(days=3, minutes=i), keep=3, label=MANUAL)
              for i in range(5)]
    names = sorted(path.name for path in folder.iterdir())
    assert [path.name for path in daily] == [n for n in names if "manual" not in n], "bản tự động còn đủ"
    assert [path.name for path in manual[-3:]] == [n for n in names if "manual" in n], "bản tay dọn riêng"
    assert latest_backup(folder) == manual[-1]


def _notifier(repo):
    return AdminNotifier(repo, MagicMock(), enabled=True, chat_id=ADMIN_CHAT)


def _admin_events(repo, event_type):
    with repo.connect() as conn:
        return conn.execute("SELECT message_html FROM admin_notifications WHERE event_type = ?", (event_type,)).fetchall()


def test_hai_bot_khac_commit_bao_bot_cu_mot_lan(tmp_path):
    repo = TrackingRepository(str(tmp_path / "v.sqlite"))
    repo.migrate()
    admin = _notifier(repo)
    repo.set_state(ops_watch.VERSION_KEYS["zalo"], "aaaaaaa@100")
    repo.set_state(ops_watch.VERSION_KEYS["telegram"], "aaaaaaa@200")
    ops_watch.check_versions(repo, admin)
    assert _admin_events(repo, "CODE_MISMATCH") == []
    repo.set_state(ops_watch.VERSION_KEYS["telegram"], "bbbbbbb@300")
    ops_watch.check_versions(repo, admin)
    ops_watch.check_versions(repo, admin)
    rows = _admin_events(repo, "CODE_MISMATCH")
    assert len(rows) == 1 and "Bot Zalo khởi động trước" in rows[0][0]


def test_ma_commit_doc_tu_git(tmp_path):
    git = tmp_path / ".git"
    (git / "refs" / "heads").mkdir(parents=True)
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    (git / "packed-refs").write_text("# pack-refs\n1234567890abcdef refs/heads/main\n")
    assert ops_watch.code_version(tmp_path) == "1234567"
    (git / "refs" / "heads" / "main").write_text("abcdef0123456789\n")
    assert ops_watch.code_version(tmp_path) == "abcdef0"
    assert ops_watch.code_version(tmp_path / "none") == "unknown"


def test_lenh_restart_theo_cach_chay_bot(tmp_path):
    assert "setsid nohup" in ops_watch.restart_command("zalo", tmp_path)
    (tmp_path / "cashback-zalo.service").write_text("")
    assert ops_watch.restart_command("zalo", tmp_path) == "systemctl restart cashback-zalo"


class _DirectTelegram:
    def __init__(self, fail: int = 0):
        self.fail = fail
        self.sent = []

    def send_message(self, chat_id, html, **kwargs):
        if self.fail:
            self.fail -= 1
            raise TelegramDeliveryError("offline")
        self.sent.append((chat_id, html))


def test_bot_zalo_bao_khi_bot_telegram_chet(tmp_path):
    repo = TrackingRepository(str(tmp_path / "h.sqlite"))
    repo.migrate()
    tg = _DirectTelegram(fail=1)
    t0 = 1_800_000_000.0
    ops_watch.check_telegram_health(repo, tg, ADMIN_CHAT, now=t0)
    assert tg.sent == [], "chưa từng có nhịp sống thì không báo"
    ops_watch.beat(repo, now=t0)
    ops_watch.check_telegram_health(repo, tg, ADMIN_CHAT, now=t0 + 400)
    assert tg.sent == []
    ops_watch.check_telegram_health(repo, tg, ADMIN_CHAT, now=t0 + 700)  # gửi lỗi: lần sau thử lại
    ops_watch.check_telegram_health(repo, tg, ADMIN_CHAT, now=t0 + 1000)
    ops_watch.check_telegram_health(repo, tg, ADMIN_CHAT, now=t0 + 1300)
    assert len(tg.sent) == 1 and "Bot Telegram không hoạt động" in tg.sent[0][1]
    ops_watch.beat(repo, now=t0 + 1500)
    ops_watch.check_telegram_health(repo, tg, ADMIN_CHAT, now=t0 + 1600)
    assert len(tg.sent) == 2 and "hoạt động lại" in tg.sent[1][1]


def test_tom_tat_tin_loi_moi_sang(tmp_path):
    bot = _ready(tmp_path)
    admin = _notifier(bot.repo)
    _order(bot, _link(bot), commission=10_000)
    _flush(bot, FakeTelegram([TelegramDeliveryError("ambiguous")]))
    morning = datetime.now(timezone.utc).astimezone(ops_watch.ICT).replace(hour=7, minute=30)
    ops_watch.check_delivery_digest(bot.repo, admin, morning)
    assert _admin_events(bot.repo, "DELIVERY_DIGEST") == [], "chưa tới 8 giờ"
    ops_watch.check_delivery_digest(bot.repo, admin, morning.replace(hour=8, minute=5))
    ops_watch.check_delivery_digest(bot.repo, admin, morning.replace(hour=12))
    rows = _admin_events(bot.repo, "DELIVERY_DIGEST")
    assert len(rows) == 1 and "không rõ đã tới chưa" in rows[0][0] and "<b>1</b>" in rows[0][0]
