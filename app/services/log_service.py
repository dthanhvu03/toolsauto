"""
PM2 log file discovery, tail, merge, and stream helpers for the dashboard.
"""
from __future__ import annotations

import asyncio
import datetime
import os
import re
from pathlib import Path
from typing import ClassVar

from fastapi.responses import PlainTextResponse, StreamingResponse

import app.config as config

_TS_PREFIX_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})"
)


class LogService:
    """Read and tail whitelisted PM2 log files under candidate directories."""

    PM2_LOG_MAP: ClassVar[dict[str, dict[str, str]]] = {
        "AI_Generator": {"out": "AI-Generator-1-out.log", "error": "AI-Generator-1-error.log"},
        "FB_Publisher": {"out": "FB-Publisher-1-out.log", "error": "FB-Publisher-1-error.log"},
        "Maintenance": {"out": "Maintenance-out.log", "error": "Maintenance-error.log"},
        "Web_Dashboard": {"out": "Web-Dashboard-out.log", "error": "Web-Dashboard-error.log"},
    }

    @staticmethod
    def get_log_path(fname: str) -> Path:
        for log_dir in config.iter_pm2_log_directories():
            p = Path(log_dir) / fname
            try:
                if p.is_file():
                    return p
            except OSError:
                continue
        for log_dir in config.iter_pm2_log_directories():
            return Path(log_dir) / fname
        return Path.home() / ".pm2" / "logs" / fname

    @staticmethod
    def tail_file(path: str, lines: int = 200) -> str:
        """Efficient tail: read last N lines without loading entire file."""
        lines = max(50, min(2000, int(lines or 200)))
        p = Path(path)
        if not p.exists() or not p.is_file():
            return f"[missing] {path}\n"

        chunk_size = 8192
        data = b""
        try:
            with p.open("rb") as f:
                f.seek(0, os.SEEK_END)
                pos = f.tell()
                while pos > 0 and data.count(b"\n") <= lines + 2:
                    read_size = chunk_size if pos >= chunk_size else pos
                    pos -= read_size
                    f.seek(pos)
                    data = f.read(read_size) + data
                    if pos == 0:
                        break
        except Exception as e:
            return f"[error reading log] {e}\n"

        text = data.decode("utf-8", errors="replace")
        parts = text.splitlines()
        return "\n".join(parts[-lines:]) + ("\n" if not text.endswith("\n") else "")

    @staticmethod
    def parse_log_ts(line: str) -> float | None:
        m = _TS_PREFIX_RE.match(line or "")
        if not m:
            return None
        s = m.group("ts")
        try:
            dt = datetime.datetime.fromisoformat(s.replace(" ", "T"))
            return dt.timestamp()
        except Exception:
            return None

    @staticmethod
    def tail_all(kind: str, lines: int) -> str:
        """Tail across all whitelisted pm2 logs and return merged last N lines."""
        lines = max(50, min(2000, int(lines or 200)))
        kind = (kind or "out").strip()
        if kind not in ("out", "error"):
            kind = "out"

        merged: list[tuple[float | None, int, str]] = []
        for idx, proc in enumerate(LogService.PM2_LOG_MAP.keys()):
            fname = LogService.PM2_LOG_MAP[proc][kind]
            path = str(LogService.get_log_path(fname))
            chunk = LogService.tail_file(path, lines=lines)
            for raw_line in (chunk.splitlines() if chunk else []):
                line = f"[{proc}] {raw_line}"
                merged.append((LogService.parse_log_ts(raw_line), idx, line))

        merged.sort(key=lambda t: (t[0] is None, t[0] or 0.0, t[1]))
        out_lines = [t[2] for t in merged[-lines:]]
        return "\n".join(out_lines) + ("\n" if out_lines else "")

    @staticmethod
    def read_new_lines(path: Path, pos: int) -> tuple[int, list[str]]:
        """Read newly appended lines from `pos` (non-blocking)."""
        try:
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                end = f.tell()
                if pos > end:
                    pos = 0
                if pos == end:
                    return pos, []
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
        except FileNotFoundError:
            return pos, []
        lines = chunk.splitlines() if chunk else []
        return pos, [ln.decode("utf-8", errors="replace") for ln in lines]

    @staticmethod
    def match_filters(line: str, level: str | None, q: str | None) -> bool:
        if not line:
            return True
        if level:
            lvl = level.strip().upper()
            if lvl in ("INFO", "WARN", "WARNING", "ERROR", "DEBUG"):
                if lvl == "WARN":
                    lvl = "WARNING"
                if lvl not in line.upper():
                    return False
        if q:
            qq = q.strip().lower()
            if qq and (qq not in line.lower()):
                return False
        return True

    @staticmethod
    def plain_tail_response(proc: str, kind: str, lines: int) -> PlainTextResponse:
        proc = (proc or "").strip()
        kind = (kind or "").strip()
        if proc == "ALL":
            return PlainTextResponse(LogService.tail_all(kind=kind, lines=lines))
        if proc not in LogService.PM2_LOG_MAP:
            return PlainTextResponse(f"[invalid proc] {proc}\n", status_code=400)
        if kind not in ("out", "error"):
            return PlainTextResponse(f"[invalid kind] {kind}\n", status_code=400)
        fname = LogService.PM2_LOG_MAP[proc][kind]
        path = str(LogService.get_log_path(fname))
        return PlainTextResponse(LogService.tail_file(path, lines=lines))

    @staticmethod
    def sse_log_stream(
        proc: str,
        kind: str,
        level: str = "",
        q: str = "",
    ) -> StreamingResponse:
        """Server-Sent Events stream for realtime logs."""
        proc = (proc or "").strip()
        kind = (kind or "").strip()
        level = (level or "").strip()
        q = (q or "").strip()
        if kind not in ("out", "error"):
            kind = "out"
        if proc != "ALL" and proc not in LogService.PM2_LOG_MAP:
            return PlainTextResponse(f"[invalid proc] {proc}\n", status_code=400)

        async def gen():
            yield ": stream-start\n\n"

            if proc == "ALL":
                states: list[tuple[str, Path, int]] = []
                for p in LogService.PM2_LOG_MAP.keys():
                    fname = LogService.PM2_LOG_MAP[p][kind]
                    path = LogService.get_log_path(fname)
                    try:
                        start_pos = path.stat().st_size
                    except Exception:
                        start_pos = 0
                    states.append((p, path, start_pos))
                while True:
                    sent = 0
                    new_states: list[tuple[str, Path, int]] = []
                    for p, path, pos in states:
                        pos2, lines = LogService.read_new_lines(path, pos)
                        new_states.append((p, path, pos2))
                        for line in lines:
                            out = f"[{p}] {line}"
                            if LogService.match_filters(out, level, q):
                                yield f"data: {out.replace(chr(10), ' ')}\n\n"
                                sent += 1
                    states = new_states
                    if sent == 0:
                        await asyncio.sleep(0.3)
            else:
                fname = LogService.PM2_LOG_MAP[proc][kind]
                path = LogService.get_log_path(fname)
                try:
                    pos = path.stat().st_size
                except Exception:
                    pos = 0
                while True:
                    pos, lines = LogService.read_new_lines(path, pos)
                    sent = 0
                    for line in lines:
                        if LogService.match_filters(line, level, q):
                            yield f"data: {line.replace(chr(10), ' ')}\n\n"
                            sent += 1
                    if sent == 0:
                        await asyncio.sleep(0.3)

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )
