"""Kiểm chứng toàn diện thiết kế lại UI/UX Quản trị Cashback Bot.

Kiểm chứng 3 nguyên tắc UX cốt lõi:
1. Dùng editMessageText khi chuyển màn hình qua inline button (không spam tin nhắn mới),
   mọi trang con có nút ◀️ Tổng quan (PLAN-060: cấp 1 chỉ cần một nút vì Quay lại = Tổng quan).
2. Không để nút chưa dùng được dẫn đến màn hình vô nghĩa (không có nút kích hoạt tự động).
3. Các trang chứa tiền hiển thị ranh giới rõ ràng giữa "Đang áp dụng", "Bản nháp" và "Mô phỏng".
"""

from __future__ import annotations

from datetime import datetime, timezone

from cashback_bot.poller import process_updates
from tests.test_cashback_bot import FakeClient, payload, service

NOW = datetime(2026, 10, 23, 7, 0, tzinfo=timezone.utc)
ADMIN_ID = 777


def _admin_bot(tmp_path):
    client = FakeClient(payload())
    bot = service(tmp_path, client, admin_user_ids=frozenset({ADMIN_ID}))
    return bot, client


class MockTelegramWithEdit:
    def __init__(self):
        self.sent_messages = []
        self.edited_messages = []
        self.answered_callbacks = []
        self.edit_should_succeed = True

    def send_message(self, chat_id, html, reply_markup=None, **_kwargs):
        self.sent_messages.append({"chat_id": chat_id, "html": html, "markup": reply_markup})

    def edit_message_text(self, chat_id, message_id, html, reply_markup=None):
        if not self.edit_should_succeed:
            return False
        self.edited_messages.append(
            {"chat_id": chat_id, "message_id": message_id, "html": html, "markup": reply_markup}
        )
        return True

    def answer_callback(self, callback_query_id, *_args):
        self.answered_callbacks.append(callback_query_id)


class DummyAdminNotifier:
    def flush_pending(self, limit=10):
        pass

    def notify_link_sent(self, update_id):
        pass


def test_edit_message_text_used_on_callback_navigation(tmp_path):
    """UX Điểm 1: Callback query dùng editMessageText để cập nhật tin nhắn thay vì gửi mới."""
    bot, _client = _admin_bot(tmp_path)
    store = bot.repo
    tg = MockTelegramWithEdit()

    callback_update = {
        "update_id": 101,
        "callback_query": {
            "id": "query_rank_1",
            "data": "c:menu:rank",
            "from": {"id": ADMIN_ID},
            "message": {
                "message_id": 5555,
                "chat": {"id": ADMIN_ID, "type": "private"},
                "text": "menu",
            },
        },
    }

    process_updates(bot, tg, store, [callback_update], DummyAdminNotifier(), now=NOW)

    # Đã answer callback query để tắt loading spinner
    assert tg.answered_callbacks == ["query_rank_1"]

    # Đã gọi edit_message_text với đúng message_id của tin nhắn trước
    assert len(tg.edited_messages) == 1
    assert tg.edited_messages[0]["message_id"] == 5555
    assert tg.edited_messages[0]["chat_id"] == ADMIN_ID
    assert "Quản trị › <b>Hạng thành viên</b>" in tg.edited_messages[0]["html"]

    # KHÔNG gọi sendMessage tạo tin nhắn rác
    assert len(tg.sent_messages) == 0


def test_edit_message_text_fallback_to_send_if_edit_fails(tmp_path):
    """UX Điểm 1 (Safety): Nếu editMessageText thất bại (vd tin quá cũ), fallback sang sendMessage."""
    bot, _client = _admin_bot(tmp_path)
    store = bot.repo
    tg = MockTelegramWithEdit()
    tg.edit_should_succeed = False  # Giả lập editMessageText trả về False

    callback_update = {
        "update_id": 102,
        "callback_query": {
            "id": "query_sim_1",
            "data": "c:menu:sim",
            "from": {"id": ADMIN_ID},
            "message": {
                "message_id": 9999,
                "chat": {"id": ADMIN_ID, "type": "private"},
            },
        },
    }

    process_updates(bot, tg, store, [callback_update], DummyAdminNotifier(), now=NOW)

    assert len(tg.sent_messages) == 1
    assert "MÔ PHỎNG" in tg.sent_messages[0]["html"]


def test_all_six_sub_screens_have_back_and_home_navigation(tmp_path):
    """UX Điểm 1: Mọi trang con đều có nút ◀️ Tổng quan về c:menu:home và breadcrumb."""
    bot, _client = _admin_bot(tmp_path)

    sub_screens = [
        "c:menu:policy",  # 1. Chính sách cashback
        "c:menu:rank",    # 2. Hạng thành viên
        "c:menu:fee",     # 3. Thuế & phí dự phòng
        "c:menu:sim",     # 4. Mô phỏng tiền hoàn
        "c:menu:hist",    # 5. Lịch sử cấu hình
        "c:menu:copy",    # 6. Nội dung lệnh
    ]

    for screen_data in sub_screens:
        reply = bot.admin_panel.handle_callback(ADMIN_ID, screen_data, "private", NOW)
        assert reply.inline_keyboard is not None, f"Màn hình {screen_data} thiếu inline_keyboard"

        # Duyệt tất cả các nút để tìm nút Quay lại và Tổng quan
        buttons = [(btn[0], btn[1]) for row in reply.inline_keyboard for btn in row]
        button_labels = [label for label, _data in buttons]
        button_targets = [data for _label, data in buttons]

        assert ("◀️ Tổng quan", "c:menu:home") in buttons, f"Màn hình {screen_data} thiếu nút ◀️ Tổng quan"
        assert button_labels.count("◀️ Tổng quan") == 1, f"Màn hình {screen_data} có nút trùng việc"
        assert reply.text.startswith("⚙️ Quản trị › "), f"Màn hình {screen_data} thiếu breadcrumb"


def test_draft_collecting_screen_has_back_navigation(tmp_path):
    """UX Điểm 1: Bước nhập số có nút Hủy bản nháp; hủy xong quay về màn Hạng thành viên."""
    bot, _client = _admin_bot(tmp_path)
    reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:tier:BRONZE", "private", NOW)
    assert "đang lưu <b>60%</b>" in reply.text
    assert "từ 0 đến 70" in reply.text
    (label, cancel), = reply.inline_keyboard[0]
    assert label == "✖️ Hủy bản nháp"
    assert cancel.startswith("c:no:")
    done = bot.admin_panel.handle_callback(ADMIN_ID, cancel, "private", NOW)
    assert "Đã hủy bản nháp" in done.text
    assert "Quản trị › <b>Hạng thành viên</b>" in done.text
    assert done.toast == "Đã hủy bản nháp"
    assert bot.admin_panel._pending_count(NOW) == 0


def test_rank_screen_has_no_automatic_activation(tmp_path):
    """UX Điểm 2: Trang Hạng thành viên không có nút kích hoạt tự động vì chưa có dữ liệu đơn thật."""
    bot, _client = _admin_bot(tmp_path)
    reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:rank", "private", NOW)

    # Hiển thị tỷ lệ & quy tắc dự kiến
    assert "Đồng" in reply.text
    assert "Bạc" in reply.text
    assert "Vàng" in reply.text
    assert "Trần V1 là 70%" in reply.text
    assert "không có nút kích hoạt tự động" in reply.text

    # Kiểm tra toàn bộ nút trên màn hình: KHÔNG có nút kích hoạt tự động
    all_data = [data for row in reply.inline_keyboard for _label, data in row]
    for data in all_data:
        assert "activate" not in data.lower()
        assert "auto" not in data.lower()
        assert "enable" not in data.lower()
        assert "apply" not in data.lower()


def test_money_screens_have_clear_boundaries(tmp_path):
    """UX Điểm 3: Các trang chứa tiền phải có ranh giới rõ ràng: Đang áp dụng, Bản nháp, Mô phỏng."""
    bot, _client = _admin_bot(tmp_path)

    # 1. Hạng thành viên
    rank_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:rank", "private", NOW)
    assert "ĐANG ÁP DỤNG" in rank_reply.text
    assert "BẢN NHÁP" in rank_reply.text
    assert "MÔ PHỎNG" in rank_reply.text

    # 2. Thuế & phí dự phòng (ADR-047: áp dụng thật, không còn bản nháp)
    fee_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:fee", "private", NOW)
    assert "ĐANG ÁP DỤNG CHO KHÁCH" in fee_reply.text
    assert "MÔ PHỎNG" in fee_reply.text

    # 3. Chính sách cashback
    policy_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:policy", "private", NOW)
    assert "ĐANG ÁP DỤNG" in policy_reply.text
    assert "BẢN NHÁP" in policy_reply.text
    assert "MÔ PHỎNG" in policy_reply.text

    # 4. Mô phỏng tiền hoàn
    sim_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:sim", "private", NOW)
    assert "ĐANG ÁP DỤNG" in sim_reply.text
    assert "MÔ PHỎNG" in sim_reply.text
    assert "hoa hồng giả định, không phải lợi nhuận" in sim_reply.text


def test_six_screens_permission_and_modes(tmp_path):
    """UX Kết luận: Phân định quyền hạn rõ ràng cho 6 màn hình.
    - Chính sách, Hạng thành viên, Thuế/phí: Có thể tạo bản nháp.
    - Mô phỏng: Chỉ dùng để tính thử.
    - Lịch sử cấu hình & Nội dung lệnh: Chế độ xem (read-only).
    """
    bot, _client = _admin_bot(tmp_path)

    # 1. Hạng thành viên: có nút tạo bản nháp Đồng, Bạc, Vàng
    rank_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:rank", "private", NOW)
    rank_datas = [d for r in rank_reply.inline_keyboard for _l, d in r]
    assert "c:tier:BRONZE" in rank_datas
    assert "c:tier:SILVER" in rank_datas
    assert "c:tier:GOLD" in rank_datas

    # 2. Thuế & phí: một nút đổi mức áp dụng (wizard xem trước rồi mới áp dụng)
    fee_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:fee", "private", NOW)
    fee_datas = [d for r in fee_reply.inline_keyboard for _l, d in r]
    assert fee_datas == ["c:rs:new", "c:menu:home"]

    # 3. Mô phỏng: chỉ để xem & tính thử, KHÔNG có nút hành động thay đổi
    sim_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:sim", "private", NOW)
    sim_datas = [d for r in sim_reply.inline_keyboard for _l, d in r]
    for d in sim_datas:
        # Chỉ có nút điều hướng và chọn hoa hồng giả định (PLAN-076), không nút ghi.
        assert d == "c:menu:home" or d.startswith("c:sim:")

    # 4. Lịch sử: chế độ xem (read-only)
    hist_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:hist", "private", NOW)
    hist_datas = [d for r in hist_reply.inline_keyboard for _l, d in r]
    for d in hist_datas:
        assert d in {"c:menu:home"}

    # 5. Nội dung lệnh: chế độ xem (read-only)
    copy_reply = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:copy", "private", NOW)
    copy_datas = [d for r in copy_reply.inline_keyboard for _l, d in r]
    for d in copy_datas:
        assert d in {"c:menu:home"}
    assert "V1 chỉ cho xem danh sách lệnh" in copy_reply.text


def test_dau_phay_trong_cau_chu_khong_bi_doi_thanh_dau_cham(tmp_path):
    """PLAN-060 P0: chỉ số tiền dùng dấu chấm ngăn nghìn, câu chữ và % thập phân giữ dấu phẩy."""
    bot, _client = _admin_bot(tmp_path)
    rank = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:rank", "private", NOW)
    fee = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:fee", "private", NOW)
    sim = bot.admin_panel.handle_callback(ADMIN_ID, "c:menu:sim", "private", NOW)
    # PLAN-076: «admin còn» là phần dư sau dự phòng phí 980đ và thuế 10.000đ (V1.1 admin chịu).
    assert "Đồng 60%: hoàn 60.000đ · admin còn 29.020đ" in rank.text
    assert "không phải thuế phải nộp. Link đã gửi giữ số cũ" in fee.text
    assert "0,98%" in fee.text
    assert "0.98%" not in fee.text
    assert "-980đ" in fee.text
    assert "Đồng 60%: hoàn 60.000đ · admin còn 29.020đ" in sim.text

    bot.admin_panel.handle_callback(ADMIN_ID, "c:tier:SILVER", "private", NOW)
    preview = bot.admin_panel.consume_text(ADMIN_ID, "66", NOW)
    assert "Trước: hoàn 65.000đ, admin còn 24.020đ" in preview.text


def test_tong_quan_khong_lap_dong(tmp_path):
    bot, _client = _admin_bot(tmp_path)
    home = bot.admin_panel.menu(ADMIN_ID, NOW)
    assert home.text.count("Đối soát") <= 1
    assert "Tỷ lệ ước tính hiện tại" not in home.text
    assert "Báo giá đang chạy: V1.1 · 70% hoa hồng ước tính" in home.text and "Việc cần làm" in home.text


def test_nut_het_hieu_luc_van_giu_nut_dieu_huong(tmp_path):
    """PLAN-060 P0: callback lỗi sửa đè tin cũ, phải còn nút để thoát."""
    bot, _client = _admin_bot(tmp_path)
    for data in ("c:ok:999:abcd1234", "c:no:999:abcd1234", "c:xyz"):
        reply = bot.admin_panel.handle_callback(ADMIN_ID, data, "private", NOW)
        targets = [d for row in reply.inline_keyboard for _label, d in row]
        assert "c:menu:home" in targets, data
