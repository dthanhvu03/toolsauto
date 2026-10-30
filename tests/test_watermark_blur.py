"""Tests for automatic watermark detection and blurring feature."""

from pathlib import Path
from PIL import Image

from app.core.media.watermark_blur import (
    build_ffmpeg_delogo_filter,
    blur_image_file,
    detect_watermark_box,
)
from app.features.viral_intake.reup_processor import ReupProcessor

SAMPLE_IMG = Path("/root/.gemini/antigravity/brain/7747b8d5-0dbd-4bec-975a-654c1a864b83/.user_uploaded/media_1793270416318_34634031.png")


def test_build_ffmpeg_delogo_filter():
    filter_str = build_ffmpeg_delogo_filter((615, 145, 100, 35))
    assert filter_str == "delogo=x=615:y=145:w=100:h=35"


def test_detect_watermark_box_on_sample_image():
    assert SAMPLE_IMG.exists(), "Sample image must exist for testing"
    box = detect_watermark_box(SAMPLE_IMG, preferred_zone="top_right")
    assert box is not None
    x, y, w, h = box
    assert x > 400
    assert y > 100
    assert w >= 20
    assert h >= 10


def test_blur_image_file(tmp_path):
    out_path = tmp_path / "blurred.png"
    ok = blur_image_file(SAMPLE_IMG, out_path, (615, 145, 100, 35), blur_radius=10, feather_px=4)
    assert ok is True
    assert out_path.exists()
    out_img = Image.open(out_path)
    assert out_img.size == (1024, 648)


def test_reup_processor_filter_chain_includes_delogo():
    vf, speed, applied = ReupProcessor._build_filter_chain(
        platform="youtube",
        width=1080,
        height=1920,
        preset="safe",
        watermark_box=(615, 145, 100, 35),
    )
    assert "delogo=x=615:y=145:w=100:h=35" in vf
    assert applied["watermark_box"] == (615, 145, 100, 35)
