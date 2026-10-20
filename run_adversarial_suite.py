"""
Adversarial Verification Suite for Whisper Hallucination Filter
Module: app.features.viral_intake.subtitle_layer
"""
import unicodedata
from app.features.viral_intake import subtitle_layer

class TestResult:
    def __init__(self, category: str, test_id: str, input_val: str, expected_desc: str, actual: str, passed: bool, notes: str = ""):
        self.category = category
        self.test_id = test_id
        self.input_val = input_val
        self.expected_desc = expected_desc
        self.actual = actual
        self.passed = passed
        self.notes = notes

def run_suite():
    results: list[TestResult] = []

    def check(category, tid, inp, pred, expected_desc, notes=""):
        cleaned = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = pred(cleaned)
        results.append(TestResult(category, tid, inp, expected_desc, cleaned, ok, notes))

    # =========================================================================
    # Category 1: Obfuscated / Noisy Hallucinations (Prompt explicit requirements)
    # =========================================================================
    check("1_Obfuscation", "dots_ghien_mi_go", "ghiền... mì... gõ", lambda s: s == "", "Completely dropped", "Explicit prompt test case")
    check("1_Obfuscation", "dot_space_ghien_mi_go", "ghiền. mì. gõ", lambda s: s == "", "Completely dropped")
    check("1_Obfuscation", "comma_ghien_mi_go", "ghiền, mì, gõ", lambda s: s == "", "Completely dropped")
    check("1_Obfuscation", "slash_ghien_mi_go", "ghiền / mì / gõ", lambda s: s == "", "Completely dropped")
    check("1_Obfuscation", "dash_ghien_mi_go", "---ghien mi go---", lambda s: s == "", "Completely dropped", "Explicit prompt test case")
    check("1_Obfuscation", "bracket_upper_ghien", "[GHIỀN MÌ GÕ]", lambda s: s == "", "Completely dropped", "Explicit prompt test case")
    check("1_Obfuscation", "parens_subscribe", "(bấm subscribe kênh!)", lambda s: s == "", "Completely dropped", "Explicit prompt test case")
    check("1_Obfuscation", "double_amp_like_share", "like   &&   share", lambda s: s == "", "Completely dropped", "Explicit prompt test case")
    check("1_Obfuscation", "dots_like_share", "like... and... share", lambda s: s == "", "Completely dropped")
    check("1_Obfuscation", "dots_lala_school", "lala... school", lambda s: s == "", "Completely dropped")
    check("1_Obfuscation", "dots_dang_ky_kenh", "đăng ký... kênh", lambda s: s == "", "Completely dropped")
    check("1_Obfuscation", "orthography_y_ghien_my_go", "ghiền mỳ gõ", lambda s: s == "", "Completely dropped", "Vietnamese y/i orthographic variation")

    # =========================================================================
    # Category 2: Multi-Hallucination Chains
    # =========================================================================
    check("2_MultiChain", "full_chain", "ghiền mì gõ lala school bấm subscribe đăng ký kênh like and share", lambda s: s == "", "Completely dropped", "Explicit prompt test case")
    check("2_MultiChain", "noisy_chain", "--- [ghiền mì gõ] ... lala school ... (đăng ký kênh) && like and share! ---", lambda s: s == "", "Completely dropped")

    # =========================================================================
    # Category 3: Diacritic Stress (NFC, NFD, Uppercase, Partial)
    # =========================================================================
    check("3_Diacritics", "nfc_ghien_mi_go", unicodedata.normalize("NFC", "Ghiền Mì Gõ"), lambda s: s == "", "Completely dropped")
    check("3_Diacritics", "nfd_ghien_mi_go", unicodedata.normalize("NFD", "Ghiền Mì Gõ"), lambda s: s == "", "Completely dropped")
    check("3_Diacritics", "partial_accent_ghien", "ghiên mì gõ", lambda s: s == "", "Completely dropped", "Explicit prompt test case")
    check("3_Diacritics", "upper_accent_ghien", "GHIỀN MÌ GÕ", lambda s: s == "", "Completely dropped")

    # =========================================================================
    # Category 4: Benign Vocabulary Stress (Must NEVER be corrupted or stripped)
    # =========================================================================
    benign_list = [
        ("benign_mi_1", "Tôi ăn mì gói mỗi sáng"),
        ("benign_mi_2", "Sợi mì dai và nước dùng ngọt thanh"),
        ("benign_go_1", "Anh ấy gõ bàn phím rất nhanh"),
        ("benign_go_2", "Tôi nghe tiếng gõ cửa lúc nửa đêm"),
        ("benign_mi_go_trap", "Tôi thích ăn mì gõ lề đường Sài Gòn"),
        ("benign_dang_ky_1", "Thủ tục đăng ký kết hôn rất đơn giản"),
        ("benign_dang_ky_2", "Tôi vừa đi đăng ký xe máy mới"),
        ("benign_nhan_dang_ky_1", "Giấy chứng nhận đăng ký doanh nghiệp"),
        ("benign_nhan_dang_ky_2", "Nơi tiếp nhận đăng ký hộ khẩu thường trú"),
        ("benign_nhan_dang_ky_3", "Nhà trường tiếp nhận đăng ký nhập học"),
        ("benign_kenh_1", "Con kênh xanh xanh chảy qua đồng lúa"),
        ("benign_kenh_2", "Kênh VTV1 đang phát sóng thời sự"),
        ("benign_like_1", "Bài viết này nhận được rất nhiều like"),
        ("benign_like_2", "Tôi like chiếc áo màu xanh này"),
        ("benign_share_1", "Bạn share tài liệu học tập giúp mình với"),
        ("benign_share_2", "Họ share bài viết này lên nhiều hội nhóm"),
        ("benign_truong_hoc_1", "Em đi đến trường học mỗi sáng"),
        ("benign_truong_hoc_2", "Trường học thân thiện học sinh tích cực"),
        ("benign_app_tutorial_1", "Sau đó bạn bấm đăng ký tài khoản"),
        ("benign_app_tutorial_2", "Bấm nút đăng ký an toàn trên ứng dụng"),
        ("benign_app_tutorial_3", "Người dùng nhấn đăng ký nhanh chóng"),
    ]
    for bid, text in benign_list:
        check("4_BenignStress", bid, text, lambda s, orig=text: s == orig, f"Exact match with: {text}")

    # =========================================================================
    # Category 5: Empty, Whitespace, Punctuation-only, Emoji
    # =========================================================================
    check("5_Punctuation_Emoji", "empty_str", "", lambda s: s == "", "Returns empty")
    check("5_Punctuation_Emoji", "whitespace_str", "   \t\n   ", lambda s: s == "", "Returns empty")
    check("5_Punctuation_Emoji", "punct_symbols", "... ,,, --- !!! ???", lambda s: s == "", "Returns empty (no dialogue)", "Prompt explicit requirement")
    check("5_Punctuation_Emoji", "triple_dots", "...", lambda s: s == "", "Returns empty")
    check("5_Punctuation_Emoji", "emoji_pure", "😀🎉🔥", lambda s: True, "Handled safely without crash")
    check("5_Punctuation_Emoji", "emoji_with_junk", "🔥 [Ghiền Mì Gõ] 👍 Bấm subscribe kênh ❤️", lambda s: s == "", "Returns empty")

    # =========================================================================
    # Category 6: Mixed Dialogue Excision Quality (Bracket artifacts & corruption)
    # =========================================================================
    check("6_MixedExcision", "parens_in_middle", "Chào mọi người (Ghiền Mì Gõ) hôm nay trời đẹp",
          lambda s: "(" not in s and ")" not in s and "Chào mọi người hôm nay trời đẹp" in s,
          "No empty brackets remaining")
    check("6_MixedExcision", "brackets_in_middle", "Chào mọi người [Ghiền Mì Gõ] hôm nay trời đẹp",
          lambda s: "[" not in s and "]" not in s and "Chào mọi người hôm nay trời đẹp" in s,
          "No empty brackets remaining")

    # =========================================================================
    # Category 7: filter_hallucination_segments Behavior
    # =========================================================================
    seg_tests = [
        {"start": 0.0, "end": 2.0, "text": "ghiền... mì... gõ"},
        {"start": 2.0, "end": 4.0, "text": "like   &&   share"},
        {"start": 4.0, "end": 6.0, "text": "... ,,, --- !!! ???"},
        {"start": 6.0, "end": 8.0, "text": "Giấy chứng nhận đăng ký doanh nghiệp"},
    ]
    filtered_segs = subtitle_layer.filter_hallucination_segments(seg_tests)
    seg_texts = [s["text"] for s in filtered_segs]

    return results, seg_tests, filtered_segs

if __name__ == "__main__":
    results, raw_segs, filtered_segs = run_suite()
    print("=" * 80)
    print(f"{'Category':<18} | {'Test ID':<25} | {'Passed':<6} | {'Notes'}")
    print("=" * 80)
    failed_count = 0
    passed_count = 0
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        if not r.passed:
            failed_count += 1
        else:
            passed_count += 1
        print(f"{r.category:<18} | {r.test_id:<25} | {status:<6} | {r.notes}")
        if not r.passed:
            print(f"   >>> Input:    {repr(r.input_val)}")
            print(f"   >>> Expected: {r.expected_desc}")
            print(f"   >>> Actual:   {repr(r.actual)}")

    print("=" * 80)
    print(f"Summary: {passed_count} Passed, {failed_count} Failed out of {len(results)} tests.")
    print("=" * 80)
    print("\nSegment Filtering Probe:")
    for orig, filt in zip(raw_segs, filtered_segs):
        print(f"Original: {repr(orig['text'])}")
        print(f"Filtered: {repr(filt['text'])}")
        print("-" * 40)
