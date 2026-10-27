"""
Test lớp phụ đề (ADR-016). Không gọi Whisper thật, không gọi ffmpeg thật
trừ khi có mock. Điểm nối `_apply_post_layers` với setting tắt phải trả về
đúng đường dẫn cũ và không đụng subtitle_layer.
"""
from __future__ import annotations

import os
import subprocess
import unicodedata

import pytest
import pysubs2

from app.features.viral_intake import subtitle_layer
from app.features.viral_intake.reup_processor import ReupProcessor



SEGMENTS = [
    {"start": 0.5, "end": 2.0, "text": "Xin chào các bạn"},
    {
        "start": 2.0,
        "end": 8.0,
        "text": "Hôm nay mình sẽ chia sẻ một mẹo nhỏ giúp da sáng mịn hơn chỉ sau ba ngày dùng thử",
    },
]


# ─── (a) build_ass ───


def test_build_ass_style_and_wrapping(tmp_path):
    out = tmp_path / "t.ass"
    path = subtitle_layer.build_ass(SEGMENTS, str(out), max_chars=22)
    assert path == str(out)
    assert out.is_file()

    subs = pysubs2.load(str(out))
    style = subs.styles["Default"]
    assert style.fontname == "Be Vietnam Pro"
    assert style.alignment == pysubs2.Alignment.BOTTOM_CENTER
    assert style.bold is True
    assert style.outline == 3.0
    assert style.shadow == 1.0
    assert style.marginv == 260
    assert subs.info["PlayResX"] == "1080"
    assert subs.info["PlayResY"] == "1920"

    events = list(subs.events)
    # Segment 1 nguyên vẹn, đúng thời gian
    assert events[0].text == "Xin chào các bạn"
    assert events[0].start == 500
    assert events[0].end == 2000

    # Mọi dòng ≤ max_chars, mỗi event ≤ 2 dòng
    for ev in events:
        lines = ev.text.split("\\N")
        assert 1 <= len(lines) <= 2
        for line in lines:
            assert len(line) <= 22, line

    # Segment 2 (79 ký tự) buộc phải tách nhiều event, chia đều 2.0→8.0 liên tục
    tail = events[1:]
    assert len(tail) >= 2
    assert tail[0].start == 2000
    assert tail[-1].end == 8000
    for prev, nxt in zip(tail, tail[1:]):
        assert prev.end == nxt.start
    joined = " ".join(ev.text.replace("\\N", " ") for ev in tail)
    assert joined == SEGMENTS[1]["text"]


def test_build_ass_normalizes_nfc(tmp_path):
    # "ệ" dạng tách (e + U+0302 + U+0323) phải thành một codepoint NFC (U+1EC7) trong file ASS
    decomposed = "Việt Nam"
    assert len(decomposed) == 10
    out = tmp_path / "nfc.ass"
    subtitle_layer.build_ass([{"start": 0, "end": 1, "text": decomposed}], str(out))
    subs = pysubs2.load(str(out))
    assert subs.events[0].text == "Việt Nam"


# ─── (b) escape path ───


def test_escape_filter_path_windows():
    assert subtitle_layer._escape_filter_path("C:\\a b\\x.ass") == "'C\\:/a b/x.ass'"
    assert subtitle_layer._escape_filter_path("/srv/x.ass") == "'/srv/x.ass'"


# ─── (c) apply với transcript rỗng ───


def test_apply_returns_false_without_segments(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(subtitle_layer, "transcribe_words", lambda *a, **k: [])
    monkeypatch.setattr(
        subtitle_layer, "burn", lambda *a, **k: calls.append("burn") or True
    )
    out = tmp_path / "out.mp4"
    assert subtitle_layer.apply(str(tmp_path / "in.mp4"), str(out)) is False
    assert not out.exists()
    assert calls == []
    assert not (tmp_path / "out.sub.tmp.ass").exists()


# ─── (d) apply khi ffmpeg ném lỗi → False, không raise, không để rác ───


def test_apply_swallows_ffmpeg_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(subtitle_layer, "transcribe_words", lambda *a, **k: SEGMENTS)

    def _boom(*a, **k):
        raise OSError("ffmpeg exploded")

    monkeypatch.setattr(subprocess, "run", _boom)
    out = tmp_path / "out.mp4"
    assert subtitle_layer.apply(str(tmp_path / "in.mp4"), str(out), fonts_dir=str(tmp_path)) is False
    assert not out.exists()
    assert not (tmp_path / "out.sub.tmp.ass").exists()


def test_burn_returns_false_on_nonzero_exit(tmp_path, monkeypatch):
    class _R:
        returncode = 1
        stderr = "bad"
        stdout = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())
    ass = tmp_path / "x.ass"
    ass.write_text("[Script Info]\n", encoding="utf-8")
    assert subtitle_layer.burn(str(tmp_path / "in.mp4"), str(ass), str(tmp_path / "o.mp4"), fonts_dir=str(tmp_path)) is False


# ─── (e) điểm nối: setting tắt ⇒ đường đi cũ y nguyên ───


def test_post_layers_disabled_keeps_path_and_skips_layer(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: False)

    def _must_not_call(*a, **k):
        raise AssertionError("subtitle_layer.apply must not be called when disabled")

    monkeypatch.setattr(subtitle_layer, "apply", _must_not_call)
    monkeypatch.setattr(ReupProcessor, "_get_video_info", staticmethod(_must_not_call))

    current = str(tmp_path / "video_reup.mp4")
    metrics: dict = {}
    result = ReupProcessor._apply_post_layers(current, current, page_url=None, metrics=metrics)
    assert result == current
    assert metrics == {
        "dub_enabled": False, "subtitle_enabled": False,
        "audio_voice_enabled": False, "audio_music_enabled": False,
    }
    assert not os.path.exists(current + ".with_sub.tmp.mp4")


def test_post_layers_enabled_but_layer_fails_keeps_previous(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.subtitle_enabled")
    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: default)
    monkeypatch.setattr(subtitle_layer, "apply", lambda *a, **k: False)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )

    current = str(tmp_path / "video_reup.mp4")
    metrics: dict = {}
    assert ReupProcessor._apply_post_layers(current, current, metrics=metrics) == current
    assert metrics["subtitle_enabled"] is True
    assert metrics["subtitle_applied"] is False


def test_post_layers_enabled_success_promotes_tmp(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.subtitle_enabled")
    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: default)

    current = tmp_path / "video_reup.mp4"
    current.write_bytes(b"old")

    def _fake_apply(inp, out, **kw):
        assert kw == {"font_size": 64, "margin_v": 260, "segments": None}
        with open(out, "wb") as fh:
            fh.write(b"x" * (ReupProcessor.MIN_OUTPUT_BYTES + 1))
        return True

    monkeypatch.setattr(subtitle_layer, "apply", _fake_apply)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    metrics: dict = {}
    result = ReupProcessor._apply_post_layers(str(current), str(current), metrics=metrics)
    assert result == str(current)
    assert metrics["subtitle_applied"] is True
    assert current.stat().st_size > 3  # đã bị thay bằng file có phụ đề
    assert not (tmp_path / "video_reup.mp4.with_sub.tmp.mp4").exists()


# ─── (f) lớp âm thanh nối cùng điểm ───


def test_post_layers_audio_reads_hook_text_and_promotes(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings
    from app.features.viral_intake import audio_layer

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.audio_voice_enabled")
    monkeypatch.setattr(runtime_settings, "get_str", lambda key, default="", db=None: default)
    monkeypatch.setattr(subtitle_layer, "apply", lambda *a, **k: (_ for _ in ()).throw(AssertionError("subtitle off")))

    current = tmp_path / "video_reup.mp4"
    current.write_bytes(b"old")
    seen: dict = {}

    def _fake_audio(inp, out, **kw):
        seen.update(kw)
        with open(out, "wb") as fh:
            fh.write(b"x" * (ReupProcessor.MIN_OUTPUT_BYTES + 1))
        return True

    monkeypatch.setattr(audio_layer, "apply", _fake_audio)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    metrics: dict = {"hook_text": "Xem ngay nhé"}
    result = ReupProcessor._apply_post_layers(str(current), str(current), metrics=metrics)
    assert result == str(current)
    assert metrics["audio_applied"] is True
    assert seen["voice_text"] == "Xem ngay nhé"
    assert seen["music_dir"] is None  # nhạc tắt
    assert seen["voice_engine"] == "auto"
    assert not (tmp_path / "video_reup.mp4.with_audio.tmp.mp4").exists()


def test_doan_nhac_bi_bo_va_khong_chay_phu_de(tmp_path, monkeypatch):
    kept = subtitle_layer.keep_speech_segments(
        [
            {"start": 0.0, "end": 1.0, "text": "la la", "no_speech_prob": 0.6},
            {"start": 1.0, "end": 2.0, "text": "nhạc lặp", "compression_ratio": 2.5},
            {"start": 2.0, "end": 3.0, "text": "không có điểm"},
        ]
    )
    assert [seg["text"] for seg in kept] == ["không có điểm"]

    calls: list[str] = []
    monkeypatch.setattr(
        subtitle_layer,
        "transcribe_words",
        lambda *a, **k: [
            {"start": 0.0, "end": 1.0, "text": "la la", "no_speech_prob": 0.9},
        ],
    )
    monkeypatch.setattr(
        subtitle_layer, "burn", lambda *a, **k: calls.append("burn") or True
    )
    out = tmp_path / "out.mp4"
    assert subtitle_layer.apply(str(tmp_path / "in.mp4"), str(out)) is False
    assert not out.exists()
    assert calls == []


def test_loi_noi_duoc_giu_khi_canh_nhac():
    kept = subtitle_layer.keep_speech_segments(
        [
            {"start": 0.0, "end": 1.5, "text": "hôm nay đi câu", "no_speech_prob": 0.2},
            {"start": 1.5, "end": 3.0, "text": "nhạc nền", "no_speech_prob": 0.9},
        ]
    )
    assert [seg["text"] for seg in kept] == ["hôm nay đi câu"]


def test_post_layers_audio_fail_keeps_previous(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings
    from app.features.viral_intake import audio_layer

    monkeypatch.setattr(runtime_settings, "get_bool", lambda key, default=False, db=None: key == "reup.audio_music_enabled")
    monkeypatch.setattr(runtime_settings, "get_str", lambda key, default="", db=None: default)
    monkeypatch.setattr(audio_layer, "apply", lambda *a, **k: False)
    monkeypatch.setattr(
        ReupProcessor, "_get_video_info", staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920})
    )
    current = str(tmp_path / "video_reup.mp4")
    metrics: dict = {}
    assert ReupProcessor._apply_post_layers(current, current, metrics=metrics) == current
    assert metrics["audio_applied"] is False


# ─── (g) Whisper Hallucination Filtering (R1, R2, R3) ───


# Group A: Accented, unaccented, uppercase, lowercase, punctuation, and bracket variants
@pytest.mark.parametrize(
    "junk",
    [
        "Ghiền Mì Gõ",
        "ghiền mì gõ",
        "GHIÈN MÌ GÕ",
        "Ghien Mi Go",
        "ghien mi go",
        "GHIEN MI GO",
        "ghiền mì-gõ",
        "ghien_mi_go",
        "#ghienmigo",
        "[Ghiền Mì Gõ]!",
        "(ghien mi go)",
        "LaLa School",
        "lala school",
        "LALA SCHOOL",
        "La La School",
        "la la school",
        "la-la school",
        "#lalaschool",
        "bấm subscribe",
        "BẤM SUBSCRIBE",
        "bam subscribe",
        "BAM SUBSCRIBE",
        "subscribe",
        "Subscribe",
        "SUBSCRIBE",
        "subcribe",
        "bấm nút subscribe",
        "nhấn đăng ký kênh",
        "đăng ký kênh",
        "ĐĂNG KÝ KÊNH",
        "dang ky kenh",
        "DANG KY KENH",
        "đăng kí kênh",
        "dang ki kenh",
        "like and share",
        "Like and Share",
        "LIKE AND SHARE",
        "like & share",
        "Like & Share",
        "like va share",
        "nhớ like and share và đăng ký kênh nhé",
        "Đăng ký kênh để ủng hộ tụi mình nhé",
        "[nhạc]",
        "(âm nhạc)",
        "[tiếng vỗ tay]",
    ],
)
def test_hallucination_variants_completely_dropped(junk):
    # Verify clean_hallucinations_from_text returns empty
    assert subtitle_layer.clean_hallucinations_from_text(junk) == ""
    # Verify filter_hallucination_segments completely drops segment
    segs = [{"start": 0.0, "end": 2.0, "text": junk}]
    assert subtitle_layer.filter_hallucination_segments(segs) == []
    # Verify keep_speech_segments completely drops segment
    assert subtitle_layer.keep_speech_segments(segs) == []


def test_hallucination_nfd_decomposed_completely_dropped():
    decomposed = unicodedata.normalize("NFD", "Ghiền Mì Gõ")
    assert subtitle_layer.clean_hallucinations_from_text(decomposed) == ""
    segs = [{"start": 0.0, "end": 2.0, "text": decomposed}]
    assert subtitle_layer.filter_hallucination_segments(segs) == []
    assert subtitle_layer.keep_speech_segments(segs) == []


# Group B: Zero false positives: verify everyday Vietnamese phrases are NOT modified
@pytest.mark.parametrize(
    "benign",
    [
        "Ăn mì tôm rất ngon",
        "Tôi đi gõ cửa phòng",
        "Tôi thích ăn mì gõ ven đường",
        "Thủ tục đăng ký kết hôn tại phường",
        "Hồ sơ đăng ký xét tuyển đại học",
        "Đăng ký xe máy cần những giấy tờ gì",
        "Em bé học trường tiểu học rất ngoan",
        "Bác nông dân gánh lúa qua con kênh nhỏ",
        "Bấm nút màu đỏ để bật quạt",
        "Bấm chuông gọi cửa",
        "Video này đạt mười nghìn like trên mạng xã hội",
        "Đăng ký khóa học tiếng Anh cấp tốc",
        "Trường học này có xe đưa đón học sinh",
        "Tiếng đàn gõ nhịp rất vui tai",
        "Hôm nay tôi đi ăn bát mì tôm gõ cửa gọi bạn",
    ],
)
def test_zero_false_positives_on_benign_vietnamese(benign):
    # Text is untouched
    assert subtitle_layer.clean_hallucinations_from_text(benign) == benign
    # Segment is preserved with original text and timestamps
    segs = [{"start": 1.0, "end": 3.5, "text": benign}]
    res = subtitle_layer.filter_hallucination_segments(segs)
    assert len(res) == 1
    assert res[0]["text"] == benign
    assert res[0]["start"] == 1.0 and res[0]["end"] == 3.5


# Group C: Mixed dialogue pruning: excise junk phrase, preserve timestamps and real dialogue
def test_mixed_dialogue_pruning_preserves_timestamps():
    segs = [
        {
            "start": 0.0,
            "end": 4.0,
            "text": "Xin chào các bạn Ghiền Mì Gõ hôm nay chúng ta cùng vào bếp",
        },
        {
            "start": 4.0,
            "end": 8.0,
            "text": "Mẫu đầm này rất xinh, nhớ like and share nha",
        },
        {
            "start": 8.0,
            "end": 12.0,
            "text": "Hôm nay tại LaLa School chúng ta cùng học nấu ăn",
        },
        {
            "start": 12.0,
            "end": 15.0,
            "text": "Hãy để lại bình luận và nhớ bấm subscribe nhé",
        },
        {
            "start": 15.0,
            "end": 18.0,
            "text": "Ghiền Mì Gõ hôm nay hướng dẫn mẹo hay, nhớ like and share nhé",
        },
    ]
    cleaned = subtitle_layer.filter_hallucination_segments(segs)
    assert len(cleaned) == 5
    assert cleaned[0]["text"] == "Xin chào các bạn hôm nay chúng ta cùng vào bếp"
    assert cleaned[0]["start"] == 0.0 and cleaned[0]["end"] == 4.0
    assert cleaned[1]["text"] == "Mẫu đầm này rất xinh"
    assert cleaned[1]["start"] == 4.0 and cleaned[1]["end"] == 8.0
    assert cleaned[2]["text"] == "Hôm nay tại chúng ta cùng học nấu ăn"
    assert cleaned[2]["start"] == 8.0 and cleaned[2]["end"] == 12.0
    assert cleaned[3]["text"] == "Hãy để lại bình luận"
    assert cleaned[3]["start"] == 12.0 and cleaned[3]["end"] == 15.0
    assert cleaned[4]["text"] == "Hôm nay hướng dẫn mẹo hay"
    assert cleaned[4]["start"] == 15.0 and cleaned[4]["end"] == 18.0


# Group D: Pure BGM / pure hallucination video: mock transcribe_words -> apply returns False, burn NEVER called
def test_apply_pure_bgm_all_hallucinations_returns_false_and_no_burn(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(
        subtitle_layer,
        "transcribe_words",
        lambda *a, **k: [
            {"start": 0.0, "end": 2.0, "text": "Ghiền Mì Gõ"},
            {"start": 2.0, "end": 4.0, "text": "LaLa School"},
            {"start": 4.0, "end": 6.0, "text": "Đăng ký kênh để ủng hộ tụi mình nhé"},
        ],
    )
    monkeypatch.setattr(subtitle_layer, "burn", lambda *a, **k: calls.append("burn") or True)
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"dummy_in")
    out = tmp_path / "out.mp4"

    res = subtitle_layer.apply(str(inp), str(out))
    assert res is False
    assert calls == []  # burn must NEVER be called
    assert not out.exists()
    assert not (tmp_path / "out.sub.tmp.ass").exists()


# Group E: Mixed segments ASS generation: verify ASS file events contain ONLY clean subtitles
def test_apply_mixed_segments_burns_only_clean_subtitles(tmp_path, monkeypatch):
    calls: list[dict] = []
    captured_events: list[str] = []

    def _fake_burn(inp, ass, out, **kw):
        calls.append({"inp": inp, "ass": ass, "out": out})
        subs = pysubs2.load(ass)
        for ev in subs.events:
            captured_events.append(ev.text)
        with open(out, "wb") as f:
            f.write(b"x" * 2048)
        return True

    monkeypatch.setattr(
        subtitle_layer,
        "transcribe_words",
        lambda *a, **k: [
            {"start": 0.0, "end": 2.0, "text": "Ghiền Mì Gõ"},
            {"start": 2.0, "end": 5.0, "text": "Xin chào các bạn like and share"},
            {"start": 5.0, "end": 8.0, "text": "Chúc mọi người một ngày vui vẻ"},
        ],
    )
    monkeypatch.setattr(subtitle_layer, "burn", _fake_burn)
    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"dummy_in")
    out = tmp_path / "out.mp4"

    res = subtitle_layer.apply(str(inp), str(out))
    assert res is True
    assert len(calls) == 1
    # Check ASS events
    assert len(captured_events) > 0
    all_sub_text = " ".join(ev.replace("\\N", " ") for ev in captured_events)
    assert "Xin chào các bạn" in all_sub_text
    assert "Chúc mọi người một ngày vui vẻ" in all_sub_text
    assert "Ghiền Mì Gõ" not in all_sub_text
    assert "like and share" not in all_sub_text


# Group F: ReupProcessor post-layers test with pure BGM: verify original video is preserved
def test_reup_processor_post_layers_pure_bgm_keeps_original_video(tmp_path, monkeypatch):
    from app.core import settings as runtime_settings

    monkeypatch.setattr(
        runtime_settings,
        "get_bool",
        lambda key, default=False, db=None: key == "reup.subtitle_enabled",
    )
    monkeypatch.setattr(runtime_settings, "get_int", lambda key, default=0, db=None: default)
    # Mock transcribe_words with pure hallucinations
    monkeypatch.setattr(
        subtitle_layer,
        "transcribe_words",
        lambda *a, **k: [
            {"start": 0.0, "end": 2.0, "text": "LaLa School"},
            {"start": 2.0, "end": 4.0, "text": "bấm subscribe"},
        ],
    )
    monkeypatch.setattr(
        ReupProcessor,
        "_get_video_info",
        staticmethod(lambda p: {"duration": 10.0, "width": 1080, "height": 1920}),
    )

    current = tmp_path / "video_reup.mp4"
    current.write_bytes(b"original_video_content")
    metrics: dict = {}
    result = ReupProcessor._apply_post_layers(str(current), str(current), metrics=metrics)
    assert result == str(current)
    assert metrics["subtitle_enabled"] is True
    assert metrics["subtitle_applied"] is False
    assert current.read_bytes() == b"original_video_content"
    assert not (tmp_path / "video_reup.mp4.with_sub.tmp.mp4").exists()


# ─── (h) Adversarial Verification Suite (47 Cases) ───

ADVERSARIAL_HALLUCINATIONS = [
    # 1_Obfuscation
    pytest.param("ghiền... mì... gõ", id="1_Obfuscation_dots_ghien_mi_go"),
    pytest.param("ghiền. mì. gõ", id="1_Obfuscation_dot_space_ghien_mi_go"),
    pytest.param("ghiền, mì, gõ", id="1_Obfuscation_comma_ghien_mi_go"),
    pytest.param("ghiền / mì / gõ", id="1_Obfuscation_slash_ghien_mi_go"),
    pytest.param("---ghien mi go---", id="1_Obfuscation_dash_ghien_mi_go"),
    pytest.param("[GHIỀN MÌ GÕ]", id="1_Obfuscation_bracket_upper_ghien"),
    pytest.param("(bấm subscribe kênh!)", id="1_Obfuscation_parens_subscribe"),
    pytest.param("like   &&   share", id="1_Obfuscation_double_amp_like_share"),
    pytest.param("like... and... share", id="1_Obfuscation_dots_like_share"),
    pytest.param("lala... school", id="1_Obfuscation_dots_lala_school"),
    pytest.param("đăng ký... kênh", id="1_Obfuscation_dots_dang_ky_kenh"),
    pytest.param("ghiền mỳ gõ", id="1_Obfuscation_orthography_y_ghien_my_go"),
    # 2_MultiChain
    pytest.param(
        "ghiền mì gõ lala school bấm subscribe đăng ký kênh like and share",
        id="2_MultiChain_full_chain",
    ),
    pytest.param(
        "--- [ghiền mì gõ] ... lala school ... (đăng ký kênh) && like and share! ---",
        id="2_MultiChain_noisy_chain",
    ),
    # 3_Diacritics
    pytest.param(unicodedata.normalize("NFC", "Ghiền Mì Gõ"), id="3_Diacritics_nfc_ghien_mi_go"),
    pytest.param(unicodedata.normalize("NFD", "Ghiền Mì Gõ"), id="3_Diacritics_nfd_ghien_mi_go"),
    pytest.param("ghiên mì gõ", id="3_Diacritics_partial_accent_ghien"),
    pytest.param("GHIỀN MÌ GÕ", id="3_Diacritics_upper_accent_ghien"),
    # 5_Punctuation_Emoji
    pytest.param("", id="5_Punctuation_Emoji_empty_str"),
    pytest.param("   \t\n   ", id="5_Punctuation_Emoji_whitespace_str"),
    pytest.param("... ,,, --- !!! ???", id="5_Punctuation_Emoji_punct_symbols"),
    pytest.param("...", id="5_Punctuation_Emoji_triple_dots"),
    pytest.param(
        "🔥 [Ghiền Mì Gõ] 👍 Bấm subscribe kênh ❤️",
        id="5_Punctuation_Emoji_emoji_with_junk",
    ),
]


@pytest.mark.parametrize("text", ADVERSARIAL_HALLUCINATIONS)
def test_adversarial_hallucination_cases_dropped(text):
    assert subtitle_layer.clean_hallucinations_from_text(text) == "", (
        f"Expected empty string for hallucination text: {repr(text)}"
    )
    segs = [{"start": 0.0, "end": 2.0, "text": text}]
    assert subtitle_layer.filter_hallucination_segments(segs) == [], (
        f"Expected segment to be dropped completely for text: {repr(text)}"
    )


def test_adversarial_pure_emoji_safe():
    # Pure emoji handled safely without crash and produces no dialogue
    res = subtitle_layer.clean_hallucinations_from_text("😀🎉🔥")
    assert res == "", f"Expected pure emoji to return empty string, got: {repr(res)}"


ADVERSARIAL_BENIGN_CASES = [
    pytest.param("Tôi ăn mì gói mỗi sáng", id="4_BenignStress_benign_mi_1"),
    pytest.param("Sợi mì dai và nước dùng ngọt thanh", id="4_BenignStress_benign_mi_2"),
    pytest.param("Anh ấy gõ bàn phím rất nhanh", id="4_BenignStress_benign_go_1"),
    pytest.param("Tôi nghe tiếng gõ cửa lúc nửa đêm", id="4_BenignStress_benign_go_2"),
    pytest.param("Tôi thích ăn mì gõ lề đường Sài Gòn", id="4_BenignStress_benign_mi_go_trap"),
    pytest.param("Thủ tục đăng ký kết hôn rất đơn giản", id="4_BenignStress_benign_dang_ky_1"),
    pytest.param("Tôi vừa đi đăng ký xe máy mới", id="4_BenignStress_benign_dang_ky_2"),
    pytest.param("Giấy chứng nhận đăng ký doanh nghiệp", id="4_BenignStress_benign_nhan_dang_ky_1"),
    pytest.param(
        "Nơi tiếp nhận đăng ký hộ khẩu thường trú",
        id="4_BenignStress_benign_nhan_dang_ky_2",
    ),
    pytest.param(
        "Nhà trường tiếp nhận đăng ký nhập học",
        id="4_BenignStress_benign_nhan_dang_ky_3",
    ),
    pytest.param("Con kênh xanh xanh chảy qua đồng lúa", id="4_BenignStress_benign_kenh_1"),
    pytest.param("Kênh VTV1 đang phát sóng thời sự", id="4_BenignStress_benign_kenh_2"),
    pytest.param("Bài viết này nhận được rất nhiều like", id="4_BenignStress_benign_like_1"),
    pytest.param("Tôi like chiếc áo màu xanh này", id="4_BenignStress_benign_like_2"),
    pytest.param("Bạn share tài liệu học tập giúp mình với", id="4_BenignStress_benign_share_1"),
    pytest.param("Họ share bài viết này lên nhiều hội nhóm", id="4_BenignStress_benign_share_2"),
    pytest.param("Em đi đến trường học mỗi sáng", id="4_BenignStress_benign_truong_hoc_1"),
    pytest.param(
        "Trường học thân thiện học sinh tích cực",
        id="4_BenignStress_benign_truong_hoc_2",
    ),
    pytest.param("Sau đó bạn bấm đăng ký tài khoản", id="4_BenignStress_benign_app_tutorial_1"),
    pytest.param(
        "Bấm nút đăng ký an toàn trên ứng dụng",
        id="4_BenignStress_benign_app_tutorial_2",
    ),
    pytest.param("Người dùng nhấn đăng ký nhanh chóng", id="4_BenignStress_benign_app_tutorial_3"),
]


@pytest.mark.parametrize("expected_text", ADVERSARIAL_BENIGN_CASES)
def test_adversarial_benign_speech_preserved(expected_text):
    assert subtitle_layer.clean_hallucinations_from_text(expected_text) == expected_text, (
        f"Benign text was modified: {repr(expected_text)}"
    )
    segs = [{"start": 1.0, "end": 3.0, "text": expected_text}]
    cleaned = subtitle_layer.filter_hallucination_segments(segs)
    assert len(cleaned) == 1
    assert cleaned[0]["text"] == expected_text
    assert cleaned[0]["start"] == 1.0 and cleaned[0]["end"] == 3.0


@pytest.mark.parametrize(
    ("input_text", "expected_content"),
    [
        (
            "Chào mọi người (Ghiền Mì Gõ) hôm nay trời đẹp",
            "Chào mọi người hôm nay trời đẹp",
        ),
        (
            "Chào mọi người [Ghiền Mì Gõ] hôm nay trời đẹp",
            "Chào mọi người hôm nay trời đẹp",
        ),
    ],
    ids=["6_MixedExcision_parens_in_middle", "6_MixedExcision_brackets_in_middle"],
)
def test_adversarial_mixed_excision_no_empty_brackets(input_text, expected_content):
    cleaned = subtitle_layer.clean_hallucinations_from_text(input_text)
    assert "(" not in cleaned and ")" not in cleaned, (
        f"Empty parentheses left in cleaned string: {repr(cleaned)}"
    )
    assert "[" not in cleaned and "]" not in cleaned, (
        f"Empty brackets left in cleaned string: {repr(cleaned)}"
    )
    assert expected_content in cleaned, (
        f"Expected content {repr(expected_content)} not found in {repr(cleaned)}"
    )


def test_adversarial_filter_hallucination_segments_probe():
    seg_tests = [
        {"start": 0.0, "end": 2.0, "text": "ghiền... mì... gõ"},
        {"start": 2.0, "end": 4.0, "text": "like   &&   share"},
        {"start": 4.0, "end": 6.0, "text": "... ,,, --- !!! ???"},
        {"start": 6.0, "end": 8.0, "text": "Giấy chứng nhận đăng ký doanh nghiệp"},
    ]
    filtered_segs = subtitle_layer.filter_hallucination_segments(seg_tests)
    assert len(filtered_segs) == 1, (
        f"Expected exactly 1 surviving segment, got {len(filtered_segs)}: {repr(filtered_segs)}"
    )
    assert filtered_segs[0]["text"] == "Giấy chứng nhận đăng ký doanh nghiệp"
    assert filtered_segs[0]["start"] == 6.0
    assert filtered_segs[0]["end"] == 8.0


# ─── (i) Outro CTA Stress Suite (34 Cases) ───

OUTRO_CTA_STRESS_CASES = [
    # Part 1: Verify All 19 Previous Failure Cases (Iteration 1 Defects)
    pytest.param("ghiền... mì... gõ", "", id="it1_fix_dots_ghien_mi_go"),
    pytest.param("ghiền. mì. gõ", "", id="it1_fix_dot_space_ghien_mi_go"),
    pytest.param("ghiền, mì, gõ", "", id="it1_fix_comma_ghien_mi_go"),
    pytest.param("ghiền / mì / gõ", "", id="it1_fix_slash_ghien_mi_go"),
    pytest.param("ghiền mỳ gõ", "", id="it1_fix_orthography_y_ghien_my_go"),
    pytest.param("like   &&   share", "", id="it1_fix_double_amp_like_share"),
    pytest.param("like... and... share", "", id="it1_fix_dots_like_share"),
    pytest.param("lala... school", "", id="it1_fix_dots_lala_school"),
    pytest.param("đăng ký... kênh", "", id="it1_fix_dots_dang_ky_kenh"),
    pytest.param(
        "Bấm nút đăng ký an toàn trên ứng dụng",
        "Bấm nút đăng ký an toàn trên ứng dụng",
        id="it1_fix_amp_an_toan",
    ),
    pytest.param(
        "Nhà trường tiếp nhận đăng ký nhập học",
        "Nhà trường tiếp nhận đăng ký nhập học",
        id="it1_fix_amp_nhap_hoc",
    ),
    pytest.param(
        "Người dùng nhấn đăng ký nhanh chóng",
        "Người dùng nhấn đăng ký nhanh chóng",
        id="it1_fix_amp_nhanh_chong",
    ),
    pytest.param(
        "Giấy chứng nhận đăng ký doanh nghiệp",
        "Giấy chứng nhận đăng ký doanh nghiệp",
        id="it1_fix_benign_doanh_nghiep",
    ),
    pytest.param(
        "Nơi tiếp nhận đăng ký hộ khẩu thường trú",
        "Nơi tiếp nhận đăng ký hộ khẩu thường trú",
        id="it1_fix_benign_ho_khau",
    ),
    pytest.param(
        "Sau đó bạn bấm đăng ký tài khoản",
        "Sau đó bạn bấm đăng ký tài khoản",
        id="it1_fix_benign_tai_khoan",
    ),
    pytest.param("... ,,, --- !!! ???", "", id="it1_fix_punct_noise"),
    pytest.param("...", "", id="it1_fix_triple_dots"),
    pytest.param(
        "Chào mọi người (Ghiền Mì Gõ) hôm nay trời đẹp",
        "Chào mọi người hôm nay trời đẹp",
        id="it1_fix_bracket_parens",
    ),
    pytest.param(
        "Chào mọi người [Ghiền Mì Gõ] hôm nay trời đẹp",
        "Chào mọi người hôm nay trời đẹp",
        id="it1_fix_bracket_square",
    ),
    # Part 2: Novel Adversarial Challenge Cases (Iteration 2 Stress)
    # Issue 1: Outro CTA combinations with 'bấm' / 'nhấn' before 'like and share'
    pytest.param("bấm like và share", "", id="it2_cta_bam_like_va_share"),
    pytest.param("nhấn like và share", "", id="it2_cta_nhan_like_va_share"),
    pytest.param("bấm like share", "", id="it2_cta_bam_like_share"),
    pytest.param("Bấm like và share để ủng hộ kênh!", "", id="it2_cta_bam_like_share_outro"),
    pytest.param("Hãy bấm like và share để ủng hộ kênh nhé!", "", id="it2_cta_hay_bam_like_share_outro"),
    pytest.param("Đừng quên bấm like và share giúp mình nhé!", "", id="it2_cta_dung_quen_bam_like_share"),
    pytest.param(
        "Các bạn hãy bấm like và share để ủng hộ kênh nha!",
        "",
        id="it2_cta_cac_ban_hay_bam_like_share",
    ),
    pytest.param("Mọi người hãy bấm like và share nha!", "", id="it2_cta_moi_nguoi_hay_bam_like_share"),
    # Issue 2: Chained CTAs with 'like' alone + subscription action
    pytest.param("like và đăng ký kênh", "", id="it2_chain_like_dang_ky_kenh"),
    pytest.param("bấm like và đăng ký kênh", "", id="it2_chain_bam_like_dang_ky_kenh"),
    pytest.param("nhớ like và đăng ký kênh", "", id="it2_chain_nho_like_dang_ky_kenh"),
    pytest.param("like và subscribe", "", id="it2_chain_like_subscribe"),
    pytest.param("bấm like và subscribe", "", id="it2_chain_bam_like_subscribe"),
    # Issue 3: Obfuscation with multiple repeated ampersands
    pytest.param("like &&&& share", "", id="it2_obf_quad_amp"),
]


@pytest.mark.parametrize(("input_text", "expected_text"), OUTRO_CTA_STRESS_CASES)
def test_outro_cta_stress_cases(input_text, expected_text):
    assert subtitle_layer.clean_hallucinations_from_text(input_text) == expected_text


def test_outro_cta_segment_filtering_debris():
    seg_debris_test = [
        {"start": 0.0, "end": 2.0, "text": "Hãy bấm like và share để ủng hộ kênh nhé!"},
        {"start": 2.0, "end": 4.0, "text": "Bấm like và share để ủng hộ kênh!"},
        {"start": 4.0, "end": 6.0, "text": "like và đăng ký kênh"},
    ]
    filtered_debris = subtitle_layer.filter_hallucination_segments(seg_debris_test)
    assert len(filtered_debris) == 0, (
        f"Expected 0 segments kept, got {len(filtered_debris)}: {[s['text'] for s in filtered_debris]}"
    )


# ─── (j) Extended Adversarial & Pipeline Stress Suite ───

EXTENDED_COMPOUND_LEAD_CTAS = [
    pytest.param("Xin vui lòng bấm like và subscribe kênh", "", id="it3_cta_xin_vui_long_sub"),
    pytest.param("Xin vui lòng đăng ký kênh để ủng hộ mình nhé!", "", id="it3_cta_xin_vui_long_dang_ky"),
    pytest.param("Xin hãy bấm like và share", "", id="it3_cta_xin_hay_bam_like"),
    pytest.param("Các bạn đừng quên bấm like và subscribe nhé", "", id="it3_cta_cac_ban_dung_quen_sub"),
    pytest.param("Các bạn đừng quên đăng ký kênh nhé", "", id="it3_cta_cac_ban_dung_quen_dang_ky"),
    pytest.param("Mọi người đừng quên bấm like và subscribe", "", id="it3_cta_moi_nguoi_dung_quen_sub"),
    pytest.param("Mọi người đừng quên đăng ký kênh nha", "", id="it3_cta_moi_nguoi_dung_quen_dang_ky"),
    pytest.param("Cả nhà đừng quên đăng ký kênh nha", "", id="it3_cta_ca_nha_dung_quen_dang_ky"),
    pytest.param("Vui lòng hãy bấm like và share", "", id="it3_cta_vui_long_hay_bam_like"),
]


@pytest.mark.parametrize(("input_text", "expected_text"), EXTENDED_COMPOUND_LEAD_CTAS)
def test_extended_compound_lead_ctas(input_text, expected_text):
    assert subtitle_layer.clean_hallucinations_from_text(input_text) == expected_text


EXTENDED_MIXED_PUNCT_CASES = [
    pytest.param(
        "Bấm like và share để ủng hộ kênh! Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
        "Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
        id="it3_punct_leading_exclamation",
    ),
    pytest.param(
        "Bấm đăng ký kênh? Cùng theo dõi tiếp video nhé.",
        "Cùng theo dõi tiếp video nhé.",
        id="it3_punct_leading_question",
    ),
    pytest.param(
        "Hôm nay chúng ta sẽ nấu món phở bò truyền thống. Bấm like và share để ủng hộ kênh!",
        "Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
        id="it3_punct_trailing_dot_exclamation",
    ),
    pytest.param(
        "Hôm nay chúng ta sẽ nấu món phở bò truyền thống. Bấm like và share để ủng hộ kênh.",
        "Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
        id="it3_punct_trailing_double_dot",
    ),
    pytest.param(
        "Chào bạn! Nhớ like và subscribe kênh nhé. Hẹn gặp lại!",
        "Chào bạn! Hẹn gặp lại!",
        id="it3_punct_middle_exclamation_dot",
    ),
]


@pytest.mark.parametrize(("input_text", "expected_text"), EXTENDED_MIXED_PUNCT_CASES)
def test_extended_mixed_punct_cleanup(input_text, expected_text):
    assert subtitle_layer.clean_hallucinations_from_text(input_text) == expected_text


def test_extended_compound_lead_segment_filtering():
    bgm_leak_test = [
        {"start": 0.0, "end": 2.5, "text": "Xin vui lòng bấm like và subscribe kênh"},
        {"start": 2.5, "end": 5.0, "text": "Các bạn đừng quên đăng ký kênh nhé!"},
        {"start": 5.0, "end": 7.5, "text": "Mọi người đừng quên bấm like và subscribe"},
    ]
    filtered = subtitle_layer.filter_hallucination_segments(bgm_leak_test)
    assert len(filtered) == 0, f"Expected 0 segments kept, got {len(filtered)}: {filtered}"


EXTENDED_AUDIO_TAGS = [
    pytest.param("(tiếng cười)", "", id="audio_tag_tieng_cuoi_parens"),
    pytest.param("[tiếng cười]", "", id="audio_tag_tieng_cuoi_brackets"),
    pytest.param("(tieng cuoi)", "", id="audio_tag_tieng_cuoi_no_diacritic"),
    pytest.param("(music)", "", id="audio_tag_music_parens"),
    pytest.param("(nhạc nền)", "", id="audio_tag_nhac_nen_parens"),
]


@pytest.mark.parametrize(("input_text", "expected_text"), EXTENDED_AUDIO_TAGS)
def test_extended_audio_tags_cleaned(input_text, expected_text):
    assert subtitle_layer.clean_hallucinations_from_text(input_text) == expected_text


def test_extended_pure_bgm_laughter_skips_apply(tmp_path, monkeypatch):
    burn_called = []

    def _spy_burn(*args, **kwargs):
        burn_called.append(True)
        return True

    monkeypatch.setattr(
        subtitle_layer,
        "transcribe_words",
        lambda *a, **k: [{"start": 0.0, "end": 1.5, "text": "(tiếng cười)"}],
    )
    monkeypatch.setattr(subtitle_layer, "burn", _spy_burn)

    inp = tmp_path / "in.mp4"
    inp.write_bytes(b"dummy_in")
    out = tmp_path / "out.mp4"

    res = subtitle_layer.apply(str(inp), str(out))
    assert res is False
    assert len(burn_called) == 0
    assert not out.exists()


EXTENDED_BRACKET_PUNCT_DEBRIS = [
    pytest.param(
        "Chào bạn (bấm subscribe kênh!) hôm nay thế nào?",
        "Chào bạn hôm nay thế nào?",
        id="bracket_exclamation_subscribe",
    ),
    pytest.param(
        "Sản phẩm này [Ghiền Mì Gõ!] mang lại hiệu quả cao",
        "Sản phẩm này mang lại hiệu quả cao",
        id="bracket_exclamation_ghien_mi_go",
    ),
    pytest.param(
        "Đặc biệt (like & share!) rất hấp dẫn",
        "Đặc biệt rất hấp dẫn",
        id="bracket_exclamation_like_share",
    ),
    pytest.param(
        "Thời sự hôm nay [Ghiền Mì Gõ?] có gì mới",
        "Thời sự hôm nay có gì mới",
        id="bracket_question_ghien_mi_go",
    ),
]


@pytest.mark.parametrize(("input_text", "expected_text"), EXTENDED_BRACKET_PUNCT_DEBRIS)
def test_extended_bracket_punct_debris_cleaned(input_text, expected_text):
    cleaned = subtitle_layer.clean_hallucinations_from_text(input_text)
    assert cleaned == expected_text
    assert "( !)" not in cleaned and "[ !]" not in cleaned
    assert "( ?)" not in cleaned and "[ ?]" not in cleaned


def test_extended_ass_bracket_debris_free(tmp_path):
    test_seg = [{"start": 0.0, "end": 3.0, "text": "Đặc biệt (bấm subscribe kênh!) rất hấp dẫn"}]
    kept = subtitle_layer.keep_speech_segments(subtitle_layer.filter_hallucination_segments(test_seg))
    ass_path = tmp_path / "test_debris.ass"
    subtitle_layer.build_ass(kept, str(ass_path))
    subs = pysubs2.load(str(ass_path))
    assert len(subs.events) == 1
    event_text = subs.events[0].text
    assert "( !)" not in event_text
    assert "[ !]" not in event_text
    assert "Đặc biệt rất hấp dẫn" in event_text


def test_extended_nan_inf_timestamps_handled_safely(tmp_path):
    segs = [
        {"start": float("nan"), "end": 2.0, "text": "NaN segment"},
        {"start": 1.0, "end": float("inf"), "text": "Inf segment"},
        {"start": 0.0, "end": 2.0, "text": "Valid segment"},
    ]
    kept = subtitle_layer.keep_speech_segments(segs)
    assert len(kept) == 1
    assert kept[0]["text"] == "Valid segment"

    ass_path = tmp_path / "nan_inf.ass"
    subtitle_layer.build_ass([
        {"start": float("nan"), "end": 2.0, "text": "NaN"},
        {"start": 1.0, "end": float("inf"), "text": "Inf"},
    ], str(ass_path))
    assert ass_path.is_file()
    subs = pysubs2.load(str(ass_path))
    assert len(subs.events) == 0


def test_extended_pure_bgm_scaling_drops_all():
    phrases = ["[nhạc]", "(tiếng cười)", "ghiền mì gõ", "lala school", "bấm subscribe", "like and share"]
    for count in [1, 5, 10, 20, 50]:
        segs = [{"start": float(i * 2), "end": float(i * 2 + 1.8), "text": phrases[i % len(phrases)]} for i in range(count)]
        kept = subtitle_layer.keep_speech_segments(segs)
        assert len(kept) == 0, f"Expected 0 kept for count {count}, got {len(kept)}"




