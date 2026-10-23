"""Quản lý nhiều tài khoản / API key của Buffer.

Hỗ trợ cấu hình nhiều Buffer API keys (vượt giới hạn 3 kênh của gói Free).
Tự động ánh xạ channel_id -> BufferClient tương ứng.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any

import app.features.buffer.client as buffer_client_mod
from app.config import RUNTIME_CONFIG_DIR
from app.features.buffer import cooldown_store
from app.features.buffer.client import BufferError

logger = logging.getLogger(__name__)

CHANNEL_CACHE_TTL_SEC = 300  # 5 phút làm mới bảng kênh trong RAM (từ file, không gọi mạng)
# Kênh của một key hầu như không đổi. Quét lại sau 6 giờ; gặp kênh lạ thì sớm nhất 30 phút.
CHANNEL_SCAN_TTL_SEC = 6 * 60 * 60
CHANNEL_UNKNOWN_RESCAN_SEC = 30 * 60
# Bảng kênh từng key (khóa = sha256 rút gọn, không ghi key). Restart không phải quét lại.
CHANNELS_FILE = RUNTIME_CONFIG_DIR / "buffer_channels.json"


def _read_channels_file() -> dict:
    try:
        data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_channels_file(data: dict) -> None:
    try:
        CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CHANNELS_FILE.with_name(f"{CHANNELS_FILE.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, CHANNELS_FILE)
    except OSError as exc:
        logger.warning("[BufferManager] Không ghi được bảng kênh %s: %s", CHANNELS_FILE, exc)


def _stored_channels(stored: dict, kid: str) -> tuple[list | None, float]:
    """(danh sách kênh đã lưu, tuổi giây). Chưa có thì (None, inf)."""
    entry = stored.get(kid) if kid else None
    if not isinstance(entry, dict) or not isinstance(entry.get("channels"), list):
        return None, float("inf")
    try:
        age = time.time() - float(entry.get("ts") or 0)
    except (TypeError, ValueError):
        age = float("inf")
    return entry["channels"], age


def _client_in_cooldown(client) -> bool:
    """True khi client đang khóa 429. Client giả không có số giây thì coi là mở."""
    fn = getattr(client, "cooldown_remaining", None)
    if not callable(fn):
        return False
    try:
        value = fn()
    except Exception:
        return False
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return float(value) > 0


def mask_key(key: str) -> str:
    """Ẩn phần lớn chuỗi API key khi ghi log."""
    k = (key or "").strip()
    if not k:
        return "<empty>"
    if len(k) <= 8:
        return f"...{k[-4:]}"
    return f"{k[:4]}...{k[-4:]}"


def parse_api_keys(raw: Any) -> list[str]:
    """Phân tích chuỗi/danh sách/dict API keys thành list các key không trùng lặp."""
    if not raw:
        return []
    keys: list[str] = []
    if isinstance(raw, (list, tuple, set)):
        for item in raw:
            if isinstance(item, dict):
                k = item.get("key") or item.get("api_key") or ""
                if str(k).strip():
                    keys.append(str(k).strip())
            elif item and str(item).strip():
                keys.append(str(item).strip())
    elif isinstance(raw, dict):
        for val in raw.values():
            if isinstance(val, dict):
                k = val.get("key") or val.get("api_key") or ""
                if str(k).strip():
                    keys.append(str(k).strip())
            elif val and str(val).strip():
                keys.append(str(val).strip())
    elif isinstance(raw, str):
        text = raw.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                parsed = json.loads(text)
                return parse_api_keys(parsed)
            except Exception:
                pass
        # Tách theo dấu phẩy, chấm phẩy hoặc xuống dòng
        for part in re.split(r"[,;\n\r]+", text):
            clean = part.strip().strip("'\"")
            if clean:
                keys.append(clean)

    # Loại bỏ trùng lặp giữ nguyên thứ tự
    seen: set[str] = set()
    deduped: list[str] = []
    for k in keys:
        if k not in seen:
            seen.add(k)
            deduped.append(k)
    return deduped


def get_configured_api_keys() -> list[str]:
    """Lấy danh sách các Buffer API keys từ runtime settings và environment."""
    keys: list[str] = []

    # 1. Từ runtime settings (nếu có)
    try:
        from app.core import settings as runtime_settings

        raw_keys = runtime_settings.get_json("BUFFER_API_KEYS") or runtime_settings.get_str("BUFFER_API_KEYS")
        if raw_keys:
            keys.extend(parse_api_keys(raw_keys))
    except Exception:
        pass

    # 2. Từ biến môi trường BUFFER_API_KEYS
    env_keys = os.getenv("BUFFER_API_KEYS", "")
    if env_keys:
        keys.extend(parse_api_keys(env_keys))

    # 3. Từ BUFFER_API_KEY đơn lẻ (backward compatibility)
    try:
        import app.config as config

        single = (getattr(config, "BUFFER_API_KEY", None) or os.getenv("BUFFER_API_KEY", "") or "").strip()
    except Exception:
        single = (os.getenv("BUFFER_API_KEY", "") or "").strip()

    if single:
        for k in parse_api_keys(single):
            if k not in keys:
                keys.append(k)

    return keys


class BufferManager:
    """Quản lý tập hợp các BufferClient tương ứng với các API keys."""

    def __init__(
        self,
        keys: list[str] | None = None,
        clients: list[Any] | None = None,
    ):
        self._explicit_keys = keys
        self._explicit_clients = clients
        self._lock = threading.Lock()
        self._channel_to_client: dict[str, Any] = {}
        self._channel_cache_ts: float = 0.0
        self._channel_meta: dict[str, dict] = {}
        self._unknown_rescan_ts: float = 0.0
        # Số thứ tự key chưa có bảng kênh (khóa/lỗi). Còn key như vậy thì kênh lạ không đổ về key chính.
        self._keys_without_table: list[int] = []
        self._skipped_unknown: set[str] = set()

    def get_keys(self) -> list[str]:
        if self._explicit_keys is not None:
            return list(self._explicit_keys)
        return get_configured_api_keys()

    def has_keys(self) -> bool:
        if self._explicit_clients is not None:
            return len(self._explicit_clients) > 0
        return len(self.get_keys()) > 0

    def get_clients(self) -> list[Any]:
        if self._explicit_clients is not None:
            return list(self._explicit_clients)
        keys = self.get_keys()
        return [buffer_client_mod.BufferClient(k) for k in keys]

    def get_primary_client(self) -> Any:
        clients = self.get_clients()
        if not clients:
            raise BufferError("Chưa có khóa Buffer (thiếu BUFFER_API_KEY hoặc BUFFER_API_KEYS).")
        return clients[0]

    def get_client_by_key(self, api_key: str) -> Any:
        clean = (api_key or "").strip()
        for c in self.get_clients():
            if getattr(c, "_key", "") == clean:
                return c
        return buffer_client_mod.BufferClient(clean)

    def refresh_channels_map(self, max_age: float = CHANNEL_SCAN_TTL_SEC) -> dict[str, Any]:
        """Dựng bảng kênh → client. Bảng đã lưu chưa quá max_age thì không gọi Buffer."""
        clients = self.get_clients()
        if not clients:
            return {}

        new_map: dict[str, Any] = {}
        new_meta: dict[str, dict] = {}
        stored = _read_channels_file()
        changed = False
        without_table: list[int] = []

        for idx, client in enumerate(clients, 1):
            key_str = getattr(client, "_key", "")
            masked = mask_key(key_str)
            kid = cooldown_store.key_id(key_str) if isinstance(key_str, str) and key_str else ""
            cached, age = _stored_channels(stored, kid)
            rows = cached
            if cached is None or age >= max_age:
                held = hasattr(client, "allows") and not client.allows("background")
                if held and (cached is not None or _client_in_cooldown(client)):
                    logger.info(
                        "[BufferManager] Bỏ quét kênh tài khoản #%d (%s) — giữ suất API cho đăng bài hoặc đang cooldown%s",
                        idx,
                        masked,
                        ", dùng bảng kênh đã lưu" if cached is not None else "",
                    )
                else:
                    # Chưa có bảng mà chạm mức giữ suất: quét một lần, kẻo kênh của key này đổ nhầm về key chính.
                    scan_kw = {"purpose": "channel_bootstrap"} if held else {}
                    try:
                        rows = []
                        for org in client.organizations(**scan_kw):
                            org_id = org.get("id")
                            if not org_id:
                                continue
                            for ch in client.channels(org_id, **scan_kw):
                                if isinstance(ch, dict):
                                    rows.append({**ch, "organizationId": org_id})
                        if kid:
                            stored[kid] = {"ts": time.time(), "channels": rows}
                            changed = True
                    except Exception as exc:
                        rows = cached
                        logger.warning(
                            "[BufferManager] Không lấy được kênh cho tài khoản #%d (%s): %s",
                            idx,
                            masked,
                            exc,
                        )
            if rows is None:
                without_table.append(idx)
            for ch in rows or []:
                if not isinstance(ch, dict):
                    continue
                cid = str(ch.get("id") or "").strip()
                if not cid:
                    continue
                new_map[cid] = client
                new_meta[cid] = {**ch, "accountIndex": idx, "apiKeyMasked": masked}

        if changed:
            _write_channels_file(stored)

        with self._lock:
            if not new_map and self._channel_to_client:
                self._channel_cache_ts = time.time()
                logger.info("[BufferManager] Giữ bảng kênh cũ — lượt quét này không lấy được kênh.")
                return dict(self._channel_to_client)
            self._channel_to_client = new_map
            self._channel_meta = new_meta
            self._channel_cache_ts = time.time()
            self._keys_without_table = without_table

        return new_map

    def get_channels_map(self, force_refresh: bool = False) -> dict[str, Any]:
        now = time.time()
        stale = (now - self._channel_cache_ts) > CHANNEL_CACHE_TTL_SEC
        never = self._channel_cache_ts == 0.0
        if force_refresh or stale or never:
            return self.refresh_channels_map()
        return dict(self._channel_to_client)

    def get_client_for_channel(self, channel_id: str) -> Any:
        """Tìm BufferClient của channel. Key chính đang cooldown thì không đổ kênh lạ về đó."""
        cid = (channel_id or "").strip()
        if not cid:
            primary = self.get_primary_client()
            if _client_in_cooldown(primary):
                return None
            return primary

        ch_map = self.get_channels_map(force_refresh=False)
        if cid in ch_map:
            return ch_map[cid]

        # Kênh lạ: quét lại key có bảng cũ hơn 30 phút, tối đa một lần mỗi 30 phút.
        # Còn key chưa có bảng (đang khóa) thì kênh lạ gần như chắc của key đó — quét lại key
        # khác chỉ đốt suất (PLAN-072). Key đó mở lại sẽ được quét ở lượt làm mới thường.
        if not self._keys_without_table and (time.time() - self._unknown_rescan_ts) > CHANNEL_UNKNOWN_RESCAN_SEC:
            self._unknown_rescan_ts = time.time()
            ch_map = self.refresh_channels_map(max_age=CHANNEL_UNKNOWN_RESCAN_SEC)
            if cid in ch_map:
                return ch_map[cid]

        if self._keys_without_table:
            # Kênh lạ có thể thuộc key chưa có bảng. Đổ về key chính là tốn suất key chính vô ích.
            if cid not in self._skipped_unknown:
                self._skipped_unknown.add(cid)
                logger.info(
                    "[BufferManager] Channel %s chưa biết thuộc key nào (tài khoản #%s chưa có bảng kênh), bỏ qua.",
                    cid,
                    ",".join(str(i) for i in self._keys_without_table),
                )
            return None

        primary = self.get_primary_client()
        if _client_in_cooldown(primary):
            logger.debug(
                "[BufferManager] Channel %s không gắn được key đang mở, bỏ qua.",
                cid,
            )
            return None
        logger.info(
            "[BufferManager] Channel %s không thấy trong danh sách quét, dùng primary client.",
            cid,
        )
        return primary

    def get_client_for_post(self, post_id: str, db: Any = None) -> Any:
        """Tìm BufferClient quản lý post_id này qua target_page của Job hoặc query trực tiếp."""
        pid = (post_id or "").strip()
        if not pid:
            return self.get_primary_client()

        # 1. Tra qua Database nếu có DB session
        if db is not None:
            try:
                from app.core.database.models import Job

                job = (
                    db.query(Job)
                    .filter(
                        Job.platform == "buffer",
                        Job.external_post_id == pid,
                    )
                    .first()
                )
                if job and job.target_page:
                    return self.get_client_for_channel(job.target_page)
            except Exception as exc:
                logger.debug("[BufferManager] Tra cứu post_id qua DB thất bại: %s", exc)

        # 2. Nếu chỉ có 1 client thì trả về ngay
        clients = self.get_clients()
        if len(clients) == 1:
            return clients[0]

        # 3. Thử tìm trên từng client
        for client in clients:
            try:
                post = client.get_post(pid)
                if post and post.get("id"):
                    return client
            except Exception:
                continue

        return self.get_primary_client()

    def list_all_channels(self, force_refresh: bool = False) -> list[dict]:
        """Liệt kê toàn bộ các kênh thuộc tất cả các tài khoản Buffer."""
        self.get_channels_map(force_refresh=force_refresh)
        return list(self._channel_meta.values())

    def quota_overview(self) -> tuple[str, list[dict]]:
        """Tổng hợp hạn mức đăng và danh sách bài chờ trên TẤT CẢ tài khoản Buffer."""
        clients = self.get_clients()
        if not clients:
            raise BufferError("Chưa có khóa Buffer.")

        all_text_sections: list[str] = []
        all_items: list[dict] = []

        is_multi = len(clients) > 1

        for idx, client in enumerate(clients, 1):
            key_str = getattr(client, "_key", "")
            masked = mask_key(key_str)
            try:
                text, items = client.quota_overview()
                if is_multi:
                    header = f"<b>=== Tài khoản #{idx} ({masked}) ===</b>\n"
                    all_text_sections.append(header + text)
                else:
                    all_text_sections.append(text)
                all_items.extend(items)
            except BufferError as exc:
                if is_multi:
                    all_text_sections.append(
                        f"<b>=== Tài khoản #{idx} ({masked}) ===</b>\n⚠️ Lỗi: {exc}"
                    )
                else:
                    raise

        combined_text = "\n\n".join(all_text_sections)
        return combined_text, all_items

    def insights_menu(self) -> tuple[str, list[tuple[str, str]]]:
        """Tổng hợp danh mục insights của tất cả các tài khoản Buffer."""
        clients = self.get_clients()
        if not clients:
            raise BufferError("Chưa có khóa Buffer.")

        all_texts: list[str] = []
        all_channels: list[tuple[str, str]] = []
        is_multi = len(clients) > 1

        for idx, client in enumerate(clients, 1):
            key_str = getattr(client, "_key", "")
            masked = mask_key(key_str)
            try:
                text, channels = client.insights_menu()
                if is_multi:
                    all_texts.append(f"<b>Tài khoản #{idx} ({masked}):</b>\n{text}")
                else:
                    all_texts.append(text)
                all_channels.extend(channels)
            except Exception as exc:
                if is_multi:
                    all_texts.append(f"<b>Tài khoản #{idx} ({masked}):</b> Lỗi: {exc}")
                else:
                    raise

        return "\n\n".join(all_texts), all_channels

    def post_statuses(self, post_ids: list[str], db: Any = None) -> dict[str, str]:
        """Đọc status của nhiều bài thuộc nhiều tài khoản khác nhau trong batch."""
        if not post_ids:
            return {}

        clients = self.get_clients()
        if not clients:
            return {}
        if len(clients) == 1:
            return clients[0].post_statuses(post_ids)

        # Gom theo key, không theo object: get_clients() tạo client mới mỗi lần → mỗi bài một request.
        groups: dict[Any, tuple[Any, list[str]]] = {}
        for pid in post_ids:
            c = self.get_client_for_post(pid, db=db)
            if c is None:
                continue
            gkey = getattr(c, "_key", None)
            if not isinstance(gkey, str) or not gkey:
                gkey = id(c)
            groups.setdefault(gkey, (c, []))[1].append(pid)

        merged: dict[str, str] = {}
        for client, subset in groups.values():
            try:
                res = client.post_statuses(subset)
                merged.update(res)
            except Exception as exc:
                logger.warning(
                    "[BufferManager] Lỗi đọc post_statuses cho nhóm %d bài: %s",
                    len(subset),
                    exc,
                )

        return merged

    def delete_post(self, post_id: str, db: Any = None) -> None:
        client = self.get_client_for_post(post_id, db=db)
        client.delete_post(post_id)


_global_manager: BufferManager | None = None
_global_manager_lock = threading.Lock()


def get_buffer_manager() -> BufferManager:
    """Trả về singleton BufferManager toàn cục."""
    global _global_manager
    if _global_manager is None:
        with _global_manager_lock:
            if _global_manager is None:
                _global_manager = BufferManager()
    return _global_manager


def reset_buffer_manager() -> None:
    """Xóa cache singleton (dùng khi cập nhật cấu hình hoặc trong unit test)."""
    global _global_manager
    with _global_manager_lock:
        _global_manager = None
