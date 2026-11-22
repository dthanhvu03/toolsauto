"""Small per-call HTTP transport for quote/link deadlines; no redirect following.

An active socket is shut down at the monotonic deadline, including trickled
headers/body. DNS resolution remains an OS blocking operation; no abandoned
background request thread is created to hide that limitation.
"""

from __future__ import annotations

import http.client
import math
import socket
import threading
import time
from urllib.parse import urlsplit


class DeadlineHttpError(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def remaining(deadline: float) -> float:
    left = deadline - time.monotonic()
    if not math.isfinite(left) or left <= 0:
        raise DeadlineHttpError("timeout")
    return left


def request_bytes(
    method: str, url: str, *, deadline: float, headers: dict[str, str] | None = None,
    body: bytes | None = None, max_bytes: int = 1024 * 1024,
) -> tuple[int, bytes]:
    """One HTTP(S) request with default TLS verification and bounded response."""
    try:
        parsed = urlsplit(url)
    except (TypeError, ValueError):
        raise DeadlineHttpError("invalid_url") from None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise DeadlineHttpError("invalid_url")
    try:
        port = parsed.port
    except ValueError:
        raise DeadlineHttpError("invalid_url") from None
    cls = http.client.HTTPSConnection if parsed.scheme == "https" else http.client.HTTPConnection
    conn = cls(parsed.hostname, port, timeout=remaining(deadline))
    expired = threading.Event()
    active_socket = None

    def abort() -> None:
        expired.set()
        sock = active_socket or conn.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    timer = threading.Timer(remaining(deadline), abort)
    timer.daemon = True
    timer.start()
    response = None
    try:
        conn.connect()
        active_socket = conn.sock
        active_socket.settimeout(remaining(deadline))
        request_headers = {"Accept-Encoding": "identity", **(headers or {})}
        target = parsed.path or "/"
        if parsed.query:
            target += "?" + parsed.query
        conn.request(method, target, body=body, headers=request_headers)
        active_socket.settimeout(remaining(deadline))
        response = conn.getresponse()
        remaining(deadline)
        if response.status != 200:
            return response.status, b""
        size = response.getheader("Content-Length")
        if size is not None and (not size.isdigit() or int(size) > max_bytes):
            raise DeadlineHttpError("response_too_large")
        if response.getheader("Content-Encoding", "identity").lower() != "identity":
            raise DeadlineHttpError("unsupported_encoding")
        data = response.read(max_bytes + 1)
        remaining(deadline)
        if len(data) > max_bytes:
            raise DeadlineHttpError("response_too_large")
        return response.status, data
    except DeadlineHttpError:
        raise
    except Exception:
        code = "timeout" if expired.is_set() or time.monotonic() >= deadline else "transport"
        raise DeadlineHttpError(code) from None
    finally:
        timer.cancel()
        if response is not None:
            response.close()
        conn.close()
