import unittest

from workers.maintenance import _extract_view_count, _humanize_yt_dlp_error, _metadata_has_video_stream


class TestMaintenanceMediaFilter(unittest.TestCase):
    def test_accepts_requested_download_with_video_codec(self):
        info = {
            "requested_downloads": [
                {"ext": "mp4", "vcodec": "h264", "acodec": "aac"},
            ]
        }
        self.assertTrue(_metadata_has_video_stream(info))

    def test_accepts_root_video_metadata(self):
        info = {"_type": "video", "ext": "mp4", "vcodec": "h264"}
        self.assertTrue(_metadata_has_video_stream(info))

    def test_rejects_audio_only_metadata(self):
        info = {
            "_type": "video",
            "ext": "mp3",
            "vcodec": "none",
            "formats": [
                {"ext": "mp3", "vcodec": "none", "acodec": "mp3"},
            ],
        }
        self.assertFalse(_metadata_has_video_stream(info))

    def test_rejects_missing_video_streams(self):
        info = {
            "requested_formats": [
                {"ext": "m4a", "vcodec": "none"},
                {"ext": "mp3", "vcodec": "none"},
            ]
        }
        self.assertFalse(_metadata_has_video_stream(info))

    def test_humanize_instagram_requires_login_without_source_account(self):
        msg = _humanize_yt_dlp_error(
            "instagram",
            "ERROR: [Instagram] abc: This content may be inappropriate: It's unavailable for certain audiences.",
            None,
        )
        self.assertIn("Create an ACTIVE instagram account", msg)

    def test_humanize_instagram_requires_relogin_with_source_account(self):
        source = type("SourceAccount", (), {"profile_path": "/tmp/ig"})()
        msg = _humanize_yt_dlp_error(
            "instagram",
            "ERROR: [Instagram] abc: This content may be inappropriate: It's unavailable for certain audiences.",
            source,
        )
        self.assertIn("Re-login the Instagram account", msg)

    def test_extract_view_count_uses_play_count_fallback(self):
        info = {"play_count": 4567}
        self.assertEqual(_extract_view_count(info), 4567)

    def test_extract_view_count_reads_first_entry(self):
        info = {"entries": [{"view_count": 8910}]}
        self.assertEqual(_extract_view_count(info), 8910)


if __name__ == "__main__":
    unittest.main()
