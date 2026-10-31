"""
Server đọc chữ VieNeu-TTS cho bước ``dub`` (PLAN-111) — chạy bằng python của venv VieNeu, **không import ``app``**.

Model nạp một lần rồi giữ trên GPU (nạp mất 1–1,5 phút; đọc một câu < 1 giây). Chỉ nghe 127.0.0.1, một luồng
(model không đọc song song). Client: ``app.core.media.tts`` engine ``vieneu``.

- ``GET /health`` → ``{"ok": true, "voices": [...]}``
- ``POST /tts`` ``{"text": "...", "voice": "Ngọc Huyền"}`` → ``audio/wav``

Chạy: ``/home/vu/venv-vieneu/bin/python app/features/studio/dub/vieneu_server.py --port 8790`` (PM2 ``VieNeu_TTS``).
"""
from __future__ import annotations

import argparse
import io
import json
import logging
import time
import unicodedata
import wave
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np

logger = logging.getLogger("vieneu_server")

MAX_TEXT_CHARS = 1500
MAX_BODY_BYTES = 64 * 1024


class Engine:
    """Bọc model: đọc một câu ra WAV. Tách riêng để test thay bằng model giả."""

    def __init__(self, tts, voices: list[str]):
        self.tts = tts
        self.voices = voices

    def wav(self, text: str, voice: str) -> bytes:
        return to_wav(self.tts.infer(text, voice=voice), self.tts.sample_rate)


def to_wav(audio, sample_rate: int) -> bytes:
    """float [-1, 1] (mono hoặc [mẫu, kênh]) → WAV 16-bit."""
    pcm = (np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0) * 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1 if pcm.ndim == 1 else pcm.shape[1])
        w.setsampwidth(2)
        w.setframerate(int(sample_rate))
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def handle_tts(engine: Engine, body: bytes) -> tuple[int, str, bytes]:
    """(mã HTTP, content-type, nội dung). Lỗi trả JSON ``{"error": ...}``."""

    def err(code: int, msg: str) -> tuple[int, str, bytes]:
        return code, "application/json", json.dumps({"error": msg}, ensure_ascii=False).encode()

    try:
        req = json.loads(body or b"{}")
    except ValueError:
        return err(400, "JSON hỏng")
    text = unicodedata.normalize("NFC", str(req.get("text") or "")).strip()
    voice = unicodedata.normalize("NFC", str(req.get("voice") or "")).strip()
    if not text:
        return err(400, "thiếu text")
    if len(text) > MAX_TEXT_CHARS:
        return err(400, f"text dài quá {MAX_TEXT_CHARS} ký tự")
    if voice not in engine.voices:
        return err(400, f"không có giọng «{voice}»")
    try:
        return 200, "audio/wav", engine.wav(text, voice)
    except Exception as exc:  # noqa: BLE001 - lỗi model trả 500, server vẫn sống
        logger.warning("đọc hỏng (%s): %s", type(exc).__name__, exc)
        return err(500, f"đọc hỏng: {type(exc).__name__}")


def make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, ctype: str, data: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802 - tên do http.server đặt
            if self.path != "/health":
                return self._send(404, "application/json", b'{"error":"not found"}')
            data = json.dumps({"ok": True, "voices": engine.voices}, ensure_ascii=False).encode()
            self._send(200, "application/json", data)

        def do_POST(self):  # noqa: N802
            if self.path != "/tts":
                return self._send(404, "application/json", b'{"error":"not found"}')
            size = int(self.headers.get("Content-Length") or 0)
            if size > MAX_BODY_BYTES:
                return self._send(413, "application/json", b'{"error":"body too large"}')
            t = time.time()
            code, ctype, data = handle_tts(engine, self.rfile.read(size))
            logger.info("POST /tts %s %.1fs", code, time.time() - t)
            self._send(code, ctype, data)

        def log_message(self, *_args):  # tắt log mặc định — đã log ở trên
            pass

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8790)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")

    from vieneu import Vieneu  # chỉ có trong venv VieNeu — import ở đầu file thì venv dự án (test) không nạp được

    t = time.time()
    tts = Vieneu(device=args.device)
    voices = [vid for _label, vid in tts.list_preset_voices()]
    engine = Engine(tts, voices)
    engine.wav("Xin chào.", voices[0])  # làm ấm — câu đầu tiên chậm gấp mấy lần
    logger.info("nạp xong %.0fs trên %s, %d giọng, nghe 127.0.0.1:%d", time.time() - t, args.device, len(voices), args.port)
    HTTPServer(("127.0.0.1", args.port), make_handler(engine)).serve_forever()


if __name__ == "__main__":
    main()
