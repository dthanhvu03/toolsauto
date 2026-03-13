"""
VideoProtector — Digital Rights Management (DRM) Module.

Provides:
1. Dynamic (moving) visible watermarking filter generation for FFmpeg.
2. Perceptual Fingerprinting (pHash) extraction and storage.
"""

import os
import json
import logging
import subprocess
import time
import shutil
from pathlib import Path
from PIL import Image
import imagehash

from app.config import BASE_DIR

logger = logging.getLogger(__name__)

# Where to store the pHash evidence log
EVIDENCE_FILE = BASE_DIR / "data" / "drm_evidence.json"

class VideoProtector:
    
    @classmethod
    def get_dynamic_watermark_filter(cls, text: str) -> str:
        """
        Generates an FFmpeg drawtext filter string for a dynamic, moving watermark.
        The text moves in a somewhat random/elliptical path to defeat static cropping.
        - Opacity: 30% (white@0.3)
        - Movement: Sine/Cosine based on time (t)
        """
        # x = w/2 + (w/3)*sin(t/2)
        # y = h/2 + (h/3)*cos(t/3)
        # This creates a non-repeating Lissajous-like curve
        return (
            f"drawtext=text='{text}':fontcolor=white@0.3:fontsize=(h/25):"
            f"x='(w-text_w)/2 + (w/3)*sin(t/2)':"
            f"y='(h-text_h)/2 + (h/3)*cos(t/3)'"
        )

    @classmethod
    def _get_video_duration(cls, video_path: str) -> float:
        """Helper to get video duration using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", video_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception as e:
            logger.warning("Failed to get duration for %s: %s", video_path, e)
            return 0.0

    @classmethod
    def extract_phash(cls, video_path: str, num_frames: int = 5) -> dict:
        """
        Extracts representative frames from the video and calculates their perceptual hash (pHash).
        Returns a dictionary of timestamps mapping to their pHash strings.
        """
        if not os.path.exists(video_path):
            return {}

        duration = cls._get_video_duration(video_path)
        if duration <= 0:
            return {}

        # Calculate timestamps (e.g., 10%, 30%, 50%, 70%, 90%)
        fractions = [(i + 0.5) / num_frames for i in range(num_frames)]
        timestamps = [duration * f for f in fractions]
        
        hashes = {}
        temp_dir = Path("/tmp/videoprotector")
        temp_dir.mkdir(parents=True, exist_ok=True)

        for i, ts in enumerate(timestamps):
            tmp_img = temp_dir / f"frame_{int(time.time())}_{i}.jpg"
            
            # Extract exactly 1 frame at the target timestamp
            cmd = [
                "ffmpeg", "-y", "-ss", str(ts), "-i", video_path,
                "-frames:v", "1", "-q:v", "2", str(tmp_img)
            ]
            
            try:
                subprocess.run(cmd, capture_output=True, check=True)
                if tmp_img.exists():
                    with Image.open(tmp_img) as img:
                        # Calculate pHash
                        h = imagehash.phash(img)
                        hashes[f"{ts:.2f}s"] = str(h)
                    
                    # Cleanup
                    tmp_img.unlink()
            except Exception as e:
                logger.error("Failed to extract pHash for frame at %ss: %s", ts, e)
                if tmp_img.exists():
                    tmp_img.unlink()

        return hashes

    @classmethod
    def extract_audio_fingerprint(cls, video_path: str) -> dict:
        """
        Extracts a Chromaprint audio fingerprint from a fixed 30s window (secs 10 to 40)
        of the video to save CPU/IO. Returns a dict with fingerprint and metadata.
        """
        if not os.path.exists(video_path):
            return {}
            
        # Check if fpcalc is installed
        if not shutil.which("fpcalc"):
            logger.warning("fpcalc not found. Audio fingerprinting skipped. Run: sudo apt install libchromaprint-tools")
            return {}

        duration_sec = cls._get_video_duration(video_path)
        if duration_sec <= 0:
            return {}
            
        # Only take a window if video is long enough, else take what's available
        start_time = 10 if duration_sec > 15 else 0
        window_duration = 30
        
        temp_dir = Path("/tmp/videoprotector")
        temp_dir.mkdir(parents=True, exist_ok=True)
        tmp_wav = temp_dir / f"audio_{int(time.time())}.wav"
        
        try:
            # Step 1: Extract Audio Window using FFmpeg
            ffmpeg_cmd = [
                "ffmpeg", "-y", "-ss", str(start_time), "-t", str(window_duration),
                "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                str(tmp_wav)
            ]
            # Timeout for FFmpeg extraction to prevent hanging
            subprocess.run(ffmpeg_cmd, capture_output=True, check=True, timeout=15)
            
            if not tmp_wav.exists() or tmp_wav.stat().st_size == 0:
                logger.info("Video %s has no valid audio stream for DRM.", os.path.basename(video_path))
                return {}
                
            # Step 2: Run fpcalc to get chromaprint JSON
            fpcalc_cmd = ["fpcalc", "-json", str(tmp_wav)]
            result = subprocess.run(fpcalc_cmd, capture_output=True, text=True, check=True, timeout=10)
            
            output_data = json.loads(result.stdout)
            
            if "fingerprint" in output_data:
                return {
                    "fingerprint": output_data["fingerprint"],
                    "duration": output_data.get("duration", 0),
                    "sample_rate": 44100,
                    "channels": 2,
                    "fpcalc_version": "unknown" # Could be parsed from fpcalc -v if needed
                }
                
        except subprocess.TimeoutExpired as e:
            logger.error("Audio fingerprinting timed out for %s: %s", video_path, e)
        except subprocess.CalledProcessError as e:
            # Check if this is a fatal lack of stream vs transient
            stderr_str = e.stderr.decode('utf-8') if isinstance(e.stderr, bytes) else str(e.stderr)
            if "does not contain any stream" in stderr_str:
                logger.info("Video %s has no audio stream.", os.path.basename(video_path))
            else:
                logger.error("Failed to extract audio fingerprint for %s", video_path)
        except Exception as e:
            logger.error("Unexpected error in audio fingerprinting for %s: %s", video_path, e)
        finally:
            if tmp_wav.exists():
                tmp_wav.unlink()
                
        return {}

    @classmethod
    def save_evidence(cls, job_id: int, account_name: str, video_path: str, phash_data: dict, audio_data: dict = None):
        """
        Saves the perceptual hashes and audio fingerprint to a JSON file as Digital Evidence.
        Uses enhanced schema with video_asset_id and structured metadata.
        """
        if not phash_data and not audio_data:
            return

        evidence_entry = {
            "video_asset_id": f"job_{job_id}",
            "account": account_name,
            "source_path": video_path,
            "filename": os.path.basename(video_path),
            "created_at": int(time.time()),
            "phash_signatures": phash_data or {},
            "audio": audio_data or {}
        }

        # Ensure directory exists
        EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)

        existing_data = []
        if EVIDENCE_FILE.exists():
            try:
                with open(EVIDENCE_FILE, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
            except Exception:
                existing_data = []

        existing_data.append(evidence_entry)

        try:
            # Atomic write
            with open(str(EVIDENCE_FILE) + ".tmp", "w", encoding="utf-8") as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            os.rename(str(EVIDENCE_FILE) + ".tmp", str(EVIDENCE_FILE))
            logger.info("Saved DRM Evidence (L2/L4) for Job #%s (%s frames, %s audio)", 
                        job_id, len(phash_data) if phash_data else 0, "found" if audio_data else "none")
        except Exception as e:
            logger.error("Failed to save DRM evidence: %s", e)
