"""
`/caidat` — xem / đổi cài đặt luồng video ngay trong Telegram.

Owner hỏi "mấy setting này setting ở tele được không" sau khi video bị cắt 1:30 mà phải mở web
mới tìm ra ô. Ghi bằng chính `upsert_setting` của web trên SQLite thật (validate, audit,
bust cache) rồi ĐỌC LẠI giá trị hiệu lực — không mock, không trả lại thứ Owner vừa gõ.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import settings as rs
from app.features.telegram_bot.command_handler import TelegramCommandHandler


class _Client:
    def __init__(self):
        self.msgs = []

    def send_message(self, text, reply_markup=None, **kw):
        self.msgs.append(text)

    @property
    def text(self):
        return " ".join(self.msgs)


@pytest.fixture
def bot(tmp_path, monkeypatch):
    import app.core.database.core as dbcore
    from app.core.database.models import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'c.sqlite'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(dbcore, "SessionLocal", factory)
    # cache của settings là toàn cục — xoá để test không thấy giá trị phiên trước
    monkeypatch.setattr(rs, "_cache_ts", 0.0)
    monkeypatch.setattr(rs, "_cache_values", {})
    monkeypatch.setattr(rs, "_push_config_value", lambda k, v: None)
    client = _Client()
    handler = TelegramCommandHandler(client)

    def run(*args):
        client.msgs.clear()
        handler.handle_command("caidat", list(args))
        return client.text

    run.factory = factory
    try:
        yield run
    finally:
        engine.dispose()


def test_khong_tham_so_thi_liet_ke_kem_gia_tri_hieu_luc(bot):
    text = bot()

    assert "dodai" in text and "90" in text and "0 = không cắt" in text
    assert "giugoc" in text and "caption" in text and "nguong" in text
    assert "/caidat dodai 0" in text, "phải chỉ cách đổi ngay trong tin"


def test_doi_do_dai_ve_0_thi_ghi_that_va_doc_lai(bot):
    text = bot("dodai", "0")

    assert "✅" in text and "= <b>0</b>" in text
    assert "Xử lý lại" in text, "video đã có thì không tự đổi — phải nói"
    with bot.factory() as db:
        assert rs.get_effective(db, "reup.max_duration_sec") == 0


def test_vuot_gioi_han_thi_tu_choi_va_noi_khoang(bot):
    text = bot("dodai", "9999")

    assert "⚠️" in text and "600" in text
    with bot.factory() as db:
        assert rs.get_effective(db, "reup.max_duration_sec") == 90, "không được ghi giá trị sai"


def test_khong_phai_so_thi_tu_choi(bot):
    assert "⚠️" in bot("dodai", "abc")


@pytest.mark.parametrize("raw,expect", [("tat", False), ("bật", True), ("off", False), ("1", True)])
def test_bool_nhan_tieng_viet(bot, raw, expect):
    text = bot("caption", raw)

    assert "✅" in text and ("bật" if expect else "tắt") in text
    with bot.factory() as db:
        assert rs.get_effective(db, "viral.auto_caption_on_ready") is expect


def test_bool_gia_tri_la_thi_bao(bot):
    assert "bật/tắt" in bot("caption", "maybe")


def test_ten_o_khong_co_thi_bao_va_chi_ve_danh_sach(bot):
    text = bot("khongco", "1")

    assert "Không có ô" in text and "/caidat" in text


def test_chi_ten_khong_gia_tri_thi_xem_mot_o(bot):
    text = bot("giugoc")

    assert "giugoc" in text and "Giữ file video gốc" in text and "✅" not in text


def test_nhan_ca_key_day_du(bot):
    text = bot("viral.min_views", "5000")

    assert "✅" in text
    with bot.factory() as db:
        assert rs.get_effective(db, "viral.min_views") == 5000


def test_help_nhac_caidat(bot):
    c = _Client()
    TelegramCommandHandler(c).handle_command("help")

    assert "/caidat" in c.text
