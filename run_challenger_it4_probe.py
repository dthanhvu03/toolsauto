"""
Empirical Challenger Iteration 4 Deep Probe
Verifying the 13 defect fixes and attacking boundary edge cases.
"""
import math
import os
import re
import tempfile
import pysubs2
from app.features.viral_intake import subtitle_layer

def run_deep_probe():
    errors = []
    print("--- 1. Testing Audio Tag Variations ---")
    audio_tags = [
        "(tiếng cười)",
        "[tiếng cười]",
        "(tieng cuoi)",
        "(TIẾNG CƯỜI)",
        "[TIENG CUOI]",
        "( Tiếng Cười )",
        "[  tiếng cười  ]",
        "(tiếng cười) (tiếng vỗ tay)",
        "(nhạc) [tiếng cười] (music)",
        "   (tiếng cười)   ",
    ]
    for tag in audio_tags:
        cleaned = subtitle_layer.clean_hallucinations_from_text(tag)
        if cleaned != "":
            errors.append(f"Audio tag failed to clean completely: {tag!r} -> {cleaned!r}")
        else:
            print(f"  [OK] {tag!r} -> {cleaned!r}")

    print("\n--- 2. Testing Mixed Audio Tags in Genuine Dialogue ---")
    mixed_audio = [
        ("Mọi người đều vui vẻ (tiếng cười) khi nghe kể chuyện.", "Mọi người đều vui vẻ khi nghe kể chuyện."),
        ("Khán giả reo hò [tiếng cười] rất náo nhiệt.", "Khán giả reo hò rất náo nhiệt."),
        ("(tiếng cười) Thật là bất ngờ!", "Thật là bất ngờ!"),
        ("Đó là một câu chuyện hay (tieng cuoi)", "Đó là một câu chuyện hay"),
    ]
    for raw, expected in mixed_audio:
        actual = subtitle_layer.clean_hallucinations_from_text(raw)
        if actual != expected:
            errors.append(f"Mixed audio tag excision mismatch: raw={raw!r} -> actual={actual!r}, expected={expected!r}")
        else:
            print(f"  [OK] raw={raw!r} -> {actual!r}")

    print("\n--- 3. Testing Bracket Debris Variations (!, ?, combinations) ---")
    bracket_cases = [
        ("Chào bạn (bấm subscribe kênh!) hôm nay thế nào?", "Chào bạn hôm nay thế nào?"),
        ("Sản phẩm này [Ghiền Mì Gõ!] mang lại hiệu quả cao", "Sản phẩm này mang lại hiệu quả cao"),
        ("Chào các bạn (like & share!!!) chúc buổi sáng tốt lành", "Chào các bạn chúc buổi sáng tốt lành"),
        ("Tin tức [Ghiền Mì Gõ???] rất nóng hổi", "Tin tức rất nóng hổi"),
        ("Đặc biệt {like and share?!} vô cùng cuốn hút", "Đặc biệt vô cùng cuốn hút"),
        ("Món ăn này (đăng ký kênh! ? !) rất ngon miệng", "Món ăn này rất ngon miệng"),
        ("Nội dung (bấm subscribe) rất bổ ích", "Nội dung rất bổ ích"),
    ]
    for raw, expected in bracket_cases:
        actual = subtitle_layer.clean_hallucinations_from_text(raw)
        has_debris = bool(re.search(r"[\(\[\{][\s\.,;:–—\-_\!\?]*[\)\]\}]", actual))
        if has_debris or actual != expected:
            errors.append(f"Bracket debris failed: raw={raw!r} -> actual={actual!r}, expected={expected!r}")
        else:
            print(f"  [OK] raw={raw!r} -> {actual!r}")

    print("\n--- 4. Testing Benign Polite Sentences (Non-CTA) ---")
    polite_cases = [
        ("Xin vui lòng xuất trình giấy tờ tùy thân.", "Xin vui lòng xuất trình giấy tờ tùy thân."),
        ("Xin hãy giữ im lặng trong phòng họp.", "Xin hãy giữ im lặng trong phòng họp."),
        ("Các bạn học sinh chú ý lắng nghe thầy cô giảng bài.", "Các bạn học sinh chú ý lắng nghe thầy cô giảng bài."),
        ("Mọi người đều đồng ý với quyết định này.", "Mọi người đều đồng ý với quyết định này."),
        ("Cả nhà cùng nhau ăn bữa cơm ấm cúng.", "Cả nhà cùng nhau ăn bữa cơm ấm cúng."),
        ("Quý vị đại biểu xin vui lòng an tọa.", "Quý vị đại biểu xin vui lòng an tọa."),
    ]
    for raw, expected in polite_cases:
        actual = subtitle_layer.clean_hallucinations_from_text(raw)
        if actual != expected:
            errors.append(f"Benign polite phrase corrupted: raw={raw!r} -> actual={actual!r}, expected={expected!r}")
        else:
            print(f"  [OK] raw={raw!r} -> {actual!r}")

    print("\n--- 5. Testing Timestamp Anomalies (NaN, Inf, Negative, Inverted) ---")
    anomaly_segs = [
        {"start": float("nan"), "end": 2.0, "text": "nan start"},
        {"start": 1.0, "end": float("nan"), "text": "nan end"},
        {"start": float("nan"), "end": float("nan"), "text": "both nan"},
        {"start": float("inf"), "end": 5.0, "text": "inf start"},
        {"start": 1.0, "end": float("inf"), "text": "inf end"},
        {"start": float("-inf"), "end": 5.0, "text": "-inf start"},
        {"start": 5.0, "end": float("-inf"), "text": "-inf end"},
        {"start": float("inf"), "end": float("inf"), "text": "both inf"},
        {"start": -1.0, "end": 2.0, "text": "negative start"},
        {"start": -5.0, "end": -2.0, "text": "negative both"},
        {"start": 5.0, "end": 2.0, "text": "inverted"},
        {"start": 2.0, "end": 2.0, "text": "equal"},
    ]
    kept = subtitle_layer.keep_speech_segments(anomaly_segs)
    if len(kept) != 0:
        errors.append(f"keep_speech_segments kept anomalous segments: {kept}")
    else:
        print(f"  [OK] keep_speech_segments dropped all 12 anomaly segments correctly (kept: {len(kept)})")

    # Now verify build_ass with anomalies directly
    with tempfile.NamedTemporaryFile(suffix=".ass", delete=False) as f:
        tmp_ass = f.name
    try:
        # build_ass with anomalous inputs directly
        subtitle_layer.build_ass(anomaly_segs, tmp_ass)
        subs = pysubs2.load(tmp_ass)
        if len(subs.events) != 0:
            errors.append(f"build_ass created events from anomalous segments: {len(subs.events)}")
        else:
            print(f"  [OK] build_ass safely dropped all 12 anomaly segments without crashing (events: 0)")
    except Exception as e:
        errors.append(f"build_ass crashed on anomalous segments: {e}")
    finally:
        if os.path.exists(tmp_ass):
            os.remove(tmp_ass)

    print("\n--- 6. Pure BGM Video with Laughing Tag (End-to-End apply check) ---")
    # Verify apply() with pure laughing tag mock
    dummy_in = "/tmp/dummy_test_in.mp4"
    dummy_out = "/tmp/dummy_test_out.mp4"
    # Create simple file if not exists
    with open(dummy_in, "wb") as f:
        f.write(b"dummy video data")

    orig_burn = subtitle_layer.burn
    orig_transcribe = subtitle_layer.transcribe_words
    burn_called = []
    subtitle_layer.burn = lambda *a, **k: burn_called.append(True)
    subtitle_layer.transcribe_words = lambda *a, **k: [{"start": 0.0, "end": 1.5, "text": "(tiếng cười)"}]
    try:
        res = subtitle_layer.apply(dummy_in, dummy_out)
        if res is not False:
            errors.append(f"apply() did not return False for pure BGM laughing tag: res={res}")
        if len(burn_called) > 0:
            errors.append(f"burn() was called for pure BGM laughing tag!")
        if os.path.exists(dummy_out):
            errors.append(f"output video was created for pure BGM laughing tag!")
        print(f"  [OK] apply() returned False, burn_called={len(burn_called)}, output_created={os.path.exists(dummy_out)}")
    finally:
        subtitle_layer.burn = orig_burn
        subtitle_layer.transcribe_words = orig_transcribe
        if os.path.exists(dummy_in): os.remove(dummy_in)
        if os.path.exists(dummy_out): os.remove(dummy_out)

    print("\n" + "=" * 50)
    if errors:
        print(f"PROBE FAILED with {len(errors)} errors:")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("ALL DEEP PROBE CHECKS PASSED (100% OK)!")
        return True

if __name__ == "__main__":
    import sys
    ok = run_deep_probe()
    sys.exit(0 if ok else 1)
