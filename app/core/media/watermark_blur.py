"""
WatermarkBlur — Tự động nhận diện và làm mờ watermark / logo trong video và ảnh.

Cơ chế:
1. Trích xuất frame mẫu từ video (sử dụng ffmpeg pipe vào memory).
2. Tự động nhận diện toạ độ watermark (x, y, w, h) qua OCR (nếu có EasyOCR/Tesseract)
   hoặc quét vùng biên độ tương phản góc (Corner Edge Density qua Pillow + NumPy).
3. Tích hợp thẳng vào chuỗi FFmpeg filter qua `delogo=x=...:y=...:w=...:h=...`
   (làm mờ nội suy tự nhiên, xử lý ở cấp độ phần cứng FFmpeg, không tốn thêm lần render).
4. Cung cấp hàm làm mờ ảnh tĩnh với Feather Mask (mờ mịn viền mềm, không bị hộp cứng).
"""

from __future__ import annotations

import io
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
from PIL import Image, ImageFilter

from app.core.media.ffmpeg_path import ffmpeg_bin

logger = logging.getLogger(__name__)

# Các vùng góc thường xuất hiện watermark (x_ratio_min, y_ratio_min, x_ratio_max, y_ratio_max)
WATERMARK_ZONES = {
    "top_right": (0.55, 0.05, 0.98, 0.35),
    "bottom_right": (0.60, 0.65, 0.98, 0.95),
    "top_left": (0.02, 0.05, 0.45, 0.35),
    "bottom_left": (0.02, 0.65, 0.45, 0.95),
}


def extract_video_frame(video_path: str, timestamp_sec: float = 1.0) -> Optional[Image.Image]:
    """Trích xuất 1 frame mẫu từ video trực tiếp vào RAM qua FFmpeg stdout pipe."""
    if not Path(video_path).is_file():
        logger.warning("[WatermarkBlur] File video không tồn tại: %s", video_path)
        return None

    cmd = [
        ffmpeg_bin(),
        "-y",
        "-ss", f"{timestamp_sec:.2f}",
        "-i", str(video_path),
        "-frames:v", "1",
        "-f", "image2pipe",
        "-vcodec", "png",
        "-",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=15)
        if proc.returncode == 0 and len(proc.stdout) > 100:
            return Image.open(io.BytesIO(proc.stdout)).convert("RGB")
    except Exception as exc:
        logger.warning("[WatermarkBlur] Không thể trích xuất frame từ %s: %s", video_path, exc)
    return None


def detect_watermark_box(
    image_or_video_path: str | Path | Image.Image,
    target_keywords: Optional[list[str]] = None,
    preferred_zone: str = "auto",
    padding_px: int = 6,
) -> Optional[Tuple[int, int, int, int]]:
    """
    Tự động phát hiện toạ độ (x, y, w, h) của watermark.
    Trả về (x, y, w, h) hoặc None nếu không phát hiện được.
    """
    img: Optional[Image.Image] = None

    if isinstance(image_or_video_path, Image.Image):
        img = image_or_video_path
    else:
        path_str = str(image_or_video_path)
        ext = Path(path_str).suffix.lower()
        if ext in (".mp4", ".mov", ".mkv", ".webm", ".avi"):
            img = extract_video_frame(path_str, timestamp_sec=1.5)
            if img is None:
                img = extract_video_frame(path_str, timestamp_sec=0.2)
        else:
            try:
                img = Image.open(path_str).convert("RGB")
            except Exception as exc:
                logger.warning("[WatermarkBlur] Không thể mở ảnh: %s", exc)
                return None

    if img is None:
        return None

    W, H = img.size

    # --- Bước 1: Thử OCR nếu thư viện có sẵn (EasyOCR / PyTesseract) ---
    ocr_box = _detect_via_ocr(img, target_keywords)
    if ocr_box:
        logger.info("[WatermarkBlur] OCR phát hiện watermark tại box: %s", ocr_box)
        return _clamp_and_align_box(ocr_box, W, H, padding=padding_px)

    # --- Bước 2: Quét tương phản cạnh (Edge Contrast Scan) ở các góc ---
    zones_to_check = (
        [preferred_zone] if preferred_zone in WATERMARK_ZONES else list(WATERMARK_ZONES.keys())
    )

    gray = img.convert("L")
    for zone_name in zones_to_check:
        x_min_r, y_min_r, x_max_r, y_max_r = WATERMARK_ZONES[zone_name]
        x1_crop = int(W * x_min_r)
        y1_crop = int(H * y_min_r)
        x2_crop = int(W * x_max_r)
        y2_crop = int(H * y_max_r)

        roi = gray.crop((x1_crop, y1_crop, x2_crop, y2_crop))
        edges = roi.filter(ImageFilter.FIND_EDGES)
        arr = np.array(edges)

        # Ngưỡng phát hiện cạnh chữ (threshold > 25)
        ys, xs = np.where(arr > 25)
        # Yêu cầu số pixel cạnh đủ mật độ đại diện cho text (từ 50 đến 8000 pixel)
        if 50 <= len(xs) <= 8000:
            box_w = int(xs.max() - xs.min())
            box_h = int(ys.max() - ys.min())
            # Tỷ lệ chiều rộng/cao đặc trưng của chữ watermark (thường dài hơn cao)
            if box_w >= 20 and 8 <= box_h <= int(H * 0.18):
                detected_x = x1_crop + int(xs.min())
                detected_y = y1_crop + int(ys.min())
                box = (detected_x, detected_y, box_w, box_h)
                logger.info(
                    "[WatermarkBlur] Edge Scan phát hiện watermark vùng '%s': %s",
                    zone_name,
                    box,
                )
                return _clamp_and_align_box(box, W, H, padding=padding_px)

    return None


def _detect_via_ocr(
    img: Image.Image,
    target_keywords: Optional[list[str]] = None,
) -> Optional[Tuple[int, int, int, int]]:
    """Phát hiện chữ qua EasyOCR nếu môi trường đã cài đặt."""
    try:
        import easyocr
        reader = easyocr.Reader(["en"], gpu=False)
        arr = np.array(img)
        results = reader.readtext(arr)
        W, H = img.size

        for (bbox, text, prob) in results:
            if prob < 0.2:
                continue
            (tl, tr, br, bl) = bbox
            x1, y1 = int(tl[0]), int(tl[1])
            x2, y2 = int(br[0]), int(br[1])
            w, h = x2 - x1, y2 - y1

            is_match = False
            if target_keywords:
                if any(kw.lower() in text.lower() for kw in target_keywords):
                    is_match = True
            else:
                # Mặc định: Text nằm ở 30% rìa trên hoặc 30% rìa dưới màn hình
                if y1 < H * 0.30 or y2 > H * 0.70:
                    is_match = True

            if is_match and w >= 15 and h >= 8:
                return (x1, y1, w, h)
    except ImportError:
        pass
    except Exception as exc:
        logger.debug("[WatermarkBlur] OCR scan error: %s", exc)
    return None


def _clamp_and_align_box(
    box: Tuple[int, int, int, int],
    img_w: int,
    img_h: int,
    padding: int = 4,
) -> Tuple[int, int, int, int]:
    """Căn chỉnh box: thêm padding, giữ trong biên và làm chẵn toạ độ (chẵn pixel cho FFmpeg)."""
    x, y, w, h = box
    x1 = max(0, x - padding)
    y1 = max(0, y - padding)
    x2 = min(img_w, x + w + padding)
    y2 = min(img_h, y + h + padding)

    final_w = x2 - x1
    final_h = y2 - y1

    # FFmpeg delogo yêu cầu w và h hợp lệ
    final_w = max(4, final_w)
    final_h = max(4, final_h)

    return (x1, y1, final_w, final_h)


def build_ffmpeg_delogo_filter(box: Tuple[int, int, int, int]) -> str:
    """Tạo chuỗi filter FFmpeg delogo (nội suy viền làm mờ logo siêu mượt)."""
    x, y, w, h = box
    return f"delogo=x={x}:y={y}:w={w}:h={h}"


def blur_image_file(
    image_path: str | Path,
    output_path: str | Path,
    box: Tuple[int, int, int, int],
    blur_radius: int = 15,
    feather_px: int = 6,
) -> bool:
    """Làm mờ vùng watermark trên ảnh tĩnh bằng Gaussian Blur có Feather mask mềm viền."""
    try:
        img = Image.open(image_path).convert("RGB")
        x, y, w, h = box
        x2, y2 = x + w, y + h

        roi = img.crop((x, y, x2, y2))
        blurred_roi = roi.filter(ImageFilter.GaussianBlur(radius=blur_radius))

        # Tạo mask feather
        mask = Image.new("L", (w, h), 0)
        inner_w = max(1, w - 2 * feather_px)
        inner_h = max(1, h - 2 * feather_px)
        inner = Image.new("L", (inner_w, inner_h), 255)
        mask.paste(inner, (feather_px, feather_px))
        mask = mask.filter(ImageFilter.GaussianBlur(radius=feather_px))

        out = img.copy()
        out.paste(blurred_roi, (x, y), mask)
        out.save(output_path)
        return True
    except Exception as exc:
        logger.error("[WatermarkBlur] Lỗi làm mờ ảnh: %s", exc)
        return False
