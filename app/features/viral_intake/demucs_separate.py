"""
Tách giọng nói khỏi nhạc nền bằng Demucs (ADR-060) — chạy như TIẾN TRÌNH RIÊNG.

    python -m app.features.viral_intake.demucs_separate <in.wav> <vocals.wav> <background.wav>

Vì sao tiến trình riêng: torch + model htdemucs chiếm ~1 GB RAM; máy chỉ có 7 GB
và worker sống lâu. Chạy xong tiến trình thoát là trả hết RAM, Demucs có crash
cũng không kéo worker theo. ``dub_layer.separate()`` gọi module này qua subprocess.

Không dùng ``torchaudio.save``/``demucs.separate`` CLI: torchaudio đời mới đổi
backend I/O liên tục. Đọc/ghi WAV bằng ``wave`` + numpy, đầu vào là WAV 44,1 kHz
stereo s16 do ffmpeg bóc sẵn.

Model tải về cache torch hub lần đầu (~80 MB). Mã thoát: 0 = xong, 2 = sai tham
số, 3 = thiếu demucs/torch, 1 = lỗi khác.
"""
from __future__ import annotations

import os
import sys
import wave

import numpy as np

try:  # phụ thuộc nặng, tuỳ chọn — thiếu thì thoát mã 3, lớp thuyết minh bỏ qua
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
except ImportError:  # pragma: no cover - phụ thuộc vào môi trường
    torch = None

MODEL_NAME = "htdemucs"
SAMPLE_RATE = 44100


def _read_wav(path: str) -> np.ndarray:
    """WAV s16 → float32 shape (2, n)."""
    with wave.open(path, "rb") as f:
        if f.getsampwidth() != 2 or f.getframerate() != SAMPLE_RATE:
            raise ValueError(f"cần WAV s16 {SAMPLE_RATE} Hz: {path}")
        channels = f.getnchannels()
        data = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16)
    audio = data.reshape(-1, channels).T.astype(np.float32) / 32768.0
    if channels == 1:
        audio = np.repeat(audio, 2, axis=0)
    return audio[:2]


def _write_wav(path: str, audio: np.ndarray) -> None:
    """float32 (2, n) → WAV s16 stereo."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).T.copy()
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes(pcm.tobytes())


def separate(in_wav: str, vocals_wav: str, background_wav: str) -> None:
    torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
    device = "cuda" if torch.cuda.is_available() else "cpu"

    model = get_model(MODEL_NAME)
    model.eval()
    wav = torch.from_numpy(_read_wav(in_wav))
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        sources = apply_model(
            model, ((wav - mean) / std)[None], device=device,
            split=True, overlap=0.25, progress=False,
        )[0]
    sources = sources * std + mean
    vocals = sources[model.sources.index("vocals")]
    background = sources.sum(0) - vocals
    _write_wav(vocals_wav, vocals.cpu().numpy())
    _write_wav(background_wav, background.cpu().numpy())


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: demucs_separate <in.wav> <vocals.wav> <background.wav>", file=sys.stderr)
        return 2
    if torch is None:
        print("demucs/torch missing", file=sys.stderr)
        return 3
    try:
        separate(*argv)
    except Exception as e:  # noqa: BLE001 - mọi lỗi đều báo qua mã thoát
        print(f"{type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
