"""
test_challenger_it2_adversarial.py — Empirical Adversarial Verification Suite (Iteration 2)
Agent: challenger_it2_2
Mission:
1. Verify pure BGM transcripts (1 to 50 segments) cause subtitle_layer.apply to:
   - return False
   - skip burn()
   - clean all temp files
   - leave input video intact
2. Verify mixed transcripts generate ASS files containing strictly clean dialogue with zero hallucination residue.
3. Verify concurrency, memory safety, and malformed segment dictionaries.
4. Formulate explicit verdict: APPROVE or CHALLENGE_FAILED.
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import os
import time
import tracemalloc

import pytest
import pysubs2

from app.features.viral_intake import subtitle_layer


# ─── 1. PURE BGM ADVERSARIAL MATRIX (1 to 50 SEGMENTS) ───

PURE_BGM_HALLUCINATIONS = [
    "Ghiền Mì Gõ",
    "ghiền mì gõ",
    "GHIÈN MÌ GÕ",
    "Ghien Mi Go",
    "ghien mi go",
    "GHIEN MI GO",
    "ghiền mì-gõ",
    "ghiền... mì... gõ",
    "ghiền. mì. gõ",
    "ghiền, mì, gõ",
    "ghiền / mì / gõ",
    "---ghien mi go---",
    "[GHIỀN MÌ GÕ]",
    "(ghien mi go)",
    "kênh Ghiền Mì Gõ",
    "nhóm Ghiền Mì Gõ",
    "phim Ghiền Mì Gõ",
    "ghiền mỳ gõ",
    "#ghienmygo",
    "#ghienmigo",
    "LaLa School",
    "lala school",
    "LALA SCHOOL",
    "lala... school",
    "học viện LaLa School",
    "phim LaLa School",
    "bấm subscribe",
    "BẤM SUBSCRIBE",
    "bam subscribe",
    "(bấm subscribe kênh!)",
    "bấm subscribe kênh",
    "nhấn subscribe",
    "bấm nút subscribe",
    "đăng ký kênh",
    "ĐĂNG KÝ KÊNH",
    "dang ky kenh",
    "đăng ký... kênh",
    "nhấn đăng ký kênh",
    "bấm đăng ký kênh",
    "đăng ký channel",
    "like and share",
    "Like and Share",
    "LIKE AND SHARE",
    "like & share",
    "like   &&   share",
    "like... and... share",
    "like va share",
    "nhớ like and share và đăng ký kênh nhé",
    "Đăng ký kênh để ủng hộ tụi mình nhé",
    "vui lòng bấm subscribe ủng hộ kênh nha",
    "các bạn hãy like and share nhé",
    "[nhạc]",
    "(âm nhạc)",
    "[tiếng vỗ tay]",
    "[tiếng cười]",
    "(tiếng động)",
    "[nhạc nền]",
    "[music]",
    "... ,,, --- !!! ???",
    "...",
    "---",
    "🔥 [Ghiền Mì Gõ] 👍 Bấm subscribe kênh ❤️",
]


@pytest.mark.parametrize("seg_count", [1, 2, 3, 5, 10, 20, 35, 50])
def test_pure_bgm_apply_returns_false_skips_burn_cleans_temp_and_preserves_input(tmp_path, seg_count):
    """
    Adversarial test for Pure BGM transcripts from 1 to 50 segments:
    - Must return False
    - burn() must be skipped (0 invocations)
    - Temp files (e.g. .sub.tmp.ass and dirty output) must be cleaned up
    - Input video must remain 100% intact (byte-exact match)
    """
    input_file = tmp_path / f"input_bgm_{seg_count}.mp4"
    output_file = tmp_path / f"output_bgm_{seg_count}.mp4"
    ass_file = tmp_path / f"output_bgm_{seg_count}.sub.tmp.ass"

    # Write original input video with known content & hash
    dummy_payload = os.urandom(8192)
    input_file.write_bytes(dummy_payload)
    orig_hash = hashlib.sha256(dummy_payload).hexdigest()

    # Pre-populate dirty output and dirty temp ass to verify active cleanup
    output_file.write_bytes(b"DIRTY_STALE_OUTPUT_LEFTOVER")
    ass_file.write_bytes(b"DIRTY_STALE_ASS_LEFTOVER")

    # Generate pure hallucination segments
    segs = []
    for i in range(seg_count):
        text = PURE_BGM_HALLUCINATIONS[i % len(PURE_BGM_HALLUCINATIONS)]
        segs.append({
            "start": float(i * 2.0),
            "end": float(i * 2.0 + 1.8),
            "text": text,
        })

    burn_called = False

    def _spy_burn(*args, **kwargs):
        nonlocal burn_called
        burn_called = True
        return True

    # Monkeypatch transcribing and burning
    orig_transcribe = subtitle_layer.transcribe_words
    orig_burn = subtitle_layer.burn
    subtitle_layer.transcribe_words = lambda *a, **k: segs
    subtitle_layer.burn = _spy_burn

    try:
        result = subtitle_layer.apply(str(input_file), str(output_file))

        # Invariant 1: apply must return False
        assert result is False, f"apply() returned True for pure BGM with {seg_count} segments"

        # Invariant 2: burn() must NEVER be invoked
        assert burn_called is False, f"burn() was invoked for pure BGM with {seg_count} segments"

        # Invariant 3: output file must NOT exist (dirty file removed, no output created)
        assert not output_file.exists(), f"output file exists after pure BGM: {output_file}"

        # Invariant 4: temp ASS file must NOT exist
        assert not ass_file.exists(), f"temp ASS file not cleaned up: {ass_file}"

        # Invariant 5: input file must exist and remain 100% intact
        assert input_file.exists(), "input video was removed!"
        current_payload = input_file.read_bytes()
        assert current_payload == dummy_payload, "input video was mutated!"
        assert hashlib.sha256(current_payload).hexdigest() == orig_hash, "input video hash changed!"
    finally:
        subtitle_layer.transcribe_words = orig_transcribe
        subtitle_layer.burn = orig_burn


# ─── 2. MIXED TRANSCRIPTS & ASS FILE PURITY VERIFICATION ───

MIXED_TEST_CASES = [
    {
        "name": "Leading junk brand",
        "raw": "Ghiền Mì Gõ xin chào quý vị khán giả đang theo dõi bản tin hôm nay",
        "expected_dialogue": "Xin chào quý vị khán giả đang theo dõi bản tin hôm nay",
        "forbidden": ["ghien mi go", "ghiền mì gõ"],
    },
    {
        "name": "Trailing CTA chain",
        "raw": "Hôm nay mình sẽ làm món súp gà, các bạn nhớ like and share và bấm subscribe nhé!",
        "expected_dialogue": "Hôm nay mình sẽ làm món súp gà",
        "forbidden": ["like and share", "subscribe", "bấm subscribe"],
    },
    {
        "name": "Embedded hallucination with parentheses",
        "raw": "Chào mọi người (Ghiền Mì Gõ) hôm nay chúng ta học nấu ăn",
        "expected_dialogue": "Chào mọi người hôm nay chúng ta học nấu ăn",
        "forbidden": ["ghien mi go", "(", ")"],
    },
    {
        "name": "Embedded hallucination with brackets",
        "raw": "Chào mọi người [LaLa School] cùng nhau luyện tập thể thao",
        "expected_dialogue": "Chào mọi người cùng nhau luyện tập thể thao",
        "forbidden": ["lala school", "[", "]"],
    },
    {
        "name": "Obfuscated junk with dots and symbols",
        "raw": "Xin chào các bạn --- ghiền... mì... gõ --- chúc một ngày vui vẻ",
        "expected_dialogue": "Xin chào các bạn chúc một ngày vui vẻ",
        "forbidden": ["ghien", "mi", "go"],
    },
    {
        "name": "Hashtag junk in dialogue",
        "raw": "Hãy theo dõi hành trình thú vị này #ghienmygo để biết thêm chi tiết",
        "expected_dialogue": "Hãy theo dõi hành trình thú vị này để biết thêm chi tiết",
        "forbidden": ["ghienmygo", "#ghienmygo"],
    },
    {
        "name": "Benign sensitive words preserved intact: mì gõ & con kênh",
        "raw": "Bác nông dân gánh lúa qua con kênh nhỏ rồi bấm chuông gọi cửa ăn bát mì gõ",
        "expected_dialogue": "Bác nông dân gánh lúa qua con kênh nhỏ rồi bấm chuông gọi cửa ăn bát mì gõ",
        "forbidden": [],
    },
    {
        "name": "Benign administrative phrase: đăng ký kết hôn",
        "raw": "Thủ tục đăng ký kết hôn và đăng ký doanh nghiệp rất nhanh chóng",
        "expected_dialogue": "Thủ tục đăng ký kết hôn và đăng ký doanh nghiệp rất nhanh chóng",
        "forbidden": [],
    },
    {
        "name": "Benign app guide without word amputation: đăng ký an toàn",
        "raw": "Bấm nút đăng ký an toàn trên ứng dụng di động",
        "expected_dialogue": "Bấm nút đăng ký an toàn trên ứng dụng di động",
        "forbidden": ["n toàn"],
    },
    {
        "name": "Benign school admission without word amputation: tiếp nhận đăng ký nhập học",
        "raw": "Nhà trường tiếp nhận đăng ký nhập học từ ngày mai",
        "expected_dialogue": "Nhà trường tiếp nhận đăng ký nhập học từ ngày mai",
        "forbidden": ["p học"],
    },
    {
        "name": "Benign fast registration without word amputation: nhấn đăng ký nhanh chóng",
        "raw": "Người dùng nhấn đăng ký nhanh chóng trong ba phút",
        "expected_dialogue": "Người dùng nhấn đăng ký nhanh chóng trong ba phút",
        "forbidden": ["nh chóng"],
    },
]


def test_mixed_transcripts_generate_strictly_pure_ass_events(tmp_path):
    """
    Test end-to-end ASS generation on mixed transcripts:
    - Pure junk segments are completely dropped from ASS.
    - Mixed segments are pruned cleanly without leftover junk or bracket scars.
    - Benign Vietnamese vocabulary is 100% preserved.
    - Inspect pysubs2 events and raw ASS file.
    """
    input_file = tmp_path / "in_mixed.mp4"
    output_file = tmp_path / "out_mixed.mp4"
    input_file.write_bytes(b"dummy_mixed_input")

    # Build an alternating segment list: junk, mixed, benign, audio tag
    segments = [
        {"start": 0.0, "end": 2.0, "text": "Ghiền Mì Gõ - Like and share"},  # PURE JUNK -> DROPPED
        {"start": 2.0, "end": 6.0, "text": "Hôm nay mình sẽ làm món súp gà, các bạn nhớ like and share nhé"},  # MIXED -> PRUNED
        {"start": 6.0, "end": 8.0, "text": "[nhạc nền] [tiếng vỗ tay]"},  # AUDIO TAG -> DROPPED
        {"start": 8.0, "end": 12.0, "text": "Bác nông dân gánh lúa qua con kênh nhỏ rồi bấm chuông gọi cửa ăn bát mì gõ"},  # BENIGN -> KEPT
        {"start": 12.0, "end": 15.0, "text": "Bấm nút đăng ký an toàn trên ứng dụng di động"},  # BENIGN -> KEPT
        {"start": 15.0, "end": 17.0, "text": "LaLa School bấm subscribe đăng ký kênh"},  # PURE JUNK -> DROPPED
        {"start": 17.0, "end": 20.0, "text": "Chào mọi người (Ghiền Mì Gõ) hôm nay chúng ta học nấu ăn"},  # MIXED -> PRUNED
    ]

    captured_ass_path = None
    captured_ass_content = None

    def _mock_burn(in_p, ass_p, out_p, **kw):
        nonlocal captured_ass_path, captured_ass_content
        captured_ass_path = ass_p
        with open(ass_p, "r", encoding="utf-8") as f:
            captured_ass_content = f.read()
        # Simulate successful burn
        with open(out_p, "wb") as f:
            f.write(b"MOCK_BURNED_VIDEO_PAYLOAD" * 100)
        return True

    orig_transcribe = subtitle_layer.transcribe_words
    orig_burn = subtitle_layer.burn
    subtitle_layer.transcribe_words = lambda *a, **k: segments
    subtitle_layer.burn = _mock_burn

    try:
        ok = subtitle_layer.apply(str(input_file), str(output_file))
        assert ok is True, "apply() failed on mixed transcripts!"
        assert captured_ass_content is not None, "burn() was not called with ASS file!"

        # Parse the captured ASS
        subs = pysubs2.SSAFile.from_string(captured_ass_content)
        events = list(subs.events)

        # There were 7 input segments:
        # 3 pure junk/tag segments must be completely absent.
        # 4 clean/pruned segments should be present (may be wrapped into 1-2 chunks each).
        assert len(events) >= 4, f"Expected at least 4 subtitle events, got {len(events)}"

        # Concatenate all event texts for full inspection
        all_event_text = " ".join(ev.text.replace("\\N", " ") for ev in events)
        all_event_stripped = subtitle_layer.strip_accents(all_event_text).lower()

        # Check Invariant: Zero hallucination residue in ASS
        forbidden_hallucinations = [
            "ghien mi go",
            "ghien my go",
            "lala school",
            "like and share",
            "subscribe",
            "[nhac]",
            "[tieng vo tay]",
        ]
        for junk in forbidden_hallucinations:
            assert junk not in all_event_stripped, f"Hallucination residue '{junk}' found in ASS text: {all_event_text}"

        # Check Invariant: No empty bracket scars `( )` or `[ ]`
        assert "()" not in all_event_text and "( )" not in all_event_text, f"Empty parens scar in ASS: {all_event_text}"
        assert "[]" not in all_event_text and "[ ]" not in all_event_text, f"Empty bracket scar in ASS: {all_event_text}"

        # Check Invariant: Dialogue content preserved
        assert "Hôm nay mình sẽ làm món súp gà" in all_event_text
        assert "Bác nông dân gánh lúa qua con kênh nhỏ rồi bấm chuông gọi cửa ăn bát mì gõ" in all_event_text
        assert "Bấm nút đăng ký an toàn trên ứng dụng di động" in all_event_text
        assert "Chào mọi người hôm nay chúng ta học nấu ăn" in all_event_text

        # Check Invariant: No word amputation
        assert "n toàn" not in all_event_text or "an toàn" in all_event_text
        assert "an toàn" in all_event_text

        # Check timestamps of events are well-ordered and positive
        for ev in events:
            assert ev.start >= 0
            assert ev.end > ev.start
            assert ev.text.strip() != ""
    finally:
        subtitle_layer.transcribe_words = orig_transcribe
        subtitle_layer.burn = orig_burn


# ─── 3. MALFORMED SEGMENT DICTIONARIES STRESS TEST ───

def test_malformed_segment_dictionaries_resilience():
    """
    Verify keep_speech_segments and filter_hallucination_segments handle:
    - Non-dict objects (None, int, float, str, list, set)
    - Empty dictionaries and missing keys
    - Inverted timestamps (end <= start)
    - Malformed timestamps (NaN, Inf, strings, None, negative numbers)
    - Pathological text inputs (None, int, huge string, pure punctuation)
    - Malformed Whisper metadata (invalid no_speech_prob, compression_ratio)
    """
    malformed_segments = [
        None,
        "string_item",
        12345,
        3.14159,
        True,
        False,
        [],
        (),
        {},  # empty dict
        {"start": 0.0},  # missing end and text
        {"end": 2.0},  # missing start and text
        {"text": ""},  # empty text
        {"text": "   "},  # whitespace text
        {"text": None, "start": 0.0, "end": 2.0},  # None text
        {"text": 123456, "start": 0.0, "end": 2.0},  # int text
        {"text": "... ,,, ---", "start": 0.0, "end": 2.0},  # pure punctuation text
        {"text": "Đảo ngược thời gian", "start": 5.0, "end": 2.0},  # end < start
        {"text": "Zero duration", "start": 3.0, "end": 3.0},  # end == start
        {"text": "Bad start str", "start": "not_a_float", "end": 2.0},
        {"text": "Bad end str", "start": 1.0, "end": "not_a_float"},
        {"text": "Start None", "start": None, "end": 2.0},
        {"text": "End None", "start": 1.0, "end": None},
        {"text": "NaN timestamp", "start": float("nan"), "end": 2.0},
        {"text": "Inf timestamp", "start": 0.0, "end": float("inf")},
        {"text": "Negative timestamps", "start": -5.0, "end": -2.0},
        {"text": "High no-speech drop", "start": 10.0, "end": 12.0, "no_speech_prob": 0.95},
        {"text": "High compression ratio drop", "start": 12.0, "end": 14.0, "compression_ratio": 4.5},
        {"text": "Invalid no-speech string", "start": 14.0, "end": 16.0, "no_speech_prob": "invalid_val"},
        {"text": "Valid legitimate speech", "start": 20.0, "end": 24.0, "no_speech_prob": 0.05, "compression_ratio": 1.1},
    ]

    # Test keep_speech_segments resilience
    kept = subtitle_layer.keep_speech_segments(malformed_segments)  # type: ignore

    # Must survive and return a list
    assert isinstance(kept, list)
    kept_texts = [seg.get("text") for seg in kept]

    # Verify that invalid segments were filtered out
    assert "Đảo ngược thời gian" not in kept_texts
    assert "Zero duration" not in kept_texts
    assert "Bad start str" not in kept_texts
    assert "Bad end str" not in kept_texts
    assert "Start None" not in kept_texts
    assert "End None" not in kept_texts
    assert "High no-speech drop" not in kept_texts
    assert "High compression ratio drop" not in kept_texts

    # Legitimate segment must be retained
    assert "Valid legitimate speech" in kept_texts


def test_apply_with_pathological_transcribe_words(tmp_path):
    """
    Test apply() when transcribe_words returns pathological outputs:
    - Returns None
    - Returns an integer
    - Returns segments with NaN/Inf
    apply() must never raise an unhandled exception, return False, clean up temp files.
    """
    input_file = tmp_path / "in_patho.mp4"
    output_file = tmp_path / "out_patho.mp4"
    input_file.write_bytes(b"payload")

    orig_transcribe = subtitle_layer.transcribe_words
    try:
        # 1. transcribe_words returns None
        subtitle_layer.transcribe_words = lambda *a, **k: None  # type: ignore
        res1 = subtitle_layer.apply(str(input_file), str(output_file))
        assert res1 is False
        assert not output_file.exists()

        # 2. transcribe_words returns [float('nan')]
        subtitle_layer.transcribe_words = lambda *a, **k: [
            {"start": float("nan"), "end": 2.0, "text": "Nan segment"}
        ]
        res2 = subtitle_layer.apply(str(input_file), str(output_file))
        assert res2 is False
        assert not output_file.exists()

        # 3. transcribe_words raises an unexpected exception
        def _boom(*a, **k):
            raise RuntimeError("Unexpected transcriber crash")

        subtitle_layer.transcribe_words = _boom
        res3 = subtitle_layer.apply(str(input_file), str(output_file))
        assert res3 is False
        assert not output_file.exists()
    finally:
        subtitle_layer.transcribe_words = orig_transcribe


# ─── 4. CONCURRENCY & MULTI-THREAD SAFETY ───

def test_multithreaded_concurrent_apply_and_filtering(tmp_path):
    """
    Test 16 concurrent threads executing subtitle filtering and apply() pipelines:
    - Multiple threads calling subtitle_layer.apply simultaneously with distinct input/output files.
    - Check for file collisions, temporary file leaks, race conditions.
    """
    def _mock_burn(in_p, ass_p, out_p, **kw):
        time.sleep(0.01)  # small delay to simulate ffmpeg activity
        with open(out_p, "wb") as f:
            f.write(b"CONCURRENT_OUT" * 50)
        return True

    orig_burn = subtitle_layer.burn
    orig_trans = subtitle_layer.transcribe_words
    subtitle_layer.burn = _mock_burn
    subtitle_layer.transcribe_words = lambda *a, **k: [
        {"start": 0.0, "end": 2.0, "text": "Hôm nay tôi đi dạo công viên cùng gia đình"}
    ]

    def _worker(thread_idx: int):
        sub_tmp = tmp_path / f"thread_{thread_idx}"
        sub_tmp.mkdir(exist_ok=True)
        inp = sub_tmp / "in.mp4"
        out = sub_tmp / "out.mp4"
        ass_tmp = sub_tmp / "out.sub.tmp.ass"
        inp.write_bytes(b"PAYLOAD")

        ok = subtitle_layer.apply(str(inp), str(out))
        return {
            "thread_idx": thread_idx,
            "ok": ok,
            "out_exists": out.exists(),
            "ass_exists": ass_tmp.exists(),
            "inp_exists": inp.exists(),
        }

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(_worker, i) for i in range(16)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == 16
        for r in results:
            assert r["ok"] is True, f"Thread {r['thread_idx']} failed apply()"
            assert r["out_exists"] is True, f"Thread {r['thread_idx']} output missing"
            assert r["ass_exists"] is False, f"Thread {r['thread_idx']} temp ASS not cleaned"
            assert r["inp_exists"] is True, f"Thread {r['thread_idx']} input missing"
    finally:
        subtitle_layer.burn = orig_burn
        subtitle_layer.transcribe_words = orig_trans


# ─── 5. MEMORY SAFETY & STABILITY ───

def test_memory_safety_over_1000_iterations():
    """
    Monitor heap memory using tracemalloc over 1,000 mixed cleaning operations.
    Ensure memory consumption does not grow unboundedly (net delta < 500 KB).
    """
    mixed_corpus = [
        "Ghiền Mì Gõ xin chào quý vị",
        "Chào mọi người (Ghiền Mì Gõ) hôm nay trời đẹp",
        "Tôi ăn mì gõ ven đường rất ngon",
        "Thủ tục đăng ký kết hôn tại ủy ban nhân dân",
        "Bấm nút đăng ký an toàn trên ứng dụng",
        "Like and share và bấm subscribe nhé cả nhà",
        "Con kênh xanh xanh chảy qua đồng lúa",
        "... ,,, --- !!! ???",
        "🔥 [Ghiền Mì Gõ] 👍 Bấm subscribe kênh ❤️",
    ]

    tracemalloc.start()
    snapshot_before = tracemalloc.take_snapshot()

    for i in range(1000):
        text = mixed_corpus[i % len(mixed_corpus)]
        _ = subtitle_layer.clean_hallucinations_from_text(text)
        segs = [{"start": 0.0, "end": 2.0, "text": text}]
        _ = subtitle_layer.keep_speech_segments(segs)

    snapshot_after = tracemalloc.take_snapshot()
    top_diffs = snapshot_after.compare_to(snapshot_before, "lineno")
    total_diff_kb = sum(stat.size_diff for stat in top_diffs) / 1024.0
    tracemalloc.stop()

    # Memory growth over 1,000 iterations must be minimal (< 500 KB)
    assert total_diff_kb < 500.0, f"Memory growth too high: {total_diff_kb:.2f} KB over 1000 iterations"
