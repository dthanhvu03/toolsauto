"""
PLAN-119 — chất lượng lồng tiếng: gộp đoạn Whisper thành câu trước khi dịch, tách câu phụ đề («sub») với câu đọc («say»,
đã Việt hoá thuật ngữ / số), nhắc AI sửa chữ nghe nhầm. ffmpeg thật cho file giọng giả, không mạng.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from app.core.media import ffmpeg_path
from app.features.studio.dub import engine

# 5 đoạn đầu dự án #12 (Whisper thật, 31/10)
GOLF = [
    {"start": 0.0, "end": 4.8, "text": "This is episode 91 of trying out different golf courses so you don't have to and today we're at"},
    {"start": 4.8, "end": 9.36, "text": "King's Down Golf Club in Wilkshire. Fun fact, King's Down was founded all the way back in 1880"},
    {"start": 9.36, "end": 13.04, "text": "making it the oldest golf club in Wilkshire and actually one of the oldest in England."},
    {"start": 13.3, "end": 17.36, "text": "The original course was laid out by John Allen who was the professional at Royal North Devon."},
    {"start": 17.42, "end": 20.7, "text": "So there's a lot of history here. First impressions were actually really good."},
]


def test_gop_doan_thanh_cau():
    units = engine.merge_sentences(GOLF)
    assert [(u["start"], u["end"]) for u in units] == [(0.0, 9.36), (9.36, 13.04), (13.3, 17.36), (17.42, 20.7)]
    assert units[0]["text"].startswith("This is episode 91") and units[0]["text"].endswith("back in 1880")
    # có dấu kết câu → không gộp; cách xa → không gộp; quá MAX_UNIT_SEC → không gộp; đoạn rỗng bỏ
    segs = [{"start": 0, "end": 2, "text": "Xin chào."}, {"start": 2, "end": 3, "text": "  "}, {"start": 2.1, "end": 4, "text": "một"},
            {"start": 5.0, "end": 6, "text": "hai"}, {"start": 6.1, "end": 16, "text": "ba"}]
    assert [u["text"] for u in engine.merge_sentences(segs)] == ["Xin chào.", "một", "hai", "ba"]


def test_doc_ket_qua_dich_dang_moi_va_cu():
    pairs = engine.parse_translation(
        'ok [{"sub": "Tee box 1 rất đẹp", "say": "Khu phát bóng số một rất đẹp"}, "câu kiểu cũ", {"say": "chỉ có say"}]', 3)
    assert pairs == [("Tee box 1 rất đẹp", "Khu phát bóng số một rất đẹp"), ("câu kiểu cũ", "câu kiểu cũ"),
                     ("chỉ có say", "chỉ có say")]
    assert engine.parse_translation('["a", "b"]', 3) is None


def test_prompt_nhac_sua_chu_nghe_nham_va_viet_hoa_cau_doc():
    prompt = engine.build_translate_prompt([{"i": 0, "text": "Wilkshire", "max_chars": 40}], "en", "vi")
    assert "mis-heard" in prompt and '"sub"' in prompt and '"say"' in prompt
    assert "khu phát bóng" in prompt and "năm giờ rưỡi" in prompt  # ví dụ Việt hoá chỉ khi đích là tiếng Việt
    assert "khu phát bóng" not in engine.build_translate_prompt([{"i": 0, "text": "x", "max_chars": 9}], "vi", "en")


def _beep(path: str) -> None:
    subprocess.run([ffmpeg_path.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=500:duration=0.6",
                    path], check=True)


def test_giong_doc_cau_say_phu_de_giu_cau_sub(tmp_path, monkeypatch):
    from tests.test_studio_dub_long import _tracks_env

    _tracks_env(monkeypatch, tmp_path, separated=True, heard=GOLF)
    monkeypatch.setattr(engine, "_probe_duration", lambda p: 21.0)
    read: list[str] = []

    def synthesize(text, out, voice):
        read.append(text)
        _beep(out)
        return True

    def translate(prompt):
        n = len(json.loads(prompt[prompt.index("Lines:\n") + 7:]))
        return json.dumps([{"sub": f"Tee box {i}", "say": f"khu phát bóng số {i}"} for i in range(n)], ensure_ascii=False)

    res = engine.make_tracks("in.mp4", str(tmp_path), translate=translate, synthesize=synthesize)
    assert res.ok and res.reason == "zh→vi, 4/4 câu"  # 5 đoạn → 4 câu
    assert read == [f"khu phát bóng số {i}" for i in range(4)]
    assert [line["text"] for line in res.lines] == [f"Tee box {i}" for i in range(4)]
    assert res.lines[1]["start"] == pytest.approx(9.36, abs=0.01)
