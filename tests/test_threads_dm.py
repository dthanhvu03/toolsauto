"""PLAN-171: AI agent tin nhắn riêng Threads — đọc hộp tin, quyết định, hạn mức, chuyển chủ bot."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from app.features.threads.growth import dm_agent
from app.features.threads.growth.config import _role_from, AccountRole, channel_code, TargetBot
from app.features.threads.growth.dm import (
    INBOX, REQUESTS, DmMessage, DmRow, messages_from, parse_age, rows_from, signature, unanswered,
)
from app.features.threads.growth.dm_agent import Decision, handle_inbox, parse_decision
from app.features.threads.growth.notify import cycle_text, dm_handoff_text
from app.features.threads.growth.storage import GrowthStorage

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
ACC = "us28qt"


def _run(coro):
    return asyncio.run(coro)


class FakeDm:
    """DmBrowser giả: hộp tin + cuộc trò chuyện dựng sẵn, ghi lại tin đã gửi."""

    def __init__(self, rows, threads, fail_send=False):
        self.rows = rows
        self.threads = threads
        self.sent = []
        self.opened = []
        self.fail_send = fail_send

    def list(self, folder):
        return [r for r in self.rows if r.folder == folder]

    def read(self, thread_id, folder):
        self.opened.append(thread_id)
        return list(self.threads[thread_id])

    def send(self, thread_id, folder, text):
        if self.fail_send:
            raise RuntimeError("Không thấy ô nhập tin nhắn")
        self.sent.append((thread_id, folder, text))
        self.threads[thread_id].append(DmMessage(True, text))

    def _pause(self, lo, hi):
        pass


def _decider(decision):
    async def fn(handle, messages, folder):
        return decision
    return fn


@pytest.fixture
def storage(tmp_path):
    return GrowthStorage(tmp_path / "g.sqlite")


# --- đọc trang ---------------------------------------------------------------------------------------------------


def test_doc_tuoi_va_hang_hop_tin():
    assert parse_age("6d") == 6 and parse_age("1w") == 7 and parse_age("1y") == 365 and parse_age("4h") == 0
    assert parse_age("hôm qua") is None
    rows = rows_from([
        {"href": "/messages/", "text": "Messages"},
        {"href": "/messages/requests", "text": "Requests\n2"},
        {"href": "/messages/t/4443028309293842/?inbox_override=requests", "text": "natalie.chilly\nB còn slot canva free k ạ?\n·\n1d"},
        {"href": "/messages/t/4443028309293842/", "text": "natalie.chilly\ntrùng\n·\n1d"},
        {"href": "/messages/t/111/", "text": "khanh.nhakhoatam\nDạ"},
    ], REQUESTS)
    assert rows == [
        DmRow("4443028309293842", "natalie.chilly", "B còn slot canva free k ạ?", 1, REQUESTS),
        DmRow("111", "khanh.nhakhoatam", "Dạ", None, REQUESTS),
    ]


def test_tin_cuoi_cua_khach_va_dau_van_tay():
    msgs = messages_from([{"t": "Em chào chị", "mine": False}, {"t": "Dạ em nghe ạ", "mine": True},
                          {"t": "Chị còn slot canva", "mine": False}, {"t": "Email e là x@y.z", "mine": False},
                          {"t": "Message...", "mine": False}])
    assert [m.text for m in unanswered(msgs)] == ["Chị còn slot canva", "Email e là x@y.z"], "bỏ chữ gợi ý ô nhập"
    assert signature(msgs) and signature(msgs + [DmMessage(True, "ok")]) == ""
    assert signature(msgs) != signature(msgs + [DmMessage(False, "?")])


def test_doc_json_quyet_dinh():
    d = parse_decision('ok {"action": "reply", "reply": "Bạn  vào link   này nha", "note": "hỏi giá", "bot": "ai_store", "hot": 140}')
    assert d == Decision("reply", "Bạn vào link này nha", "hỏi giá", "ai_store", 100)
    assert parse_decision('{"action": "skip", "reply": "bỏ"}').reply == ""
    assert parse_decision('{"action": "reply", "reply": ""}') is None
    assert parse_decision('{"action": "ban"}') is None and parse_decision("không phải json") is None


# --- một nhịp hộp tin ---------------------------------------------------------------------------------------------


def test_tra_loi_khach_moi_trong_requests_va_khong_mo_lai(storage):
    row = DmRow("1", "natalie.chilly", "B còn slot canva free k ạ?", 1, REQUESTS)
    fake = FakeDm([row], {"1": [DmMessage(False, "Chào bạn ạ"), DmMessage(False, "B còn slot canva free k ạ?")]})
    events = handle_inbox(fake, storage, ACC, NOW, _run, _decider(Decision("reply", "Còn nè b, vào link này nha", "xin canva", "canva", 80)))
    assert fake.sent == [("1", REQUESTS, "Còn nè b, vào link này nha")]
    assert events[0]["action"] == "reply" and events[0]["theirs"] == "Chào bạn ạ / B còn slot canva free k ạ?"
    assert storage.count_dm_sent_since(NOW - timedelta(hours=1), ACC) == 1
    again = FakeDm([row], fake.threads)
    assert handle_inbox(again, storage, ACC, NOW, _run, _decider(Decision("reply", "lặp", "", "", 0))) == []
    assert again.opened == [], "chữ hàng không đổi → không mở lại"


def test_tin_cuoi_cua_minh_cuoc_cu_va_bo_qua(storage):
    rows = [DmRow("a", "ptn_no_oc", "Chào bạn 👋 Mình tặng…", 6, INBOX),
            DmRow("b", "dracula79_hn", "Bé hấp dẫn🌹", 365, REQUESTS),
            DmRow("c", "co_duyen", "bên có bán giá siêu rẻ", 6, INBOX)]
    fake = FakeDm(rows, {"a": [DmMessage(True, "Chào bạn 👋 Mình tặng…")], "c": [DmMessage(False, "bên có bán giá siêu rẻ")]})
    events = handle_inbox(fake, storage, ACC, NOW, _run, _decider(Decision("skip", "", "người bán chào hàng", "none", 0)))
    assert fake.opened == ["a", "c"], "Requests 1 năm trước không mở"
    assert fake.sent == [] and [e["action"] for e in events] == ["skip"]
    assert storage.dm_thread("c", ACC)["status"] == "open"


def test_skip_trong_requests_thi_khong_accept(storage):
    row = DmRow("r", "h.nguoisao", "tin sàm sỡ", 2, REQUESTS)
    fake = FakeDm([row], {"r": [DmMessage(False, "tin sàm sỡ")]})
    handle_inbox(fake, storage, ACC, NOW, _run, _decider(Decision("skip", "", "sàm sỡ", "none", 0)))
    assert fake.sent == [] and storage.dm_thread("r", ACC)["status"] == "ignored"


def test_handoff_bao_anh_roi_im_24_gio(storage):
    row = DmRow("h", "khach", "acc lỗi rồi shop ơi", 0, INBOX)
    fake = FakeDm([row], {"h": [DmMessage(False, "acc lỗi rồi shop ơi")]})
    events = handle_inbox(fake, storage, ACC, NOW, _run,
                          _decider(Decision("handoff", "Mình báo chủ shop kiểm tra liền nha", "acc lỗi — bảo hành", "ai_store", 60)))
    assert events[0]["action"] == "handoff" and len(fake.sent) == 1
    assert storage.dm_thread("h", ACC)["status"] == "handoff"
    text = dm_handoff_text(events[0])
    assert "Khách cần anh xử lý" in text and "/messages/t/h/" in text and "bảo hành" in text
    # Khách nhắn thêm trong 24 giờ: không trả lời, chỉ báo anh.
    fake.threads["h"].append(DmMessage(False, "shop ơi?"))
    later = FakeDm([DmRow("h", "khach", "shop ơi?", 0, INBOX)], fake.threads)
    events = handle_inbox(later, storage, ACC, NOW + timedelta(hours=1), _run, _decider(Decision("reply", "x", "", "", 0)))
    assert [e["action"] for e in events] == ["handoff_more"] and later.sent == []


def test_han_muc_gio_va_moi_cuoc(storage):
    for i in range(dm_agent.MAX_PER_HOUR):
        storage.log_dm(f"t{i}", ACC, "x", "out", "hi")
    fake = FakeDm([DmRow("n", "moi", "giá?", 0, INBOX)], {"n": [DmMessage(False, "giá?")]})
    assert handle_inbox(fake, storage, ACC, datetime.now(timezone.utc), _run, _decider(Decision("reply", "y", "", "", 0))) == []
    assert fake.opened == [], "hết suất giờ: không mở hộp tin"


def test_gui_loi_thi_danh_dau_va_bao_anh(storage):
    fake = FakeDm([DmRow("f", "k", "giá canva?", 0, INBOX)], {"f": [DmMessage(False, "giá canva?")]}, fail_send=True)
    events = handle_inbox(fake, storage, ACC, NOW, _run, _decider(Decision("reply", "1.100đ nha b", "hỏi giá", "ai_store", 70)))
    assert events[0]["action"] == "failed" and "định gửi" in events[0]["note"]
    assert storage.dm_thread("f", ACC)["status"] == "handoff", "không gửi lại tự động (tránh trùng)"


def test_ai_loi_thi_de_luot_sau(storage):
    fake = FakeDm([DmRow("z", "k", "hello", 0, INBOX)], {"z": [DmMessage(False, "hello")]})
    assert handle_inbox(fake, storage, ACC, NOW, _run, _decider(None)) == []
    assert storage.dm_thread("z", ACC) is None, "chưa đánh dấu → lượt sau thử lại"


# --- kiến thức + cấu hình -----------------------------------------------------------------------------------------


def test_prompt_co_bang_gia_link_va_kiem_username(tmp_path, monkeypatch):
    store = tmp_path / "store.sqlite"
    with sqlite3.connect(store) as c:
        c.execute("CREATE TABLE products (name TEXT, price INT, description TEXT, active INT, upstream_available INT)")
        c.execute("INSERT INTO products VALUES ('Slot Canva Pro 1 Tháng BHF', 1100, 'nhận lời mời, vào được', 1, 1)")
    cb = tmp_path / "cb.sqlite"
    with sqlite3.connect(cb) as c:
        c.execute("CREATE TABLE telegram_users (telegram_user_id INT, username TEXT)")
        c.execute("CREATE TABLE link_requests (telegram_user_id INT, link_status TEXT)")
        c.execute("INSERT INTO telegram_users VALUES (7, 'khanhnq')")
        c.execute("INSERT INTO link_requests VALUES (7, 'created')")
    monkeypatch.setenv("STORE_DB_PATH", str(store))
    monkeypatch.setenv("CASHBACK_DB_PATH", str(cb))
    assert "Slot Canva Pro 1 Tháng BHF: 1.100đ (còn hàng)" in dm_agent.catalog()
    assert dm_agent.cashbot_user("Của e là @khanhnq") == "@khanhnq: đã vào Cashbot, đã tạo 1 link"
    assert "CHƯA thấy" in dm_agent.cashbot_user("@ainguoila")
    prompt = dm_agent.build_prompt("k", [DmMessage(False, "giá canva?")], INBOX, dm_agent.catalog(), None)
    assert channel_code(TargetBot.CASHBOT, "dm") in prompt and channel_code(TargetBot.AI_STORE, "dm") in prompt
    assert "1.100đ" in prompt and "mật khẩu" in prompt
    assert "?start=canva," in prompt, "đúng link đợt tặng Canva của chủ bot"


def test_vai_tai_khoan_doc_co_dm():
    assert _role_from({"dm": True}, AccountRole(enabled=True)).dm is True
    assert _role_from({}, AccountRole()).dm is False


def test_bao_cao_vong_co_tin_nhan_rieng():
    text = cycle_text({"posted": 0, "dms": [
        {"handle": "natalie", "action": "reply", "theirs": "còn slot k", "reply": "còn nha", "hot": 80},
        {"handle": "spam", "action": "skip", "theirs": "x"}]})
    assert "nhắn riêng 1 người" in text and "@natalie" in text and "@spam" not in text
    json.dumps(text)


def test_mo_trinh_duyet_gap_checkpoint_thi_van_dong():
    """14/11: checkpoint lúc mở → __exit__ không chạy → Playwright kẹt → mọi tài khoản sau đó mở lỗi."""
    from app.features.threads.adapter import ThreadsSessionInvalidError
    from app.features.threads.growth.browser import GrowthBrowser

    class Adapter:
        closed = 0
        page = type("P", (), {"url": "https://www.threads.com/auth_platform/challengepicker/"})()

        def open_session(self, profile):
            return True

        def _page_needs_login(self):
            return True

        def close_session(self):
            Adapter.closed += 1

    with pytest.raises(ThreadsSessionInvalidError):
        with GrowthBrowser("/p", adapter_factory=Adapter):
            pass
    assert Adapter.closed == 1
