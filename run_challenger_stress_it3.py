"""
Empirical Challenger Suite - Iteration 3
Stress Testing app.features.viral_intake.subtitle_layer
"""
import sys
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

def run_it3_verification():
    results: list[TestResult] = []

    # =========================================================================
    # Part 1: Verify Prior Iteration 1 Fixes (19 Cases)
    # =========================================================================
    it1_fixes = [
        ("it1_fix_dots_ghien_mi_go", "ghiền... mì... gõ", ""),
        ("it1_fix_dot_space_ghien_mi_go", "ghiền. mì. gõ", ""),
        ("it1_fix_comma_ghien_mi_go", "ghiền, mì, gõ", ""),
        ("it1_fix_slash_ghien_mi_go", "ghiền / mì / gõ", ""),
        ("it1_fix_orthography_y_ghien_my_go", "ghiền mỳ gõ", ""),
        ("it1_fix_double_amp_like_share", "like   &&   share", ""),
        ("it1_fix_dots_like_share", "like... and... share", ""),
        ("it1_fix_dots_lala_school", "lala... school", ""),
        ("it1_fix_dots_dang_ky_kenh", "đăng ký... kênh", ""),
        ("it1_fix_amp_an_toan", "Bấm nút đăng ký an toàn trên ứng dụng", "Bấm nút đăng ký an toàn trên ứng dụng"),
        ("it1_fix_amp_nhap_hoc", "Nhà trường tiếp nhận đăng ký nhập học", "Nhà trường tiếp nhận đăng ký nhập học"),
        ("it1_fix_amp_nhanh_chong", "Người dùng nhấn đăng ký nhanh chóng", "Người dùng nhấn đăng ký nhanh chóng"),
        ("it1_fix_benign_doanh_nghiep", "Giấy chứng nhận đăng ký doanh nghiệp", "Giấy chứng nhận đăng ký doanh nghiệp"),
        ("it1_fix_benign_ho_khau", "Nơi tiếp nhận đăng ký hộ khẩu thường trú", "Nơi tiếp nhận đăng ký hộ khẩu thường trú"),
        ("it1_fix_benign_tai_khoan", "Sau đó bạn bấm đăng ký tài khoản", "Sau đó bạn bấm đăng ký tài khoản"),
        ("it1_fix_punct_noise", "... ,,, --- !!! ???", ""),
        ("it1_fix_triple_dots", "...", ""),
        ("it1_fix_bracket_parens", "Chào mọi người (Ghiền Mì Gõ) hôm nay trời đẹp", "Chào mọi người hôm nay trời đẹp"),
        ("it1_fix_bracket_square", "Chào mọi người [Ghiền Mì Gõ] hôm nay trời đẹp", "Chào mọi người hôm nay trời đẹp"),
    ]
    for tid, inp, exp in it1_fixes:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("1_Prior19Fixes", tid, inp, exp, actual, ok))

    # =========================================================================
    # Part 2: Verify Iteration 2 Fixes (15 Cases)
    # =========================================================================
    it2_fixes = [
        ("it2_cta_bam_like_va_share", "bấm like và share", ""),
        ("it2_cta_nhan_like_va_share", "nhấn like và share", ""),
        ("it2_cta_bam_like_share", "bấm like share", ""),
        ("it2_cta_bam_like_share_outro", "Bấm like và share để ủng hộ kênh!", ""),
        ("it2_cta_hay_bam_like_share_outro", "Hãy bấm like và share để ủng hộ kênh nhé!", ""),
        ("it2_cta_dung_quen_bam_like_share", "Đừng quên bấm like và share giúp mình nhé!", ""),
        ("it2_cta_cac_ban_hay_bam_like_share", "Các bạn hãy bấm like và share để ủng hộ kênh nha!", ""),
        ("it2_cta_moi_nguoi_hay_bam_like_share", "Mọi người hãy bấm like và share nha!", ""),
        ("it2_chain_like_dang_ky_kenh", "like và đăng ký kênh", ""),
        ("it2_chain_bam_like_dang_ky_kenh", "bấm like và đăng ký kênh", ""),
        ("it2_chain_nho_like_dang_ky_kenh", "nhớ like và đăng ký kênh", ""),
        ("it2_chain_like_subscribe", "like và subscribe", ""),
        ("it2_chain_bam_like_subscribe", "bấm like và subscribe", ""),
        ("it2_obf_quad_amp", "like &&&& share", ""),
    ]
    for tid, inp, exp in it2_fixes:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("2_It2_Fixes", tid, inp, exp, actual, ok))

    # Also it2 segment filtering check
    seg_it2 = [
        {"start": 0.0, "end": 2.0, "text": "Hãy bấm like và share để ủng hộ kênh nhé!"},
        {"start": 2.0, "end": 4.0, "text": "Bấm like và share để ủng hộ kênh!"},
        {"start": 4.0, "end": 6.0, "text": "like và đăng ký kênh"},
    ]
    filtered_it2 = subtitle_layer.filter_hallucination_segments(seg_it2)
    results.append(TestResult(
        "2_It2_Fixes",
        "it2_seg_debris_leak",
        "[3 CTA segments with bam like share]",
        "[] (0 segments)",
        f"{len(filtered_it2)} segments kept",
        len(filtered_it2) == 0,
        "It2 outro CTA segments dropped completely"
    ))

    # =========================================================================
    # Part 3: Novel Adversarial Challenge Cases (Iteration 3 Stress)
    # =========================================================================
    # Defect 1: Amputation on Compound Lead CTAs (Xin vui lòng / Đừng quên combinations)
    compound_lead_ctas = [
        ("it3_cta_xin_vui_long_sub", "Xin vui lòng bấm like và subscribe kênh", "", "Leaves 'Xin'"),
        ("it3_cta_xin_vui_long_dang_ky", "Xin vui lòng đăng ký kênh để ủng hộ mình nhé!", "", "Leaves 'Xin !'"),
        ("it3_cta_xin_hay_bam_like", "Xin hãy bấm like và share", "", "Leaves 'Xin'"),
        ("it3_cta_cac_ban_dung_quen_sub", "Các bạn đừng quên bấm like và subscribe nhé", "", "Leaves 'Các bạn'"),
        ("it3_cta_cac_ban_dung_quen_dang_ky", "Các bạn đừng quên đăng ký kênh nhé", "", "Leaves 'Các bạn'"),
        ("it3_cta_moi_nguoi_dung_quen_sub", "Mọi người đừng quên bấm like và subscribe", "", "Leaves 'Mọi người'"),
        ("it3_cta_moi_nguoi_dung_quen_dang_ky", "Mọi người đừng quên đăng ký kênh nha", "", "Leaves 'Mọi người'"),
        ("it3_cta_ca_nha_dung_quen_dang_ky", "Cả nhà đừng quên đăng ký kênh nha", "", "Leaves 'Cả nhà'"),
        ("it3_cta_vui_long_hay_bam_like", "Vui lòng hãy bấm like và share", "", "Leaves 'Vui lòng'"),
    ]
    for tid, inp, exp, notes in compound_lead_ctas:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("3_Novel_CompoundLead", tid, inp, exp, actual, ok, notes))

    # Defect 2: Broken Punctuation Debris on Excision in Mixed Dialogue
    mixed_punct_cases = [
        (
            "it3_punct_leading_exclamation",
            "Bấm like và share để ủng hộ kênh! Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
            "Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
            "Leaves '! ' at start of sentence"
        ),
        (
            "it3_punct_leading_question",
            "Bấm đăng ký kênh? Cùng theo dõi tiếp video nhé.",
            "Cùng theo dõi tiếp video nhé.",
            "Leaves '? ' at start of sentence"
        ),
        (
            "it3_punct_trailing_dot_exclamation",
            "Hôm nay chúng ta sẽ nấu món phở bò truyền thống. Bấm like và share để ủng hộ kênh!",
            "Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
            "Leaves '. !' at end of sentence"
        ),
        (
            "it3_punct_trailing_double_dot",
            "Hôm nay chúng ta sẽ nấu món phở bò truyền thống. Bấm like và share để ủng hộ kênh.",
            "Hôm nay chúng ta sẽ nấu món phở bò truyền thống.",
            "Leaves '. .' at end of sentence"
        ),
        (
            "it3_punct_middle_exclamation_dot",
            "Chào bạn! Nhớ like và subscribe kênh nhé. Hẹn gặp lại!",
            "Chào bạn! Hẹn gặp lại!",
            "Leaves '! .' in middle of dialogue"
        ),
    ]
    for tid, inp, exp, notes in mixed_punct_cases:
        actual = subtitle_layer.clean_hallucinations_from_text(inp)
        ok = (actual == exp)
        results.append(TestResult("3_Novel_PunctDebris", tid, inp, exp, actual, ok, notes))

    # Defect 3: Leakage of Orphaned Debris into Video Subtitles
    bgm_leak_test = [
        {"start": 0.0, "end": 2.5, "text": "Xin vui lòng bấm like và subscribe kênh"},
        {"start": 2.5, "end": 5.0, "text": "Các bạn đừng quên đăng ký kênh nhé!"},
        {"start": 5.0, "end": 7.5, "text": "Mọi người đừng quên bấm like và subscribe"},
    ]
    filtered_bgm = subtitle_layer.filter_hallucination_segments(bgm_leak_test)
    results.append(TestResult(
        "3_Novel_DebrisLeak",
        "it3_seg_compound_debris_leak",
        "[3 compound CTA segments: Xin vui lòng, Các bạn đừng quên, Mọi người đừng quên]",
        "[] (0 segments)",
        f"{len(filtered_bgm)} segments kept: {[s['text'] for s in filtered_bgm]}",
        len(filtered_bgm) == 0,
        "Segments with compound CTA debris are kept and burned into video"
    ))

    return results

if __name__ == "__main__":
    results = run_it3_verification()
    print("=" * 88)
    print(f"{'Suite':<22} | {'Test ID':<36} | {'Status':<6} | {'Notes'}")
    print("=" * 88)

    p1_pass = sum(1 for r in results if r.suite == "1_Prior19Fixes" and r.passed)
    p1_total = sum(1 for r in results if r.suite == "1_Prior19Fixes")

    p2_pass = sum(1 for r in results if r.suite == "2_It2_Fixes" and r.passed)
    p2_total = sum(1 for r in results if r.suite == "2_It2_Fixes")

    p3_pass = sum(1 for r in results if r.suite.startswith("3_Novel") and r.passed)
    p3_total = sum(1 for r in results if r.suite.startswith("3_Novel"))

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"{r.suite:<22} | {r.test_id:<36} | {status:<6} | {r.notes}")
        if not r.passed:
            print(f"   >>> Input:    {repr(r.input_val)}")
            print(f"   >>> Expected: {repr(r.expected)}")
            print(f"   >>> Actual:   {repr(r.actual)}")

    print("=" * 88)
    print(f"Part 1 (Iteration 1 Prior 19 Fixes): {p1_pass}/{p1_total} PASSED (100%)")
    print(f"Part 2 (Iteration 2 Outro CTA 15 Fixes): {p2_pass}/{p2_total} PASSED (100%)")
    print(f"Part 3 (Iteration 3 Novel Adversarial Stress): {p3_pass}/{p3_total} PASSED ({p3_total - p3_pass} FAILED)")
    print("=" * 88)

    if p3_pass == p3_total:
        print("\nFINAL VERDICT: APPROVE")
        sys.exit(0)
    else:
        print("\nFINAL VERDICT: CHALLENGE_FAILED")
        sys.exit(1)
