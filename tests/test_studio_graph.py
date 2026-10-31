"""
ADR-061 — spec và lệnh render là hàm thuần: kiểm không cần ffmpeg, không cần DB.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.features.studio.compose.templates import ComposeInput, basic, own_footage, reup_dub, speech_ranges
from app.features.studio.render.graph import Media, SpecError, build, clip_ranges
from app.features.studio.render.subtitles import apply_edits, build_ass, shift_lines
from app.features.studio.spec import ProjectSpec

MEDIA = {
    1: Media(path="/v/a.mp4", kind="video", duration=60.0, has_audio=True),
    2: Media(path="/v/mute.mp4", kind="video", duration=10.0, has_audio=False),
    3: Media(path="/i/logo.png", kind="image", duration=0.0, has_audio=False),
    4: Media(path="/m/music.mp3", kind="audio", duration=30.0, has_audio=True),
    5: Media(path="/d/voice.flac", kind="audio", duration=60.0, has_audio=True),
    6: Media(path="/d/bg.flac", kind="audio", duration=60.0, has_audio=True),
}


def _build(spec: dict, **kw):
    return build(
        ProjectSpec.model_validate(spec), MEDIA, output="/out/x.mp4", workdir="/w",
        font_file="/f/Bold.ttf", fonts_dir="/f", **kw,
    )


def _graph(plan) -> str:
    return plan.argv[plan.argv.index("-filter_complex") + 1]


# ── spec ──


def test_spec_tu_choi_truong_la_de_trinh_edit_go_sai_ten_la_biet_ngay():
    with pytest.raises(ValidationError):
        ProjectSpec.model_validate({"clips": [{"asset": 1}], "subtitle": {"enabled": True}})


def test_spec_tu_choi_clip_end_truoc_start():
    with pytest.raises(ValidationError):
        ProjectSpec.model_validate({"clips": [{"asset": 1, "start": 5, "end": 5}]})


def test_spec_can_it_nhat_mot_clip():
    with pytest.raises(ValidationError):
        ProjectSpec.model_validate({"clips": []})


def test_asset_ids_gom_clip_track_logo_tieng_clip():
    spec = ProjectSpec.model_validate(
        {"clips": [{"asset": 1, "audio": [{"asset": 5}]}], "audio": {"tracks": [{"asset": 4}]}, "logo": {"asset": 3}}
    )
    assert spec.asset_ids() == {1, 3, 4, 5}


# ── khoảng cắt ──


def test_clip_end_qua_dai_cat_ve_het_asset_va_anh_mac_dinh_3_giay():
    spec = ProjectSpec.model_validate({"clips": [{"asset": 1, "start": 50, "end": 90}, {"asset": 3}]})
    assert clip_ranges(spec, MEDIA) == [(1, 50, 60.0), (3, 0.0, 3.0)]


def test_clip_audio_hoac_asset_khong_co_thi_bao_loi_spec():
    with pytest.raises(SpecError):
        clip_ranges(ProjectSpec.model_validate({"clips": [{"asset": 4}]}), MEDIA)
    with pytest.raises(SpecError):
        clip_ranges(ProjectSpec.model_validate({"clips": [{"asset": 99}]}), MEDIA)


# ── lệnh ffmpeg ──


def test_mot_luot_encode_hai_clip_noi_bang_concat():
    plan = _build({"clips": [{"asset": 1, "start": 3, "end": 13}, {"asset": 1, "start": 20, "end": 25}]})
    g = _graph(plan)
    assert plan.duration == pytest.approx(15.0)
    assert plan.argv.count("-c:v") == 1
    assert plan.argv[plan.argv.index("-ss") + 1] == "3"
    assert "concat=n=2:v=1:a=1[vcat][acat]" in g
    assert plan.argv[plan.argv.index("-t", plan.argv.index("-filter_complex")) + 1] == "15"


def test_video_khong_tieng_hoac_original_0_thi_chen_im_lang_dung_do_dai():
    g = _graph(_build({"clips": [{"asset": 2}]}))
    assert "aevalsrc=0:c=stereo:s=48000:d=10[a0]" in g
    g = _graph(_build({"clips": [{"asset": 1, "end": 5}], "audio": {"original": 0}}))
    assert "[0:a]" not in g and "d=5[a0]" in g


def test_fit_crop_va_pad():
    assert "crop=1080:1920" in _graph(_build({"canvas": {"fit": "crop"}, "clips": [{"asset": 1}]}))
    assert "pad=1080:1920" in _graph(_build({"canvas": {"fit": "pad"}, "clips": [{"asset": 1}]}))


def test_chu_hook_ghi_nguon_di_qua_textfile_khong_nhung_chuoi_vao_filter():
    plan = _build({
        "clips": [{"asset": 1, "end": 10}],
        "texts": [{"text": "Mẹo: 3 giây, đừng bỏ lỡ!", "end": 3}],
        "credit": "Nguồn: @tac'gia",
    })
    g = _graph(plan)
    assert plan.files["/w/text0.txt"] == "Mẹo: 3 giây, đừng bỏ lỡ!"
    assert plan.files["/w/credit.txt"] == "Nguồn: @tac'gia"
    assert "Mẹo" not in g and "tac'gia" not in g
    assert "enable='between(t,0,3)'" in g and "expansion=none" in g


def test_logo_phai_la_anh_va_overlay_sau_cung():
    g = _graph(_build({"clips": [{"asset": 1}], "logo": {"asset": 3, "pos": "br"}}))
    assert "[vpost][logo]overlay=W-w-40:H-h-40" in g and g.index("[vpost]") < g.index("[vout]")
    with pytest.raises(SpecError):
        _build({"clips": [{"asset": 1}], "logo": {"asset": 1}})


def test_track_nhac_lap_tre_va_tron_khong_chuan_hoa_am_luong():
    plan = _build({
        "clips": [{"asset": 1, "end": 20}],
        "audio": {"original": 1, "tracks": [{"asset": 4, "volume": 0.12, "loop": True, "start": 1.5}]},
    })
    g = _graph(plan)
    i = plan.argv.index("/m/music.mp3")
    assert plan.argv[i - 3:i - 1] == ["-stream_loop", "-1"]
    assert "volume=0.12,adelay=1500|1500,atrim=0:20[t0]" in g
    assert "amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]" in g


def test_track_khong_co_tieng_bao_loi():
    with pytest.raises(SpecError):
        _build({"clips": [{"asset": 1}], "audio": {"tracks": [{"asset": 2}]}})


def test_phu_de_tu_transcript_ghi_file_ass_va_goi_filter_ass():
    plan = _build(
        {"clips": [{"asset": 1, "start": 10, "end": 20}], "subtitles": {"enabled": True}},
        transcripts={1: [{"start": 11, "end": 13, "text": "xin chào"}]},
    )
    assert "ass='/w/subs.ass':fontsdir='/f'" in _graph(plan)
    assert "xin chào" in plan.files["/w/subs.ass"]
    assert "0:00:01.00,0:00:03.00" in plan.files["/w/subs.ass"]


def test_phu_de_bat_ma_khong_co_loi_thi_khong_them_filter():
    plan = _build({"clips": [{"asset": 1}], "subtitles": {"enabled": True}}, transcripts={1: []})
    assert "ass=" not in _graph(plan) and not plan.files


# ── phụ đề ──


def test_doi_loi_thoai_theo_doan_cat_qua_hai_clip():
    lines = [
        {"start": 1, "end": 4, "text": "bị cắt mất"},
        {"start": 9, "end": 12, "text": "nửa trong nửa ngoài"},
        {"start": 31, "end": 33, "text": "đoạn hai"},
    ]
    out = shift_lines([(1, 10, 20), (1, 30, 40)], {1: lines})
    assert out == [
        {"start": 0, "end": 2, "text": "nửa trong nửa ngoài"},
        {"start": 11, "end": 13, "text": "đoạn hai"},
    ]


def test_sua_tay_doi_chu_va_chuoi_rong_bo_dong():
    lines = [{"start": 0, "end": 1, "text": "a"}, {"start": 1, "end": 2, "text": "b"}]
    assert apply_edits(lines, {0: "A sửa", 1: "  "}) == [{"start": 0, "end": 1, "text": "A sửa"}]


def test_ass_giu_kieu_chu_reup_cu_va_ngat_toi_da_hai_dong():
    ass = build_ass(
        [{"start": 0, "end": 4, "text": "một hai ba bốn năm sáu bảy tám chín mười mười một mười hai"}],
        width=1080, height=1920, font_size=64, margin_v=260, max_chars=12,
    )
    assert "Be Vietnam Pro" in ass and "PlayResY: 1920" in ass
    events = [row for row in ass.splitlines() if row.startswith("Dialogue:")]
    assert len(events) >= 2 and all(row.count("\\N") <= 1 for row in events)


# ── P2: tiếng của clip (lồng tiếng) ──


def test_clip_co_audio_thi_lay_tieng_tu_file_do_cung_moc_giay():
    plan = _build({"clips": [
        {"asset": 3, "end": 2},
        {"asset": 1, "start": 10, "end": 20, "audio": [{"asset": 5}, {"asset": 6, "volume": 0.4}]},
    ]})
    g = _graph(plan)
    for path in ("/d/voice.flac", "/d/bg.flac"):
        i = plan.argv.index(path)
        assert plan.argv[i - 5:i - 1] == ["-ss", "10", "-t", "10"]
    assert "[2:a]" in g and "[3:a]" in g and "[1:a]" not in g, "không dùng tiếng gốc của clip đã lồng"
    assert "volume=0.4,apad,atrim=0:10[a1s1]" in g
    assert "[a1s0][a1s1]amix=inputs=2:duration=first:normalize=0[a1]" in g
    assert "aevalsrc=0:c=stereo:s=48000:d=2[a0]" in g


def test_tieng_clip_phai_la_asset_audio():
    with pytest.raises(SpecError):
        _build({"clips": [{"asset": 1, "audio": [{"asset": 2}]}]})


# ── P2: mẫu ──


def _inp(**kw) -> ComposeInput:
    base = dict(asset_id=1, duration=30.0, has_audio=True, has_transcript=True, credit="@a")
    return ComposeInput(**{**base, **kw})


def test_basic_khong_dot_phu_de_tieng_khac():
    assert basic(_inp(transcript_lang="zh")).subtitles.enabled is False
    assert basic(_inp(transcript_lang="vi")).subtitles.enabled is True
    assert basic(_inp(transcript_lang=None)).subtitles.enabled is True  # không rõ thì cứ đốt
    assert basic(_inp(transcript_lang="en", params={"subtitle_lang": ""})).subtitles.enabled is True


def test_reup_dub_dung_tieng_long_cho_clip_chinh_khong_dung_intro():
    dub = {"ok": True, "voice_asset": 5, "background_asset": 6, "background_volume": 0.15}
    spec = reup_dub(_inp(transcript_lang="zh", dub=dub, intro_asset_id=9, params={"background_volume": 2}))
    intro, main = spec.clips
    assert intro.asset == 9 and intro.audio == []
    assert [(a.asset, a.volume) for a in main.audio] == [(5, 1.0), (6, 0.3)]
    assert spec.subtitles.enabled and spec.subtitles.source == "dub"
    assert spec.credit == "Nguồn: @a"


def test_reup_dub_khong_long_duoc_thi_nhu_basic():
    spec = reup_dub(_inp(transcript_lang="vi", dub={"ok": False, "reason": "đã đúng ngôn ngữ đích"}))
    assert spec.clips[0].audio == [] and spec.subtitles.source == "transcript" and spec.subtitles.enabled


def test_khoang_lang_thanh_cac_doan_co_tieng_noi_pad():
    silences = [{"start": 0.0, "end": 1.0}, {"start": 5.0, "end": 5.3}, {"start": 8.0, "end": 10.0}]
    assert speech_ranges(12.0, silences, min_gap=0.6, pad=0.1) == [(0.9, 8.1), (9.9, 12.0)]


def test_qua_nhieu_doan_thi_gop_khe_ngan_nhat():
    silences = [{"start": i + 0.5, "end": i + 0.5 + (0.7 if i % 2 else 0.9)} for i in range(0, 200, 2)]
    ranges = speech_ranges(200.0, silences, min_gap=0.6, pad=0.0)
    assert len(ranges) <= 60 and ranges[0][0] == 0.0 and ranges[-1][1] == 200.0


def test_own_footage_cat_khoang_lang_bo_ghi_nguon_va_ap_max_len_sau_khi_cat():
    silences = [{"start": 2.0, "end": 4.0}, {"start": 10.0, "end": 12.0}]
    spec = own_footage(_inp(silences=silences, params={"pad": 0, "max_len": 9}))
    assert [(c.start, c.end) for c in spec.clips] == [(0.0, 2.0), (4.0, 10.0), (12.0, 13.0)]
    assert spec.credit is None and spec.subtitles.enabled


def test_own_footage_khong_co_khoang_lang_thi_giu_nguyen():
    spec = own_footage(_inp(silences=[], params={"cut_silence": True}))
    assert [(c.start, c.end) for c in spec.clips] == [(0.0, None)] and spec.credit is None
