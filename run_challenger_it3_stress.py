"""
Empirical Challenger Verification Suite - Iteration 3
Rigorous Adversarial Stress-Testing for Subtitle Generation and Burning Pipeline.

Test Dimensions:
1. Pure BGM Transcripts (1 to 50 segments):
   - 1A: Pure BGM / Hallucinations without audio tag defects (1, 2, 5, 10, 20, 50 segments).
   - 1B: Pure BGM containing Whisper audio tag variants (including `(tiếng cười)`, `[tiếng cười]`).
2. Mixed Transcripts & ASS Generation Integrity:
   - 2A: Mixed dialogue + CTA / BGM excision without bracket terminal punctuation.
   - 2B: Mixed dialogue with bracketed hallucinations ending in `!` or `?` (e.g. `(bấm subscribe kênh!)`).
3. Concurrency, Memory Safety, and Malformed Segment Dictionaries:
   - 3A: Malformed segment dictionaries (missing keys, non-dict types, invalid types).
   - 3B: IEEE-754 anomalous float timestamps (`NaN`, `Inf`) in `keep_speech_segments` and `build_ass`.
   - 3C: Concurrency stress (16 simultaneous worker threads running pipeline tasks).
   - 3D: Memory safety and file descriptor leakage (5,000 segments processed).
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
from typing import Any, Callable

import pysubs2

from app.features.viral_intake import subtitle_layer


class TestResult:
    def __init__(
        self,
        section: str,
        test_id: str,
        passed: bool,
        details: str = "",
        error: str | None = None,
    ):
        self.section = section
        self.test_id = test_id
        self.passed = passed
        self.details = details
        self.error = error


class ChallengerSuite:
    def __init__(self):
        self.results: list[TestResult] = []
        self.temp_dir = tempfile.mkdtemp(prefix="challenger_it3_")
        self.dummy_video_path = os.path.join(self.temp_dir, "base_dummy_video.mp4")
        self._generate_dummy_video(self.dummy_video_path)
        self.dummy_video_hash = self._file_hash(self.dummy_video_path)
        self.dummy_video_size = os.path.getsize(self.dummy_video_path)

    def _generate_dummy_video(self, path: str):
        """Generate a valid 2-second MP4 video with an audio track using ffmpeg."""
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=2:size=320x240:rate=10",
            "-f", "lavfi", "-i", "sine=frequency=1000:duration=2",
            "-c:v", "libx264", "-c:a", "aac",
            path,
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        if res.returncode != 0 or not os.path.isfile(path):
            raise RuntimeError(f"Failed to generate dummy video: {res.stderr}")

    def _file_hash(self, path: str) -> str:
        if not os.path.isfile(path):
            return ""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    def record(self, section: str, test_id: str, passed: bool, details: str = "", error: str | None = None):
        res = TestResult(section, test_id, passed, details, error)
        self.results.append(res)
        status = "PASS" if passed else "FAIL"
        err_msg = f" | ERROR: {error}" if error else ""
        print(f"[{status}] {section} :: {test_id} - {details}{err_msg}")

    # =========================================================================
    # SECTION 1A: Pure BGM Transcripts (Standard Hallucinations, 1 to 50 Segments)
    # =========================================================================
    def run_section_1a_pure_bgm_standard(self):
        print("\n" + "=" * 70)
        print("SECTION 1A: Pure BGM Transcripts (Standard Hallucinations, 1 to 50)")
        print("=" * 70)

        standard_bgm_phrases = [
            "[nhạc]",
            "(âm nhạc)",
            "[nhạc nền]",
            "[music]",
            "(tiếng vỗ tay)",
            "(tiếng động)",
            "ghiền mì gõ",
            "ghien mi go",
            "---ghien mi go---",
            "lala school",
            "lala... school",
            "bấm subscribe",
            "đăng ký kênh",
            "đăng ký... kênh",
            "like and share",
            "like   &&   share",
            "like &&&& share",
            "bấm like và share",
            "nhấn like share",
            "Bấm like và share để ủng hộ kênh!",
            "Hãy bấm like và share để ủng hộ kênh nhé!",
            "Đừng quên bấm like và share giúp mình nhé!",
            "Các bạn hãy bấm like và share để ủng hộ kênh nha!",
            "Mọi người hãy bấm like và share nha!",
            "like và đăng ký kênh",
            "bấm like và đăng ký kênh",
            "nhớ like và đăng ký kênh",
            "like và subscribe",
            "bấm like và subscribe",
            "... ,,, --- !!! ???",
            "...",
            "---",
            "ghiền... mì... gõ",
            "ghiền. mì. gõ",
            "ghiền / mì / gõ",
            "ghiền mỳ gõ",
            "GHIỀN MÌ GÕ",
            "[GHIỀN MÌ GÕ]",
            "like... and... share",
            "bấm like và share",
            "nhấn like và share",
            "bấm like share",
            "   ",
            "",
        ]

        counts_to_test = [1, 2, 5, 10, 20, 35, 50]

        for n in counts_to_test:
            test_id = f"standard_pure_bgm_n_{n:02d}"
            segments = []
            for i in range(n):
                phrase = standard_bgm_phrases[i % len(standard_bgm_phrases)]
                seg = {
                    "start": float(i * 2.0),
                    "end": float(i * 2.0 + 1.8),
                    "text": phrase,
                }
                if i % 3 == 0:
                    seg["no_speech_prob"] = 0.85
                if i % 5 == 0:
                    seg["compression_ratio"] = 2.8
                segments.append(seg)

            test_dir = tempfile.mkdtemp(prefix=f"test_std_bgm_{n}_", dir=self.temp_dir)
            input_copy = os.path.join(test_dir, f"input_{n}.mp4")
            shutil.copyfile(self.dummy_video_path, input_copy)
            output_video = os.path.join(test_dir, f"output_{n}.mp4")
            expected_tmp_ass = os.path.splitext(output_video)[0] + ".sub.tmp.ass"

            burn_called = []
            orig_burn = subtitle_layer.burn

            def spy_burn(*args, **kwargs):
                burn_called.append(True)
                return orig_burn(*args, **kwargs)

            orig_transcribe = subtitle_layer.transcribe_words

            def mock_transcribe(*args, **kwargs):
                return [dict(s) for s in segments]

            try:
                subtitle_layer.burn = spy_burn
                subtitle_layer.transcribe_words = mock_transcribe

                res = subtitle_layer.apply(input_copy, output_video)

                cond1 = (res is False)
                cond2 = (len(burn_called) == 0)
                cond3 = (not os.path.exists(output_video))
                cond4 = (not os.path.exists(expected_tmp_ass))
                cond5 = (self._file_hash(input_copy) == self.dummy_video_hash)
                cond6 = (os.path.getsize(input_copy) == self.dummy_video_size)

                all_passed = cond1 and cond2 and cond3 and cond4 and cond5 and cond6
                details = (
                    f"res={res}, burn_called={len(burn_called)}, "
                    f"out_exists={os.path.exists(output_video)}, tmp_ass={os.path.exists(expected_tmp_ass)}, "
                    f"input_intact={cond5 and cond6}"
                )
                self.record("Section1A_PureBGM_Standard", test_id, all_passed, details)

            except Exception as e:
                self.record("Section1A_PureBGM_Standard", test_id, False, "Exception raised", str(e))
            finally:
                subtitle_layer.burn = orig_burn
                subtitle_layer.transcribe_words = orig_transcribe

    # =========================================================================
    # SECTION 1B: Pure BGM Transcripts with Audio Tag Defects ((tiếng cười))
    # =========================================================================
    def run_section_1b_pure_bgm_audio_tag_defects(self):
        print("\n" + "=" * 70)
        print("SECTION 1B: Pure BGM Audio Tag Defects (Whisper Laughter & Audio Tags)")
        print("=" * 70)

        # Test audio tag phrases that Whisper emits on background noise/laughter
        tag_cases = [
            ("audio_tag_tieng_cuoi_parens", "(tiếng cười)"),
            ("audio_tag_tieng_cuoi_brackets", "[tiếng cười]"),
            ("audio_tag_tieng_cuoi_no_diacritic", "(tieng cuoi)"),
            ("audio_tag_music_parens", "(music)"),
            ("audio_tag_nhac_nen_parens", "(nhạc nền)"),
        ]

        for tid, tag in tag_cases:
            cleaned = subtitle_layer.clean_hallucinations_from_text(tag)
            passed = (cleaned == "")
            details = f"Input: {tag!r} -> Cleaned: {cleaned!r} (expected '')"
            err = f"Audio tag {tag!r} failed to be cleaned by _AUDIO_TAG_RE" if not passed else None
            self.record("Section1B_AudioTagDefect", tid, passed, details, error=err)

        # Verify impact on apply(): A 1-segment pure BGM video with (tiếng cười)
        test_dir = tempfile.mkdtemp(prefix="test_cuoi_apply_", dir=self.temp_dir)
        input_copy = os.path.join(test_dir, "input_cuoi.mp4")
        shutil.copyfile(self.dummy_video_path, input_copy)
        output_video = os.path.join(test_dir, "output_cuoi.mp4")

        orig_transcribe = subtitle_layer.transcribe_words
        burn_called = []
        orig_burn = subtitle_layer.burn

        def spy_burn(*args, **kwargs):
            burn_called.append(True)
            return orig_burn(*args, **kwargs)

        try:
            subtitle_layer.burn = spy_burn
            subtitle_layer.transcribe_words = lambda *a, **k: [
                {"start": 0.0, "end": 1.5, "text": "(tiếng cười)"}
            ]
            res = subtitle_layer.apply(input_copy, output_video)
            passed = (res is False) and (len(burn_called) == 0) and not os.path.exists(output_video)
            details = f"res={res}, burn_called={len(burn_called)}, out_exists={os.path.exists(output_video)}"
            err = "Pure BGM video with (tiếng cười) triggered burn() and burned subtitle!" if not passed else None
            self.record("Section1B_AudioTagDefect", "apply_pure_bgm_tieng_cuoi", passed, details, error=err)
        finally:
            subtitle_layer.burn = orig_burn
            subtitle_layer.transcribe_words = orig_transcribe

    # =========================================================================
    # SECTION 2A: Mixed Transcripts Clean Excision (Standard)
    # =========================================================================
    def run_section_2a_mixed_transcripts_clean(self):
        print("\n" + "=" * 70)
        print("SECTION 2A: Mixed Transcripts Clean Dialogue Excision")
        print("=" * 70)

        mixed_scenarios = [
            {
                "id": "mixed_lead_in_junk",
                "segments": [
                    {"start": 0.0, "end": 2.5, "text": "[Ghiền Mì Gõ] Chào mừng mọi người đến với kênh ẩm thực"},
                    {"start": 2.5, "end": 4.5, "text": "Hôm nay chúng ta sẽ nấu món canh chua cá lóc"},
                ],
                "expected_clean": [
                    "Chào mừng mọi người đến với kênh ẩm thực",
                    "Hôm nay chúng ta sẽ nấu món canh chua cá lóc",
                ],
            },
            {
                "id": "mixed_outro_cta_variants",
                "segments": [
                    {"start": 0.0, "end": 3.0, "text": "Nêm nếm gia vị vừa ăn rồi tắt bếp"},
                    {"start": 3.0, "end": 6.0, "text": "Chúc các bạn thành công, hãy bấm like và share để ủng hộ kênh nhé!"},
                    {"start": 6.0, "end": 8.0, "text": "bấm like và subscribe"},
                ],
                "expected_clean": [
                    "Nêm nếm gia vị vừa ăn rồi tắt bếp",
                    "Chúc các bạn thành công",
                ],
            },
            {
                "id": "mixed_interspersed_pure_and_mixed",
                "segments": [
                    {"start": 0.0, "end": 1.5, "text": "[nhạc nền] (tiếng vỗ tay)"},
                    {"start": 1.5, "end": 3.5, "text": "Bước đầu tiên là sơ chế nguyên liệu thật sạch"},
                    {"start": 3.5, "end": 5.0, "text": "like &&&& share"},
                    {"start": 5.0, "end": 7.0, "text": "Cắt thịt thành từng lát mỏng vừa ăn (lala school) rồi ướp tiêu"},
                    {"start": 7.0, "end": 8.5, "text": "... ,,, ---"},
                    {"start": 8.5, "end": 10.5, "text": "Cảm ơn các bạn đã theo dõi, nhớ like và đăng ký kênh nhé"},
                ],
                "expected_clean": [
                    "Bước đầu tiên là sơ chế nguyên liệu thật sạch",
                    "Cắt thịt thành từng lát mỏng vừa ăn rồi ướp tiêu",
                    "Cảm ơn các bạn đã theo dõi",
                ],
            },
            {
                "id": "mixed_chained_social_calls",
                "segments": [
                    {"start": 0.0, "end": 3.0, "text": "Mọi chi tiết xin liên hệ số điện thoại bên dưới"},
                    {"start": 3.0, "end": 5.5, "text": "Các bạn hãy bấm like và share để ủng hộ kênh nha!"},
                    {"start": 5.5, "end": 7.0, "text": "Hẹn gặp lại trong video ngày mai"},
                ],
                "expected_clean": [
                    "Mọi chi tiết xin liên hệ số điện thoại bên dưới",
                    "Hẹn gặp lại trong video ngày mai",
                ],
            },
            {
                "id": "mixed_benign_speech_preserved",
                "segments": [
                    {"start": 0.0, "end": 2.5, "text": "Giấy chứng nhận đăng ký doanh nghiệp đã hoàn tất"},
                    {"start": 2.5, "end": 5.0, "text": "Sau đó bạn bấm đăng ký tài khoản trên ứng dụng"},
                    {"start": 5.0, "end": 7.5, "text": "Tôi ăn mì gói và nghe tiếng gõ cửa lúc nửa đêm"},
                ],
                "expected_clean": [
                    "Giấy chứng nhận đăng ký doanh nghiệp đã hoàn tất",
                    "Sau đó bạn bấm đăng ký tài khoản trên ứng dụng",
                    "Tôi ăn mì gói và nghe tiếng gõ cửa lúc nửa đêm",
                ],
            },
        ]

        for scenario in mixed_scenarios:
            tid = scenario["id"]
            raw_segments = scenario["segments"]
            expected_texts = scenario["expected_clean"]

            filtered = subtitle_layer.filter_hallucination_segments(raw_segments)
            kept = subtitle_layer.keep_speech_segments(filtered)

            ass_path = os.path.join(self.temp_dir, f"{tid}.ass")
            subtitle_layer.build_ass(kept, ass_path)

            try:
                subs = pysubs2.load(ass_path, encoding="utf-8")
                events = list(subs.events)
                event_texts = [e.text.replace("\\N", " ").strip() for e in events]
                joined_event_text = " ".join(event_texts)
                all_expected_present = all(exp in joined_event_text for exp in expected_texts)
                valid_timestamps = all(e.start >= 0 and e.end > e.start for e in events)

                passed = all_expected_present and valid_timestamps
                details = f"events={len(events)}, all_expected={all_expected_present}, valid_ts={valid_timestamps}"
                self.record("Section2A_MixedClean", tid, passed, details)

            except Exception as e:
                self.record("Section2A_MixedClean", tid, False, "ASS parse/inspection failure", str(e))

    # =========================================================================
    # SECTION 2B: Mixed Transcripts with Bracket Punctuation Debris (( !), [ !])
    # =========================================================================
    def run_section_2b_mixed_bracket_punctuation_debris(self):
        print("\n" + "=" * 70)
        print("SECTION 2B: Bracket Punctuation Debris Excision Defect")
        print("=" * 70)

        bracket_cases = [
            ("bracket_exclamation_subscribe", "Chào bạn (bấm subscribe kênh!) hôm nay thế nào?", "Chào bạn hôm nay thế nào?"),
            ("bracket_exclamation_ghien_mi_go", "Sản phẩm này [Ghiền Mì Gõ!] mang lại hiệu quả cao", "Sản phẩm này mang lại hiệu quả cao"),
            ("bracket_exclamation_like_share", "Đặc biệt (like & share!) rất hấp dẫn", "Đặc biệt rất hấp dẫn"),
            ("bracket_question_ghien_mi_go", "Thời sự hôm nay [Ghiền Mì Gõ?] có gì mới", "Thời sự hôm nay có gì mới"),
        ]

        for tid, inp, exp in bracket_cases:
            actual = subtitle_layer.clean_hallucinations_from_text(inp)
            has_debris = bool(re.search(r"[\(\[\{]\s*[!\?]+\s*[\)\]\}]", actual))
            passed = (actual == exp) and not has_debris
            details = f"Input: {inp!r} -> Actual: {actual!r}"
            err = f"Left orphaned bracket debris in middle of sentence: {actual!r}" if not passed else None
            self.record("Section2B_BracketDebris", tid, passed, details, error=err)

        # Build ASS for bracketed text and verify whether ASS contains ( !) or [ !]
        test_seg = [{"start": 0.0, "end": 3.0, "text": "Đặc biệt (bấm subscribe kênh!) rất hấp dẫn"}]
        kept = subtitle_layer.keep_speech_segments(subtitle_layer.filter_hallucination_segments(test_seg))
        ass_path = os.path.join(self.temp_dir, "ass_bracket_debris.ass")
        subtitle_layer.build_ass(kept, ass_path)
        subs = pysubs2.load(ass_path)
        ass_text = subs.events[0].text if subs.events else ""
        ass_has_debris = "( !)" in ass_text or "[ !]" in ass_text
        self.record(
            "Section2B_BracketDebris",
            "ass_event_contains_bracket_debris",
            not ass_has_debris,
            f"ASS Event Text: {ass_text!r}",
            error="ASS file contains '( !)' residue burned into subtitles!" if ass_has_debris else None,
        )

    # =========================================================================
    # SECTION 3A: Malformed Dictionaries Safe Handling
    # =========================================================================
    def run_section_3a_malformed_dictionaries(self):
        print("\n" + "=" * 70)
        print("SECTION 3A: Malformed Segment Dictionaries Robustness")
        print("=" * 70)

        malformed_cases = [
            ("malformed_none_in_list", [None, None]),
            ("malformed_non_dict_types", ["string", 123, [1, 2], True]),
            ("malformed_empty_dicts", [{}, {}, {"key": "val"}]),
            ("malformed_missing_text", [{"start": 1.0, "end": 2.0}]),
            ("malformed_text_none", [{"start": 1.0, "end": 2.0, "text": None}]),
            ("malformed_text_int", [{"start": 1.0, "end": 2.0, "text": 12345}]),
            ("malformed_text_dict", [{"start": 1.0, "end": 2.0, "text": {"inner": "text"}}]),
            ("malformed_missing_timestamps", [{"text": "Xin chào"}]),
            ("malformed_invalid_timestamps", [{"start": "abc", "end": "xyz", "text": "Xin chào"}]),
            ("malformed_none_timestamps", [{"start": None, "end": None, "text": "Xin chào"}]),
            ("malformed_inverted_timestamps", [{"start": 5.0, "end": 2.0, "text": "Ngược thời gian"}]),
            ("malformed_equal_timestamps", [{"start": 3.0, "end": 3.0, "text": "Bằng thời gian"}]),
            ("malformed_no_speech_invalid", [{"start": 1.0, "end": 2.0, "text": "Test", "no_speech_prob": "invalid"}]),
            ("malformed_ratio_invalid", [{"start": 1.0, "end": 2.0, "text": "Test", "compression_ratio": [1, 2]}]),
            ("malformed_massive_text", [{"start": 1.0, "end": 2.0, "text": "A" * 50000}]),
        ]

        for tid, segs in malformed_cases:
            try:
                filtered = subtitle_layer.filter_hallucination_segments(segs)
                kept = subtitle_layer.keep_speech_segments(segs)
                ass_out = os.path.join(self.temp_dir, f"{tid}.ass")
                subtitle_layer.build_ass(kept, ass_out)
                self.record("Section3A_Malformed", tid, True, f"Handled safely: filtered={len(filtered)}, kept={len(kept)}")
            except Exception as e:
                self.record("Section3A_Malformed", tid, False, "Raised exception", str(e))

    # =========================================================================
    # SECTION 3B: IEEE-754 Anomalous Floats (NaN / Inf) in Pipeline
    # =========================================================================
    def run_section_3b_nan_inf_timestamps(self):
        print("\n" + "=" * 70)
        print("SECTION 3B: IEEE-754 Anomalous Floats (NaN / Inf) in Pipeline")
        print("=" * 70)

        # Test keep_speech_segments behavior with NaN and Inf
        segs = [
            {"start": float("nan"), "end": 2.0, "text": "NaN segment"},
            {"start": 1.0, "end": float("inf"), "text": "Inf segment"},
        ]
        kept = subtitle_layer.keep_speech_segments(segs)
        nan_dropped = not any(math.isnan(s.get("start", 0)) for s in kept)
        inf_dropped = not any(math.isinf(s.get("end", 0)) for s in kept)

        self.record(
            "Section3B_NaN_Inf",
            "keep_speech_segments_drops_nan",
            nan_dropped,
            f"Kept: {kept}",
            error="keep_speech_segments failed to drop segment with NaN start!" if not nan_dropped else None,
        )
        self.record(
            "Section3B_NaN_Inf",
            "keep_speech_segments_drops_inf",
            inf_dropped,
            f"Kept: {kept}",
            error="keep_speech_segments failed to drop segment with Inf end!" if not inf_dropped else None,
        )

        # Test build_ass behavior with NaN / Inf
        try:
            ass_nan = os.path.join(self.temp_dir, "test_nan.ass")
            subtitle_layer.build_ass([{"start": float("nan"), "end": 2.0, "text": "NaN"}], ass_nan)
            self.record("Section3B_NaN_Inf", "build_ass_nan_tolerance", True, "Handled safely")
        except Exception as e:
            self.record(
                "Section3B_NaN_Inf",
                "build_ass_nan_tolerance",
                False,
                "build_ass crashed on NaN timestamp",
                error=f"{type(e).__name__}: {e}",
            )

        try:
            ass_inf = os.path.join(self.temp_dir, "test_inf.ass")
            subtitle_layer.build_ass([{"start": 1.0, "end": float("inf"), "text": "Inf"}], ass_inf)
            self.record("Section3B_NaN_Inf", "build_ass_inf_tolerance", True, "Handled safely")
        except Exception as e:
            self.record(
                "Section3B_NaN_Inf",
                "build_ass_inf_tolerance",
                False,
                "build_ass crashed on Inf timestamp",
                error=f"{type(e).__name__}: {e}",
            )

    # =========================================================================
    # SECTION 3C: Concurrency Stress (16 Simultaneous Workers)
    # =========================================================================
    def run_section_3c_concurrency(self):
        print("\n" + "=" * 70)
        print("SECTION 3C: Concurrency Stress (16 Simultaneous Workers)")
        print("=" * 70)

        num_threads = 16
        tasks_per_thread = 2
        total_tasks = num_threads * tasks_per_thread
        concurrency_errors = []

        def worker_task(task_id: int):
            try:
                is_bgm = (task_id % 2 == 0)
                if is_bgm:
                    test_segs = [
                        {"start": 0.0, "end": 1.0, "text": "[nhạc] Ghiền Mì Gõ"},
                        {"start": 1.0, "end": 2.0, "text": "bấm like và share để ủng hộ kênh"},
                    ]
                else:
                    test_segs = [
                        {"start": 0.0, "end": 1.0, "text": "Chào mừng các bạn"},
                        {"start": 1.0, "end": 2.0, "text": "like and share"},
                    ]

                filtered = subtitle_layer.filter_hallucination_segments(test_segs)
                kept = subtitle_layer.keep_speech_segments(filtered)

                if is_bgm:
                    if len(kept) != 0:
                        concurrency_errors.append(f"Task {task_id}: pure BGM retained segments: {kept}")
                else:
                    if len(kept) != 1 or kept[0]["text"] != "Chào mừng các bạn":
                        concurrency_errors.append(f"Task {task_id}: mixed retained unexpected: {kept}")

                    ass_path = os.path.join(self.temp_dir, f"concurrent_{task_id}.ass")
                    subtitle_layer.build_ass(kept, ass_path)
                    if not os.path.isfile(ass_path):
                        concurrency_errors.append(f"Task {task_id}: ASS file not created")
                    else:
                        subs = pysubs2.load(ass_path)
                        if len(subs.events) != 1 or subs.events[0].text != "Chào mừng các bạn":
                            concurrency_errors.append(f"Task {task_id}: ASS text corrupted")

            except Exception as e:
                concurrency_errors.append(f"Task {task_id} failed with exception: {e}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_task, i) for i in range(total_tasks)]
            concurrent.futures.wait(futures)

        concurrency_passed = (len(concurrency_errors) == 0)
        self.record(
            "Section3C_Concurrency",
            "thread_pool_16_workers",
            concurrency_passed,
            f"Executed {total_tasks} tasks. Errors: {len(concurrency_errors)}",
            error="; ".join(concurrency_errors[:3]) if concurrency_errors else None,
        )

    # =========================================================================
    # SECTION 3D: Memory Safety & FD Leak Check (5000 Segments)
    # =========================================================================
    def run_section_3d_memory_and_fd(self):
        print("\n" + "=" * 70)
        print("SECTION 3D: Memory Safety & FD Leak Check (5,000 Segments)")
        print("=" * 70)

        large_segs = []
        for i in range(5000):
            large_segs.append({
                "start": float(i),
                "end": float(i + 0.9),
                "text": f"Câu thoại thử nghiệm số {i} với độ dài vừa phải để kiểm tra bộ nhớ",
            })

        def count_open_fds() -> int:
            try:
                return len(os.listdir("/proc/self/fd"))
            except Exception:
                return 0

        fds_before = count_open_fds()

        try:
            t0 = time.time()
            filtered_large = subtitle_layer.filter_hallucination_segments(large_segs)
            kept_large = subtitle_layer.keep_speech_segments(filtered_large)
            large_ass = os.path.join(self.temp_dir, "large_5000.ass")
            subtitle_layer.build_ass(kept_large, large_ass)
            elapsed = time.time() - t0

            fds_after = count_open_fds()
            fd_diff = fds_after - fds_before

            memory_passed = (len(kept_large) == 5000) and os.path.isfile(large_ass) and (fd_diff <= 2)
            details = f"5000 segs processed in {elapsed:.2f}s, fd_before={fds_before}, fd_after={fds_after}, diff={fd_diff}"
            self.record("Section3D_MemorySafety", "large_5000_segments_fd_leak", memory_passed, details)

        except Exception as e:
            self.record("Section3D_MemorySafety", "large_5000_segments_fd_leak", False, "Failed", str(e))

    def cleanup(self):
        try:
            shutil.rmtree(self.temp_dir)
        except Exception:
            pass

    def run_all(self) -> bool:
        try:
            self.run_section_1a_pure_bgm_standard()
            self.run_section_1b_pure_bgm_audio_tag_defects()
            self.run_section_2a_mixed_transcripts_clean()
            self.run_section_2b_mixed_bracket_punctuation_debris()
            self.run_section_3a_malformed_dictionaries()
            self.run_section_3b_nan_inf_timestamps()
            self.run_section_3c_concurrency()
            self.run_section_3d_memory_and_fd()
        finally:
            self.cleanup()

        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed

        print("\n" + "=" * 70)
        print(f"CHALLENGER IT3 FINAL AUDIT SUMMARY: {passed}/{total} PASSED ({failed} FAILED)")
        print("=" * 70)

        # Group failures by section
        if failed > 0:
            print("\nSUMMARY OF EMPIRICALLY CONFIRMED DEFECTS:")
            for r in self.results:
                if not r.passed:
                    print(f" - [{r.section}] {r.test_id}: {r.error}")

        if failed == 0:
            print("\n>>> FINAL VERDICT: APPROVE <<<\n")
            return True
        else:
            print("\n>>> FINAL VERDICT: CHALLENGE_FAILED <<<\n")
            return False


if __name__ == "__main__":
    suite = ChallengerSuite()
    success = suite.run_all()
    sys.exit(0 if success else 1)
