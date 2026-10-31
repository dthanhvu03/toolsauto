"""
PLAN-120 — ngắt dòng phụ đề: mỗi câu một lượt, ≤ 2 dòng, ngắt theo dấu câu / cụm từ, không tách tên riêng, không lượt /
dòng một chữ, thời gian theo độ dài; đo bề rộng bằng font thật (hệ số libass).
"""
from __future__ import annotations

import pysubs2
import pytest

from app.features.studio import paths
from app.features.studio.render.subtitles import _Measure, _timed, build_ass, split_caption

FONT = str(paths.fonts_dir() / "BeVietnamPro-Bold.ttf")


def _chars(max_chars=22):
    return _Measure(font_file=None, font_size=64, width=1080, max_chars=max_chars)


def _font():
    return _Measure(font_file=FONT, font_size=64, width=1080, max_chars=22)


def _flat(events):
    return [" ⏎ ".join(rows) for rows in events]


def test_moi_cau_mot_luot_va_khong_tach_ten_rieng():
    m = _font()
    assert _flat(split_caption("Rất giàu lịch sử. Ấn tượng đầu rất tốt.", m)) == ["Rất giàu lịch sử.", "Ấn tượng đầu rất tốt."]
    flat = " | ".join(_flat(split_caption("Sân do John Allen từ Royal North Devon thiết kế. Do đó", m)))
    for name in ("John Allen", "Royal North Devon"):
        assert name in flat.replace(" ⏎ ", " ") and f"{name.split()[0]} ⏎" not in flat


def test_ngat_sau_dau_phay_dong_can_khong_chu_le():
    m = _chars(22)
    events = split_caption("Tập 91 trải nghiệm sân golf thay bạn, hôm nay chúng ta tới sân Kingsdown", m)
    rows = [r for e in events for r in e]
    assert all(len(r) <= 22 for r in rows) and all(len(r.split()) >= 2 for r in rows)
    assert all(len(e) <= 2 for e in events)
    assert any(r.endswith("bạn,") for r in rows)  # ngắt ngay sau dấu phẩy


def test_font_that_chu_rong_tinh_dung():
    m = _font()
    assert m.limit == pytest.approx(32.0)  # khung 1080 chứa ~42 ký tự, chặn ở READ_CAP cho dễ đọc
    assert m(["M" * 26]) > 1.25 * m(["a" * 26])  # đếm ký tự thì bằng nhau (26), đo font thì «M» rộng hơn hẳn


def test_thoi_gian_theo_do_dai_lien_mach():
    t = _timed([["một hai ba bốn năm sáu bảy"], ["tám chín"]], 10.0, 14.0)
    assert t[0][0] == 10.0 and t[-1][1] == 14.0 and t[0][1] == t[1][0]
    assert (t[0][1] - t[0][0]) > (t[1][1] - t[1][0]) >= 0.7  # lượt dài hiện lâu hơn, lượt ngắn vẫn ≥ 0,7 s


def test_build_ass_dung_font_va_khong_luot_mot_chu():
    lines = [{"start": 0.0, "end": 4.0, "text": "Rất giàu lịch sử. Ấn tượng đầu rất tốt. Tee box 1"},
             {"start": 4.0, "end": 9.0, "text": "Chưa rõ chơi muộn mùa hè ra sao, nhưng tôi phải chạy từ hố 12 về lại"}]
    ev = pysubs2.SSAFile.from_string(build_ass(lines, width=1080, height=1920, font_size=64, margin_v=260, max_chars=22,
                                               font_file=FONT)).events
    assert all(len(e.text.replace("\\N", " ").split()) >= 2 for e in ev)
    assert all(e.text.count("\\N") <= 1 for e in ev)
    assert ev[0].text == "Rất giàu lịch sử."
