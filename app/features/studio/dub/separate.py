"""
Tách giọng nói khỏi nhạc nền bằng Demucs (ADR-060) — chạy như TIẾN TRÌNH RIÊNG.

    python -m app.features.studio.dub.separate <in.wav> <vocals.wav> <background.wav>

Vì sao tiến trình riêng: torch + model htdemucs chiếm ~1 GB RAM; máy chỉ có 7 GB
và worker sống lâu. Chạy xong tiến trình thoát là trả hết RAM, Demucs có crash
cũng không kéo worker theo. ``studio.dub.engine.separate()`` gọi module này qua subprocess. Port từ
``viral_intake.demucs_separate`` (ADR-060); bản cũ xoá ở PLAN-106 P6.

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

try:  # phụ thuộc nặng, tuỳ chọn — thiếu thì thoát mã 3, bước lồng tiếng lùi về nền là tiếng gốc hạ nhỏ
    import torch
    from demucs.apply import apply_model
    from demucs.pretrained import get_model
except ImportError:  # pragma: no cover - phụ thuộc vào môi trường
    torch = None

MODEL_NAME = "htdemucs"
SAMPLE_RATE = 44100


CHUNK_SEC = 60  # PLAN-118: tách theo khúc — RAM cỡ một khúc, không theo độ dài video (8:41 cả bài → hết RAM, exit -9)
OVERLAP_SEC = 1.0  # hai khúc chồng nhau 1 giây, trộn mượt (crossfade) để không nghe thấy chỗ nối


def _to_float(raw: bytes, channels: int) -> np.ndarray:
    """PCM s16 → float32 shape (2, n)."""
    audio = np.frombuffer(raw, dtype=np.int16).reshape(-1, channels).T.astype(np.float32) / 32768.0
    if channels == 1:
        audio = np.repeat(audio, 2, axis=0)
    return audio[:2]


def _to_pcm(audio: np.ndarray) -> bytes:
    """float32 (2, n) → PCM s16 stereo."""
    return (np.clip(audio, -1.0, 1.0) * 32767.0).astype(np.int16).T.copy().tobytes()


def _open_out(path: str) -> wave.Wave_write:
    f = wave.open(path, "wb")
    f.setnchannels(2)
    f.setsampwidth(2)
    f.setframerate(SAMPLE_RATE)
    return f


def _split(model, wav: np.ndarray, device: str) -> tuple[np.ndarray, np.ndarray]:
    """Một khúc (2, n) → (giọng, nền), mỗi cái (2, n)."""
    x = torch.from_numpy(wav)
    ref = x.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    with torch.no_grad():
        sources = apply_model(model, ((x - mean) / std)[None], device=device, split=True, overlap=0.25, progress=False)[0]
    sources = sources * std + mean
    vocals = sources[model.sources.index("vocals")]
    return vocals.cpu().numpy(), (sources.sum(0) - vocals).cpu().numpy()


def separate(in_wav: str, vocals_wav: str, background_wav: str) -> None:
    """
    Đọc → tách → ghi từng khúc ``CHUNK_SEC`` giây. Khúc sau đọc lùi ``OVERLAP_SEC`` để chồng lên đuôi khúc trước; đuôi mỗi khúc
    giữ lại chưa ghi, trộn với đầu khúc sau (fade tuyến tính) rồi mới ghi → file ra dài đúng bằng file vào.
    """
    torch.set_num_threads(max(1, (os.cpu_count() or 2) // 2))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = get_model(MODEL_NAME)
    model.eval()
    size, ov = int(CHUNK_SEC * SAMPLE_RATE), int(OVERLAP_SEC * SAMPLE_RATE)
    with wave.open(in_wav, "rb") as src, _open_out(vocals_wav) as out_v, _open_out(background_wav) as out_b:
        if src.getsampwidth() != 2 or src.getframerate() != SAMPLE_RATE:
            raise ValueError(f"cần WAV s16 {SAMPLE_RATE} Hz: {in_wav}")
        channels, total = src.getnchannels(), src.getnframes()
        tail: tuple[np.ndarray, np.ndarray] | None = None
        for i in range(0, total, size):
            a, b = max(0, i - ov), min(total, i + size)
            src.setpos(a)
            vocals, background = _split(model, _to_float(src.readframes(b - a), channels), device)
            lead = i - a  # phần đầu khúc này trùng đuôi khúc trước
            if tail is not None and lead:
                fade = np.linspace(0.0, 1.0, lead, dtype=np.float32)
                vocals[:, :lead] = tail[0] * (1 - fade) + vocals[:, :lead] * fade
                background[:, :lead] = tail[1] * (1 - fade) + background[:, :lead] * fade
            hold = min(ov, b - i) if b < total else 0  # đuôi giữ lại cho khúc sau (khúc cuối thì ghi hết)
            cut = vocals.shape[1] - hold
            out_v.writeframes(_to_pcm(vocals[:, :cut]))
            out_b.writeframes(_to_pcm(background[:, :cut]))
            tail = (vocals[:, cut:], background[:, cut:]) if hold else None


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
