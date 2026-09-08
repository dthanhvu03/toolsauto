"""
ADR-024 mục 3 — UI cho trạng thái ``DUPLICATE`` (trùng nội dung ở tầng material).

Backend (``constants.ViralStatus.DUPLICATE``, 2 cột hash, ``dedup.py``, ``processor.py``,
migration) do agent khác làm song song, nên test này KHÔNG phụ thuộc nó: dựng ``item`` bằng
``SimpleNamespace`` theo đúng hợp đồng đã chốt trong ADR —
``status="DUPLICATE"`` + ``last_error="Trùng nội dung với #12 (pHash cách 3)"`` + không còn
file ``_reup`` (``has_reup=False``).

Khuôn render fragment lấy từ tests/test_material_caption_ui.py.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.main_templates import templates


DUP_ERROR = "Trùng nội dung với #12 (pHash cách 3)"


def _item(**over) -> SimpleNamespace:
    base = dict(
        id=68, platform="tiktok", url="https://t.tk/v68", title="Video demo",
        views=12345, status="DUPLICATE", thumbnail_url=None, last_error=DUP_ERROR,
        process_tries=0, ai_caption=None, ai_hashtags_list=[], ai_caption_at=None,
        ai_caption_error=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _render_row(item, has_reup: bool = False) -> str:
    return templates.get_template("fragments/viral_row.html").render(
        {"request": None, "item": item, "account_name": "—", "now": 0, "has_reup": has_reup}
    )


def _flat(html: str) -> str:
    """Bỏ khoảng trắng quanh thẻ để assert '>Trùng<' không phụ thuộc indent."""
    return re.sub(r"\s*([<>])\s*", r"\1", re.sub(r"\s+", " ", html))


def _table_source() -> str:
    src, _, _ = templates.env.loader.get_source(templates.env, "fragments/app_viral_table.html")
    return src


def _page_source() -> str:
    src, _, _ = templates.env.loader.get_source(templates.env, "pages/app_viral.html")
    return src


# ── (a) Badge "Trùng" — trung tính, không phải lỗi ───────────────────────────


def test_duplicate_row_shows_neutral_badge_with_vietnamese_label():
    html = _flat(_render_row(_item()))

    assert ">Trùng<" in html
    # Không dùng màu đỏ của FAILED — trùng là quyết định đúng của tool, không phải lỗi.
    assert "color-danger" not in html.split(">Trùng<")[0][-400:]
    assert ">Lỗi<" not in html


def test_duplicate_badge_title_carries_full_last_error():
    html = _render_row(_item())

    assert f'title="{DUP_ERROR}"' in html


def test_duplicate_row_shows_last_error_line_so_owner_sees_which_material():
    html = _render_row(_item())

    # Câu 37 ký tự → chưa bị cắt, Owner đọc thẳng được "#12".
    assert DUP_ERROR in html
    assert "#12" in html


def test_duplicate_long_last_error_is_truncated_around_40_chars():
    long_err = "Trùng nội dung với #12 (pHash cách 3) — khung 1.23s/2.46s/3.69s trùng khít"
    html = _render_row(_item(last_error=long_err))

    # Dòng nhỏ bị cắt quanh 40 ký tự (Jinja truncate: 40 - len("…") rồi nối "…").
    assert long_err[:39] + "…" in html
    # …nhưng title vẫn giữ nguyên câu đầy đủ (chỉ xuất hiện trong title, không ở dòng chữ).
    assert f'title="{long_err}"' in html
    assert html.count(long_err) == 2


def test_duplicate_without_last_error_still_readable():
    html = _flat(_render_row(_item(last_error=None)))

    assert ">Trùng<" in html
    assert "Trùng nội dung với video đã có" in html


def test_duplicate_last_error_is_html_escaped():
    html = _render_row(_item(last_error='Trùng với #9 <script>alert(1)</script>'))

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


# ── (b) Không có nút hành động vô nghĩa ──────────────────────────────────────


def test_duplicate_row_has_no_download_or_thumbnail_button():
    """File tải về đã bị xoá (ADR-024) ⇒ mọi nút dựa trên file phải biến mất."""
    html = _render_row(_item())

    assert "Tải file" not in html
    assert "Thumbnail" not in html
    assert f"/viral/68/reup-preview" not in html
    assert f"/viral/68/reup-thumb" not in html


def test_duplicate_row_has_no_caption_button():
    html = _render_row(_item())

    assert "Viết caption" not in html
    assert "/viral/68/caption" not in html
    assert "Caption AI" not in html


def test_duplicate_row_has_no_process_or_retry_button():
    html = _render_row(_item())

    assert "/viral/68/process" not in html
    assert "/viral/68/retry" not in html
    assert "Reup lại" not in html


def test_duplicate_row_keeps_delete_button():
    html = _render_row(_item())

    assert 'hx-post="/viral/68/delete"' in html
    assert 'hx-target="#viral-68"' in html


def test_duplicate_row_ignores_stale_has_reup_flag():
    """Nếu router còn thấy file cũ (cache/đua), hàng trùng vẫn không mời bấm gì dựa trên file."""
    html = _render_row(_item(), has_reup=True)

    assert "/viral/68/reup-preview" not in html
    assert "/viral/68/caption" not in html
    assert "Mở _reup.mp4" not in html


# ── (c) Không làm hỏng các trạng thái cũ ─────────────────────────────────────


def test_ready_row_still_has_download_and_thumbnail():
    html = _flat(_render_row(_item(status="READY", last_error=None), has_reup=True))

    assert ">Tải file<" in html
    assert ">Thumbnail<" in html
    assert 'download="viral_68_reup.mp4"' in html
    assert ">Trùng<" not in html


def test_ready_row_still_has_caption_button():
    html = _flat(_render_row(_item(status="READY", last_error=None), has_reup=True))

    assert ">Viết caption<" in html
    assert 'hx-post="/viral/68/caption"' in html


def test_failed_row_still_red_with_retry():
    html = _flat(_render_row(_item(status="FAILED", last_error="yt-dlp 403")))

    assert ">Lỗi<" in html
    assert 'hx-post="/viral/68/retry"' in html
    assert ">Trùng<" not in html


def test_new_row_still_has_process_button():
    html = _flat(_render_row(_item(status="NEW", last_error=None)))

    assert 'hx-post="/viral/68/process"' in html
    assert ">Trùng<" not in html


# ── (d) Chip đếm + bộ lọc ────────────────────────────────────────────────────


def test_table_fragment_has_duplicate_count_chip():
    html = templates.get_template("fragments/app_viral_table.html").render(
        {
            "request": None,
            "items": [],
            "status_counts": {"NEW": 1, "PROCESSING": 0, "DRAFTED": 2, "READY": 3,
                              "FAILED": 0, "DUPLICATE": 5},
            "page": 1, "total_pages": 1, "total": 0, "ffmpeg_ok": True,
        }
    )
    flat = _flat(html)

    assert ">Trùng 5<" in flat
    assert "document.getElementById('vStatus').value='DUPLICATE'" in html


def test_table_fragment_survives_backend_without_duplicate_key():
    """Backend chưa trả key DUPLICATE trong pipeline_banner ⇒ chip hiện 0, không vỡ."""
    html = templates.get_template("fragments/app_viral_table.html").render(
        {
            "request": None,
            "items": [],
            "status_counts": {"NEW": 1, "FAILED": 0},
            "page": 1, "total_pages": 1, "total": 0, "ffmpeg_ok": True,
        }
    )

    assert ">Trùng 0<" in _flat(html)


def test_table_fragment_empty_row_colspan_unchanged():
    src = _table_source()

    assert 'colspan="7"' in src
    assert 'colspan="8"' not in src


def test_status_filter_has_duplicate_option():
    src = _page_source()

    assert '<option value="DUPLICATE">Trùng</option>' in src
    # Không đụng các option cũ.
    assert '<option value="READY">Sẵn sàng đăng tay (READY)</option>' in src
    assert '<option value="FAILED">Lỗi (FAILED)</option>' in src


def test_page_keeps_status_select_id_and_endpoint():
    src = _page_source()

    assert 'id="vStatus"' in src
    assert "/app/viral/table?page=" in src
