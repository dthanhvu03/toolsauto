"""Tiến độ xử lý video trên Telegram — mốc bước + heartbeat (không % giả).

Một tin được sửa tại chỗ: Owner thấy bước hiện tại và biết bot còn sống
khi job dài (tải TikTok / ffmpeg / caption).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from app.core.progress_report import STAGE_LABELS, progress_scope

logger = logging.getLogger(__name__)

HEARTBEAT_SEC = 50


def _fmt_elapsed(seconds: float) -> str:
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} giây"
    m, r = divmod(s, 60)
    if m < 60:
        return f"{m} phút {r} giây" if r else f"{m} phút"
    h, m = divmod(m, 60)
    return f"{h} giờ {m} phút"


class TelegramProcessProgress:
    """Gửi 1 tin ⏳ rồi ``editMessageText`` theo mốc / heartbeat."""

    def __init__(self, client, material_id: int):
        self.client = client
        self.material_id = material_id
        self.message_id: Optional[int] = None
        self._stage = "start"
        self._started = time.monotonic()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._hb_thread: Optional[threading.Thread] = None
        self._closed = False

    def start(self) -> None:
        text = self._render(heartbeat=False)
        result = self.client.send_message(text)
        if isinstance(result, dict):
            self.message_id = result.get("message_id")
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop,
            name=f"tg-progress-hb-{self.material_id}",
            daemon=True,
        )
        self._hb_thread.start()

    def on_stage(self, stage: str) -> None:
        if stage not in STAGE_LABELS:
            return
        with self._lock:
            if self._closed:
                return
            self._stage = stage
            self._push(heartbeat=False)

    def fail(self, detail: str = "") -> None:
        with self._lock:
            self._stage = "failed"
            self._closed = True
            self._stop.set()
            tip = (detail or "").strip()
            if len(tip) > 160:
                tip = tip[:157] + "…"
            body = f"⚠️ <b>#{self.material_id}</b> xử lý lỗi"
            if tip:
                body += f"\n{tip}"
            self._edit(body)

    def done(self) -> None:
        with self._lock:
            self._stage = "done"
            self._closed = True
            self._stop.set()
            elapsed = _fmt_elapsed(time.monotonic() - self._started)
            self._edit(
                f"✅ <b>#{self.material_id}</b> xong · mất {elapsed}\n"
                "Video (và caption nếu có) gửi ngay dưới."
            )

    def close_silent(self) -> None:
        """Dừng heartbeat khi không muốn sửa tin (vd. đã gửi video READY)."""
        with self._lock:
            self._closed = True
            self._stop.set()

    def running(self):
        """Context: start + gắn ``report_stage`` → pipeline; thoát thì tắt heartbeat."""
        progress = self

        class _Ctx:
            def __enter__(self_inner):
                progress.start()
                self_inner._scope = progress_scope(progress.on_stage)
                self_inner._scope.__enter__()
                return progress

            def __exit__(self_inner, *exc):
                self_inner._scope.__exit__(*exc)
                progress._stop.set()
                return False

        return _Ctx()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(HEARTBEAT_SEC):
            with self._lock:
                if self._closed or self._stage in ("done", "failed"):
                    return
                self._push(heartbeat=True)

    def _push(self, *, heartbeat: bool) -> None:
        self._edit(self._render(heartbeat=heartbeat))

    def _render(self, *, heartbeat: bool) -> str:
        label = STAGE_LABELS.get(self._stage, self._stage)
        lines = [
            f"⏳ Đang xử lý video <b>#{self.material_id}</b>",
            f"· {label}",
        ]
        if heartbeat or (time.monotonic() - self._started) >= HEARTBEAT_SEC:
            lines.append(f"⏱ vẫn chạy · đã {_fmt_elapsed(time.monotonic() - self._started)}")
        return "\n".join(lines)

    def _edit(self, text: str) -> None:
        if not self.message_id:
            return
        try:
            self.client.edit_message_text(self.message_id, text)
        except Exception:
            logger.debug(
                "[Telegram] edit progress #%s message_id=%s failed",
                self.material_id,
                self.message_id,
                exc_info=True,
            )

