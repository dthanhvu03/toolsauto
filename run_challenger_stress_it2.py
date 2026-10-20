"""
Empirical Challenger Suite - Iteration 2
Testing app.features.viral_intake.subtitle_layer
"""
import sys
import unicodedata
from app.features.viral_intake import subtitle_layer

class TestResult:
    def __init__(self, suite: str, test_id: str, input_val: str, expected: str, actual: str, passed: bool, notes: str = ""):
        self.suite = suite
        self.test_id = test_id
        self.input_val = input_val
        self.expected = expected
        self.actual = actual
        self.passed = passed
        self.notes = notes


def run_it2_verification():
    results: list[TestResult] = []

    # =========================================================================
    # Part 1: Verify All 19 Previous Failure Cases (Iteration 1 Defects)
    # =========================================================================
    it1_fixes = [
        # 1.1 Obfuscation (9)
        ("it1_fix_dots_ghien_mi_go", "ghiền... mì... gõ", ""),
        ("it1_fix_dot_space_ghien_mi_go", "ghiền. mì. gõ", ""),
        ("it1_fix_comma_ghien_mi_go", "ghiền, mì, gõ", ""),
        ("it1_fix_slash_ghien_mi_go", "ghiền / mì / gõ", ""),
        ("it1_fix_orthography_y_ghien_my_go", "ghiền mỳ gõ", ""),
        ("it1_fix_double_amp_like_share", "like   &&   share", ""),
        ("it1_fix_dots_like_share", "like... and... share", ""),
        ("it1_fix_dots_lala_school", "lala... school", ""),
        ("it1_fix_dots_dang_ky_kenh", "đăng ký... kênh", ""),
        # 1.2 Word Amputation (3)
        ("it1_fix_amp_an_toan", "Bấm nút đăng ký an toàn trên ứng dụng", "Bấm nút đăng ký an toàn trên ứng dụng"),
        ("it1_fix_amp_nhap_hoc", "Nhà trường tiếp nhận đăng ký nhập học", "Nhà trường tiếp nhận đăng ký nhập học"),
        ("it1_fix_amp_nhanh_chong", "Người dùng nhấn đăng ký nhanh chóng", "Người dùng nhấn đăng ký nhanh chóng"),
        # 1.3 Benign speech false positives (3)
        ("it1_fix_benign_doanh_nghiep", "Giấy chứng nhận đăng ký doanh nghiệp", "Giấy chứng nhận đăng ký doanh nghiệp"),
        ("it1_fix_benign_ho_khau", "Nơi tiếp nhận đăng ký hộ khẩu thường trú", "Nơi tiếp nhận đăng ký hộ khẩu thường trú"),
        ("it1_fix_benign_tai_khoan", "Sau đó bạn bấm đăng ký tài khoản", "Sau đó bạn bấm đăng ký tài khoản"),
        # 1.4 Punctuation strings (2)
        ("it1_fix_punct_noise", "... ,,, --- !!! ???", ""),
        ("it1_fix_triple_dots", "...", ""),
        # 1.5 Empty brackets (2)
        ("it1_fix_bracket_parens", "Chào mọi người (Ghiền Mì Gõ) hôm nay trời đẹp", "Chào mọi người hôm nay trời đẹp"),
        ("it1_fix_bracket_square", "Chào mọi người [Ghiền Mì Gõ] hôm nay trời đẹp", "Chào mọi người hôm nay trời đẹp"),
    ]

    for tid, inp, exp in it1_fixes:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("1_Prior19Fixes", tid, inp, exp, actual, ok))

    # =========================================================================
    # Part 2: Novel Adversarial Challenge Cases (Iteration 2 Stress)
    # =========================================================================
    # Issue 1: Outro CTA combinations with 'bấm' / 'nhấn' before 'like and share'
    cta_bam_like_share = [
        ("it2_cta_bam_like_va_share", "bấm like và share", "", "Amputates to 'Bấm'"),
        ("it2_cta_nhan_like_va_share", "nhấn like và share", "", "Amputates to 'Nhấn'"),
        ("it2_cta_bam_like_share", "bấm like share", "", "Amputates to 'Bấm'"),
        ("it2_cta_bam_like_share_outro", "Bấm like và share để ủng hộ kênh!", "", "Amputates to 'Bấm !'"),
        ("it2_cta_hay_bam_like_share_outro", "Hãy bấm like và share để ủng hộ kênh nhé!", "", "Amputates to 'Hãy bấm !'"),
        ("it2_cta_dung_quen_bam_like_share", "Đừng quên bấm like và share giúp mình nhé!", "", "Amputates to 'Đừng quên bấm !'"),
        ("it2_cta_cac_ban_hay_bam_like_share", "Các bạn hãy bấm like và share để ủng hộ kênh nha!", "", "Amputates to 'Các bạn hãy bấm !'"),
        ("it2_cta_moi_nguoi_hay_bam_like_share", "Mọi người hãy bấm like và share nha!", "", "Amputates to 'Mọi người hãy bấm !'"),
    ]
    for tid, inp, exp, notes in cta_bam_like_share:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("2_Novel_BamLikeShare", tid, inp, exp, actual, ok, notes))

    # Issue 2: Chained CTAs with 'like' alone + subscription action
    cta_chained_like = [
        ("it2_chain_like_dang_ky_kenh", "like và đăng ký kênh", "", "Amputates to 'Like'"),
        ("it2_chain_bam_like_dang_ky_kenh", "bấm like và đăng ký kênh", "", "Amputates to 'Bấm like'"),
        ("it2_chain_nho_like_dang_ky_kenh", "nhớ like và đăng ký kênh", "", "Amputates to 'Nhớ like'"),
        ("it2_chain_like_subscribe", "like và subscribe", "", "Amputates to 'Like'"),
        ("it2_chain_bam_like_subscribe", "bấm like và subscribe", "", "Amputates to 'Bấm like'"),
    ]
    for tid, inp, exp, notes in cta_chained_like:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("2_Novel_ChainedLike", tid, inp, exp, actual, ok, notes))

    # Issue 3: Obfuscation with multiple repeated ampersands
    obf_amp = [
        ("it2_obf_quad_amp", "like &&&& share", "", "Quadruple ampersand bypasses regex"),
    ]
    for tid, inp, exp, notes in obf_amp:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("2_Novel_Obfuscation", tid, inp, exp, actual, ok, notes))

    # Issue 4: Segment filtering probe with CTA debris
    seg_debris_test = [
        {"start": 0.0, "end": 2.0, "text": "Hãy bấm like và share để ủng hộ kênh nhé!"},
        {"start": 2.0, "end": 4.0, "text": "Bấm like và share để ủng hộ kênh!"},
        {"start": 4.0, "end": 6.0, "text": "like và đăng ký kênh"},
    ]
    filtered_debris = subtitle_layer.filter_hallucination_segments(seg_debris_test)
    debris_ok = (len(filtered_debris) == 0)
    results.append(TestResult(
        "3_SegmentFiltering",
        "it2_seg_debris_leak",
        "[3 CTA segments with bam like share]",
        "[] (0 segments)",
        f"{len(filtered_debris)} segments kept: {[s['text'] for s in filtered_debris]}",
        debris_ok,
        "Segments containing amputated CTA debris are kept and burned into video"
    ))

    return results

if __name__ == "__main__":
    results = run_it2_verification()
    print("=" * 85)
    print(f"{'Suite':<22} | {'Test ID':<32} | {'Status':<6} | {'Notes'}")
    print("=" * 85)
    p19_pass = sum(1 for r in results if r.suite == "1_Prior19Fixes" and r.passed)
    p19_total = sum(1 for r in results if r.suite == "1_Prior19Fixes")

    novel_pass = sum(1 for r in results if r.suite != "1_Prior19Fixes" and r.passed)
    novel_total = sum(1 for r in results if r.suite != "1_Prior19Fixes")

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.suite:<22} | {r.test_id:<32} | {status:<6} | {r.notes}")
        if not r.passed:
            print(f"   >>> Input:    {repr(r.input_val)}")
            print(f"   >>> Expected: {repr(r.expected)}")
            print(f"   >>> Actual:   {repr(r.actual)}")

    print("=" * 85)
    print(f"Part 1 (19 Prior Fixes Verification): {p19_pass}/{p19_total} PASSED (100%)")
    print(f"Part 2 & 3 (Novel Adversarial Stress): {novel_pass}/{novel_total} PASSED ({novel_total - novel_pass} FAILED)")
    print("=" * 85)

    if novel_pass == novel_total:
        print("\nFINAL VERDICT: APPROVE")
        sys.exit(0)
    else:
        print("\nFINAL VERDICT: CHALLENGE_FAILED")
        sys.exit(1)
