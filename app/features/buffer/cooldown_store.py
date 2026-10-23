"""Giờ được gọi lại của từng key Buffer sau 429, ghi ra file.

Maintenance và Web là hai process; restart thì RAM mất. File này để mọi process,
mọi lần khởi động cùng thấy một mốc. File chỉ có sha256 rút gọn của key, không có key.

Khóa ``first_comment:<key>`` (PLAN-070, ``adapter.py``) dùng chung file: mốc thử lại
bình luận đầu tiên cho key gói Free. Hash khác hẳn key thô nên không lẫn với mốc 429.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: bỏ khóa file, vẫn ghi atomic
    fcntl = None

from app.config import RUNTIME_CONFIG_DIR

logger = logging.getLogger(__name__)

PATH: Path = RUNTIME_CONFIG_DIR / "buffer_cooldown.json"

_LOCK = threading.Lock()
_CACHE: dict = {"path": None, "sig": None, "data": {}}


def key_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _num(value) -> float:
    try:
        out = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return out if math.isfinite(out) else 0.0


def _read() -> dict:
    """Đọc file, cache theo mtime + size. File hỏng thì coi như rỗng."""
    path = PATH
    try:
        st = path.stat()
    except OSError:
        return {}
    sig = (st.st_mtime_ns, st.st_size)
    if _CACHE["path"] == path and _CACHE["sig"] == sig:
        return _CACHE["data"]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("[Buffer] File cooldown đọc lỗi, bỏ qua: %s", exc)
        data = {}
    if not isinstance(data, dict):
        data = {}
    _CACHE.update(path=path, sig=sig, data=data)
    return data


def until(key: str) -> float:
    """Mốc epoch được gọi lại key này. 0 nếu không có."""
    with _LOCK:
        row = _read().get(key_id(key))
    if not isinstance(row, dict):
        return 0.0
    return _num(row.get("until"))


def save(key: str, until_ts: float, retry_after: int | None = None) -> None:
    """Ghi mốc gọi lại, giữ mốc xa hơn nếu file đã có. Ghi lỗi chỉ log, không chặn luồng gọi."""
    path = PATH
    now = time.time()
    kid = key_id(key)
    with _LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path.with_name(path.name + ".lock"), "a", encoding="utf-8") as lock_fh:
                if fcntl is not None:
                    fcntl.flock(lock_fh, fcntl.LOCK_EX)
                _CACHE["sig"] = None
                data = {
                    k: v
                    for k, v in _read().items()
                    if isinstance(v, dict) and _num(v.get("until")) > now
                }
                if _num(until_ts) > _num((data.get(kid) or {}).get("until")):
                    data[kid] = {
                        "until": round(float(until_ts), 3),
                        "retry_after": retry_after,
                        "set_at": round(now, 3),
                    }
                tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                os.replace(tmp, path)
                _CACHE["sig"] = None
        except OSError as exc:
            logger.warning("[Buffer] Không ghi được file cooldown %s: %s", path, exc)
