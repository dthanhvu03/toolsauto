"""
ADR-021 mục 4 + 5 — UI "AI viết caption cho video READY".

Backend (``service.generate_caption_for_material``, 4 cột trên ``ViralMaterial``, migration) do
agent khác làm song song, nên test này KHÔNG phụ thuộc nó: monkeypatch một service giả đúng
chữ ký hợp đồng ``generate_caption_for_material(db, material_id, *, style=None) -> (ok, msg)``
và dựng ``item`` bằng SimpleNamespace cho phần render fragment.

Khuôn app/SQLite tạm lấy từ tests/test_viral_router_background.py.
"""
from __future__ import annotations

import json
import logging
import re
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database.core import get_db
from app.core.database.models import ViralMaterial
from app.features.viral_intake import router as viral_router
from app.features.viral_intake.service import ViralService
from app.main_templates import templates


# ── Khuôn app + service giả ──────────────────────────────────────────────────


@pytest.fixture
def session_factory(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'material_caption_ui.sqlite'}")
    ViralMaterial.__table__.create(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    try:
        yield factory
    finally:
        engine.dispose()


@pytest.fixture
def calls(monkeypatch):
    """Ghi lại lời gọi service thay vì chạy Whisper + LLM thật."""
    recorded: list[tuple] = []
    state = {"raise": None}

    def fake_generate(db, material_id, *, style=None):
        recorded.append(("generate_caption_for_material", db, material_id, style))
        if state["raise"]:
            raise RuntimeError(state["raise"])
        return True, f"fake caption #{material_id}"

    # raising=False: thuộc tính có thể chưa tồn tại khi backend chưa merge.
    monkeypatch.setattr(
        ViralService, "generate_caption_for_material", staticmethod(fake_generate), raising=False
    )
    return SimpleNamespace(recorded=recorded, state=state)


@pytest.fixture
def client(session_factory, monkeypatch, calls):
    app = FastAPI()
    app.include_router(viral_router.router)

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    # Task nền mở session riêng qua SessionLocal của router → trỏ về DB tạm.
    monkeypatch.setattr(viral_router, "SessionLocal", session_factory)
    return TestClient(app)


def _triggers(resp) -> dict:
    return json.loads(resp.headers["HX-Trigger"])


# ── (a) POST /viral/{id}/caption trả toast ngay ──────────────────────────────


def test_caption_accepts_immediately_with_toast_and_refresh(client, calls):
    resp = client.post("/viral/42/caption")

    assert resp.status_code == 204
    trig = _triggers(resp)
    assert trig["showMessage"]["type"] == "success"
    assert "Đang viết caption" in trig["showMessage"]["msg"]
    assert "#42" in trig["showMessage"]["msg"]
    assert trig["refreshViralTable"] is True
    # Bảng phải tự làm mới thêm vài nhịp (Whisper + LLM lâu hơn 1 request).
    assert trig["viralSourcesScanStarted"] is True


# ── (b) task nền: đúng material_id + style ───────────────────────────────────


def test_background_task_gets_material_id_and_style_none_when_form_empty(client, calls):
    client.post("/viral/7/caption")

    # TestClient chạy xong background task trước khi trả response → gọi đúng 1 lần.
    assert len(calls.recorded) == 1
    name, bg_db, material_id, style = calls.recorded[0]
    assert name == "generate_caption_for_material"
    assert material_id == 7
    assert style is None
    assert isinstance(bg_db, Session)


@pytest.mark.parametrize("raw", ["", "   ", "\n"])
def test_blank_style_variants_all_become_none(client, calls, raw):
    client.post("/viral/7/caption", data={"style": raw})

    assert calls.recorded[0][3] is None


def test_background_task_passes_style_when_form_has_one(client, calls):
    client.post("/viral/9/caption", data={"style": "short"})

    assert calls.recorded[0][2] == 9
    assert calls.recorded[0][3] == "short"


def test_background_uses_its_own_session(client, session_factory, calls):
    """Session của request đã đóng khi response trả về → task nền phải tự mở."""
    client.post("/viral/7/caption")

    bg_db = calls.recorded[0][1]
    assert isinstance(bg_db, Session)
    # Session nền đã được đóng lại bởi context manager của _generate_caption_in_background.
    assert not bg_db.is_active or bg_db.get_bind() is not None


# ── (c) service ném lỗi trong nền ⇒ vẫn 204, lỗi được log đủ stack ───────────


def test_background_failure_is_logged_not_swallowed(client, calls, caplog):
    calls.state["raise"] = "gemini 401 UNAUTHENTICATED"

    with caplog.at_level(logging.ERROR, logger=viral_router.__name__):
        resp = client.post("/viral/11/caption")

    assert resp.status_code == 204
    assert _triggers(resp)["showMessage"]["type"] == "success"
    rec = [r for r in caplog.records if "Lỗi viết caption nền" in r.getMessage()]
    assert rec and rec[0].exc_info
    assert "gemini 401 UNAUTHENTICATED" in str(rec[0].exc_info[1])


def test_missing_service_attribute_does_not_500(client, monkeypatch, caplog):
    """Backend chưa merge ⇒ AttributeError trong nền, request vẫn phải trả toast bình thường."""
    monkeypatch.delattr(ViralService, "generate_caption_for_material", raising=False)

    with caplog.at_level(logging.ERROR, logger=viral_router.__name__):
        resp = client.post("/viral/3/caption")

    assert resp.status_code == 204
    assert [r for r in caplog.records if "Lỗi viết caption nền" in r.getMessage()]


# ── (d) render fragment 3 trạng thái ─────────────────────────────────────────


def _item(**over) -> SimpleNamespace:
    base = dict(
        id=68, platform="tiktok", url="https://t.tk/v68", title="Video demo",
        views=12345, status="READY", thumbnail_url=None, last_error=None,
        process_tries=0, ai_caption=None, ai_hashtags_list=[], ai_caption_at=None,
        ai_caption_error=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _render(item, has_reup: bool = True) -> str:
    return templates.get_template("fragments/viral_row.html").render(
        {"request": None, "item": item, "account_name": "—", "now": 0, "has_reup": has_reup}
    )


def _flat(html: str) -> str:
    """Bỏ khoảng trắng quanh thẻ để assert '>Viết caption<' không phụ thuộc indent."""
    return re.sub(r"\s*([<>])\s*", r"\1", re.sub(r"\s+", " ", html))


def test_fragment_without_caption_shows_write_button(client):
    html = _flat(_render(_item()))

    assert ">Viết caption<" in html
    assert 'hx-post="/viral/68/caption"' in html
    assert 'hx-swap="none"' in html
    assert ">Sao chép<" not in html
    assert ">Thử lại<" not in html


def test_fragment_without_reup_has_no_caption_ui_at_all(client):
    """Chưa có file _reup thì không có gì để viết caption → không hiện nút."""
    html = _render(_item(status="NEW"), has_reup=False)

    assert "/viral/68/caption" not in html
    assert "Caption AI" not in html


def test_fragment_with_caption_shows_text_chips_and_buttons(client):
    item = _item(
        ai_caption="Bí quyết da đẹp mỗi ngày.\nChỉ 3 bước thôi!",
        ai_hashtags_list=["#dadep", "#skincare", "#reviewvn"],
    )
    raw = _render(item)
    html = _flat(raw)

    assert "Caption AI" in html
    assert "Bí quyết da đẹp mỗi ngày." in raw
    assert "line-clamp-2" in raw and "group-open/cap:line-clamp-none" in raw
    assert "<details" in raw and "<summary" in raw
    for tag in ("#dadep", "#skincare", "#reviewvn"):
        assert f">{tag}<" in html
    assert ">Sao chép<" in html
    assert ">Viết lại<" in html
    assert ">Viết caption<" not in html
    # Nút "Viết lại" dùng đúng endpoint caption.
    assert raw.count('hx-post="/viral/68/caption"') == 1


def test_copy_payload_is_caption_newline_hashtags_joined_by_space(client):
    item = _item(ai_caption="Dòng một\nDòng hai", ai_hashtags_list=["#a", "#b"])
    raw = _render(item)

    payload = _copy_payload(raw)
    assert payload == "Dòng một\nDòng hai\n#a #b"


def test_copy_payload_without_hashtags_is_caption_only(client):
    raw = _render(_item(ai_caption="Chỉ có caption", ai_hashtags_list=[]))

    assert _copy_payload(raw) == "Chỉ có caption"


def test_copy_helper_has_clipboard_and_execcommand_fallback(client):
    raw = _render(_item(ai_caption="x", ai_hashtags_list=[]))

    assert "navigator.clipboard.writeText" in raw
    assert "document.execCommand('copy')" in raw
    assert "Đã chép ✓" in raw
    assert "2000" in raw  # trả nhãn cũ sau 2 giây
    assert "window.viralCopyCaption = window.viralCopyCaption ||" in raw  # nhiều dòng → 1 hàm


def test_fragment_with_error_shows_truncated_error_and_retry(client):
    long_err = (
        "Chưa cấu hình key AI — vào .env đặt GEMINI_API_KEY (dạng AIza…) "
        "rồi chạy python manage.py ai check"
    )
    raw = _render(_item(ai_caption_error=long_err))
    html = _flat(raw)

    assert "Caption lỗi" in html
    assert ">Thử lại<" in html
    assert 'hx-post="/viral/68/caption"' in raw
    assert ">Viết caption<" not in html
    assert ">Sao chép<" not in html
    # title giữ lỗi đầy đủ, phần hiện ra bị cắt còn 60 ký tự.
    assert f'title="{long_err}"' in raw
    shown = _shown_error(raw)
    assert len(shown) == 60 and shown.endswith("…")
    assert long_err.startswith(shown[:-1])


def test_short_error_is_not_truncated(client):
    raw = _render(_item(ai_caption_error="Chưa có file _reup"))

    assert "Chưa có file _reup" in raw
    assert "…" not in _shown_error(raw)


def test_caption_and_error_together_show_caption_plus_warning_line(client):
    raw = _render(_item(ai_caption="Caption cũ", ai_caption_error="Viết lại hỏng: 429"))
    html = _flat(raw)

    assert ">Sao chép<" in html
    assert "Lần viết gần nhất lỗi:" in html
    assert "Viết lại hỏng: 429" in raw


# ── (e) caption có nháy / xuống dòng / emoji ⇒ HTML không vỡ ─────────────────


NASTY = 'Nó "đỉnh" thật\' — xem ngay 😍\n</script><img src=x onerror=alert(1)>\nGiá & chất lượng <5%'


def test_nasty_caption_is_escaped_in_html_body(client):
    raw = _render(_item(ai_caption=NASTY, ai_hashtags_list=["#a<b>", "#c&d"]))

    # Không lọt thẻ đóng script nào ngoài thẻ đóng thật của khối helper.
    assert raw.count("</script>") == 1
    assert "<img src=x" not in raw
    assert "&lt;/script&gt;" in raw or "\\u003c/script\\u003e" in raw
    assert "&amp;" in raw  # dấu & trong caption đã escape
    assert ">#a&lt;b&gt;<" in _flat(raw)


def test_nasty_caption_cannot_break_out_of_onclick_attribute(client):
    raw = _render(_item(ai_caption=NASTY, ai_hashtags_list=["#a"]))

    payload_json = _copy_json(raw)
    # tojson escape ' < > & → nháy đơn không thể đóng sớm thuộc tính onclick='...'
    assert "'" not in payload_json
    assert "<" not in payload_json and ">" not in payload_json
    assert "\\u0027" in payload_json and "\\u003c" in payload_json
    assert "\\n" in payload_json  # xuống dòng thành escape JSON, không phá thuộc tính
    # Nội dung giải mã lại vẫn đúng nguyên văn.
    assert json.loads(payload_json) == NASTY + "\n#a"


def test_emoji_survives_round_trip(client):
    raw = _render(_item(ai_caption="Đỉnh 😍🔥", ai_hashtags_list=[]))

    assert json.loads(_copy_json(raw)) == "Đỉnh 😍🔥"


def test_nasty_error_is_escaped_in_title_attribute(client):
    raw = _render(_item(ai_caption_error='Lỗi "lạ" <script>alert(1)</script>'))

    assert "<script>alert(1)" not in raw
    assert "&lt;script&gt;" in raw
    assert '&#34;' in raw or "&quot;" in raw  # nháy kép trong title đã escape


# ── helper đọc lại dữ liệu nhúng ─────────────────────────────────────────────


def _copy_json(html: str) -> str:
    m = re.search(r"onclick='window\.viralCopyCaption\(this, (.*?)\)'", html, re.S)
    assert m, "không tìm thấy onclick sao chép trong fragment"
    return m.group(1)


def _copy_payload(html: str) -> str:
    return json.loads(_copy_json(html))


def _shown_error(html: str) -> str:
    """Chuỗi lỗi thật sự in ra bảng (không phải trong thuộc tính title)."""
    m = re.search(
        r"<p[^>]*--color-danger[^>]*>\s*(?:Lần viết gần nhất lỗi:\s*)?(.*?)\s*</p>",
        html,
        re.S,
    )
    assert m, "không tìm thấy dòng lỗi caption trong fragment"
    return m.group(1)
