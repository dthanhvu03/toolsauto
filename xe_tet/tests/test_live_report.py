"""PLAN-143: báo cáo sau mỗi buổi live — ghi theo phút, chỉ đếm sự kiện TikTok khi đã kết nối, trang /report đọc lại được."""

from xe_tet.server import live_log, report


def test_live_log_counts_per_minute_and_phase_then_saves(tmp_path):
    log = live_log.LiveLog()
    db = live_log.LiveStore(tmp_path / "x.db")
    t0 = 1_800_000_000.0
    log.raw({"type": "comment", "uid": "a", "text": "Huế"}, t0)  # chưa kết nối: không ghi
    assert not log.active
    log.update(True, "kenh", t0, "BOARDING", 120)
    log.raw({"type": "comment", "uid": "a", "text": "Huế"}, t0 + 5, returning=True)
    log.raw({"type": "comment", "uid": "a", "text": "xe nào"}, t0 + 6, returning=True)
    log.raw({"type": "comment", "uid": "b", "text": "Cà Mau"}, t0 + 7, returning=False)
    log.raw({"type": "gift", "uid": "b", "diamonds": 30}, t0 + 8)
    log.raw({"type": "like", "uid": "c", "count": 15}, t0 + 9)
    log.game({"type": "ticket", "name": "A", "next": False}, t0 + 10)
    log.game({"type": "ticket", "name": "B", "next": True}, t0 + 11)
    log.game({"type": "ticket", "name": "A", "changed": True}, t0 + 12)  # đổi vé: không tính thêm
    log.update(True, "kenh", t0 + 70, "DRIVING", 150)
    log.raw({"type": "gift", "uid": "a", "diamonds": 100}, t0 + 75)
    log.game({"type": "dropoff", "people": [{"name": "A"}, {"name": "C"}]}, t0 + 80)
    log.update(True, "kenh", t0 + 81, "DROPOFF", 150)
    session, rows = log.take()
    m0, m1 = rows
    assert (m0["comments"], m0["uniq"], m0["xu"], m0["likes"], m0["seats"], m0["queued"]) == (3, 2, 30, 15, 1, 1)
    assert (m0["regulars"], m0["newcomers"], m0["phase"], m0["viewers"]) == (1, 1, "BOARDING", 120)
    assert (m1["xu"], m1["delivered"]) == (100, 2)
    assert session["uniq_commenters"] == 2 and session["uniq_gifters"] == 2 and session["uniq_boarded"] == 2
    log.saved(db.save(session, rows))
    log.raw({"type": "comment", "uid": "d", "text": "Huế"}, t0 + 90)
    log.update(True, "kenh", t0 + 90, "DRIVING", 90)
    db.save(*log.take())  # lần ghi sau cập nhật cùng buổi, không tạo buổi mới
    (s,) = db.sessions()
    assert s["comments"] == 4 and s["xu"] == 130 and s["peak_viewers"] == 150 and s["delivered"] == 2


def test_session_survives_short_reconnect_and_ends_after_gap(tmp_path):
    log = live_log.LiveLog()
    t0 = 1_800_000_000.0
    log.update(True, "kenh", t0, "BOARDING", 10)
    log.update(False, "kenh", t0 + 30, "BOARDING", 0)  # rớt mạng ngắn
    log.update(True, "kenh", t0 + 60, "BOARDING", 10)
    assert log.active and log.session["started"] == t0
    log.update(False, "kenh", t0 + 60 + live_log.SESSION_GAP + 1, "BOARDING", 0)
    session, _ = log.take()
    assert session["ended"] == t0 + 60 and not log.active  # hết buổi: ghi lần cuối rồi quên


def test_report_page_renders_sessions_minutes_and_notes(tmp_path):
    db = live_log.LiveStore(tmp_path / "x.db")
    assert "Chưa có buổi live" in report.render(db, None)
    log = live_log.LiveLog()
    t0 = 1_800_000_000.0
    for i, phase in enumerate(["BOARDING", "DRIVING", "DROPOFF"]):
        log.update(True, "kenh", t0 + i * 60, phase, 100 + i)
        log.raw({"type": "comment", "uid": f"u{i}", "text": "Huế"}, t0 + i * 60 + 1, returning=i == 0)
        log.raw({"type": "gift", "uid": f"u{i}", "diamonds": 10 * (i + 1)}, t0 + i * 60 + 2)
    db.save(*log.take())
    html = report.render(db, None, token="abc")
    assert "@kenh" in html and "<svg" in html and "Thả khách" in html and "Quà nhiều nhất lúc" in html
    assert "token=abc" in html  # link các buổi giữ mã điều khiển


def test_hub_counts_only_tiktok_events_while_connected(monkeypatch):
    from xe_tet.server import app as server
    hub = server.Hub()
    hub.handle({"type": "comment", "uid": "x", "name": "X", "text": "Huế"})  # bấm thử trên /control: không ghi
    hub.handle_tiktok({"type": "comment", "uid": "y", "name": "Y", "text": "Huế"})  # chưa kết nối: không ghi
    assert not hub.live.active
    hub.live.update(True, "kenh", 1_800_000_000.0, "BOARDING", 5)
    hub.handle({"type": "comment", "uid": "x", "name": "X", "text": "Nghệ An"})
    hub.handle_tiktok({"type": "comment", "uid": "y", "name": "Y", "text": "Cà Mau"})
    _, rows = hub.live.take()
    assert sum(r["comments"] for r in rows) == 1


def test_short_dropoff_scene_keeps_its_own_gifts(tmp_path):
    """Thả khách chỉ vài giây: quà lúc đó vẫn tính cho cảnh «Thả khách» (không bị phút «Xe chạy» nuốt mất)."""
    log = live_log.LiveLog()
    db = live_log.LiveStore(tmp_path / "x.db")
    t0 = 1_800_000_000.0
    log.update(True, "kenh", t0, "DRIVING", 10)
    log.update(True, "kenh", t0 + 50, "DROPOFF", 10)
    log.raw({"type": "gift", "uid": "a", "diamonds": 100}, t0 + 52)
    log.update(True, "kenh", t0 + 56, "DRIVING", 10)
    log.update(True, "kenh", t0 + 59, "DRIVING", 10)
    session, rows = log.take()
    assert rows[0]["phase"] == "DRIVING"  # cả phút vẫn là «xe chạy»
    assert session["phases"]["DROPOFF"]["xu"] == 100 and session["phases"]["DROPOFF"]["seconds"] == 6
    db.save(session, rows)
    html = report.render(db, None)
    assert "Thả khách" in html.split("Theo cảnh")[1]


def test_comments_saved_classified_and_exported(tmp_path):
    """Anh 03/11 «tải dữ liệu bình luận về để xem mình nên xử lý những trường hợp nào»: lưu từng câu + game hiểu là gì; báo cáo
    gom câu game chưa làm gì / câu hỏi phải hỏi AI; tải CSV."""
    log = live_log.LiveLog()
    db = live_log.LiveStore(tmp_path / "x.db")
    t0 = 1_800_000_000.0
    log.update(True, "kenh", t0, "BOARDING", 50)
    for i, (uid, text) in enumerate([("a", "Huế"), ("b", "xe nào"), ("c", "chào cả nhà"), ("d", "Chào cả nhà!"),
                                     ("e", "tặng quà sao vậy"), ("f", "ủa sao xe hổng chạy")]):
        log.raw({"type": "comment", "uid": uid, "name": uid.upper(), "text": text}, t0 + i)
    sid = db.save(*log.take())
    db.save_comments(sid, log.take_comments())
    rows = db.comments(sid)
    assert [r["kind"] for r in rows] == ["province", "where", "chat", "chat", "question", "question"]
    html = report.render(db, sid)
    assert "Câu game chưa làm gì" in html and "chào cả nhà" in html.lower() and "comments.csv" in html
    csv_text = report.comments_csv(db, sid)
    assert csv_text.startswith("﻿") and "chào cả nhà" in csv_text and "Gõ tỉnh (đặt vé)" in csv_text
