"""Buffer GraphQL client — https://api.buffer.com

Personal API key: Settings → API. Header `Authorization: Bearer`.
Media is a public HTTPS URL. Buffer has no upload endpoint.
Docs: https://developers.buffer.com/guides/getting-started.html

Rate-limit guard (vá cháy quota):
- Giãn tối thiểu giữa 2 request cùng key (tránh burst TikTok 7 bài/phút).
- Sau HTTP 429: chặn gọi tiếp đến hết cooldown (không spam Retry-After).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_URL = "https://api.buffer.com"
MODES = frozenset({"addToQueue", "shareNow", "shareNext", "customScheduled"})
_IMAGE_EXT = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
_VIDEO_EXT = frozenset({".mp4", ".mov", ".webm"})

# Khoảng cách tối thiểu giữa 2 GraphQL call cùng API key (giây)
MIN_REQUEST_INTERVAL_SEC = 5.0
# Cooldown sàn khi 429 (Buffer free hay reset chậm)
MIN_429_COOLDOWN_SEC = 900  # 15 phút
# Trần cooldown local — tránh khóa key nhiều ngày vì header lệch
MAX_429_COOLDOWN_SEC = 7200  # 2 giờ
# Phần bucket còn lại giữ cho createPost/editPost. Hỏi kênh, hỏi suất, hỏi status phải dừng trước.
POST_RESERVE_RATIO = 0.70

_GUARD_LOCK = threading.Lock()
_KEY_GUARD: dict[str, dict] = {}


def _guard_row(key: str) -> dict:
    row = _KEY_GUARD.get(key)
    if row is None:
        row = {
            "cooldown_until": 0.0,
            "last_call_at": 0.0,
            "limit": None,
            "remaining": None,
        }
        _KEY_GUARD[key] = row
    return row


def any_key_ready(keys: list[str]) -> bool:
    """False khi mọi key đã biết đều đang cooldown. Key chưa gặp thì coi là sẵn sàng."""
    if not keys:
        return False
    now = time.time()
    with _GUARD_LOCK:
        return any(float(_guard_row(k)["cooldown_until"]) <= now for k in keys)


class BufferError(Exception):
    """Lỗi Buffer. Không chứa API key."""

    def __init__(self, message: str, *, status_code: int | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _gql_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def asset_kind(url: str) -> str:
    """image | video. Đuôi không rõ thì coi là video (reup của tool)."""
    path = (url or "").split("?", 1)[0].split("#", 1)[0].lower()
    ext = ""
    if "." in path.rsplit("/", 1)[-1]:
        ext = "." + path.rsplit(".", 1)[-1]
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _VIDEO_EXT or not ext:
        return "video"
    return "video"


class BufferClient:
    def __init__(self, api_key: str, *, endpoint: str = API_URL, timeout: float = 30):
        key = (api_key or "").strip()
        if not key:
            raise BufferError("Thieu BUFFER_API_KEY.")
        self._key = key
        self._endpoint = endpoint
        self._timeout = timeout
        self._lock = threading.Lock()
        with _GUARD_LOCK:
            row = _guard_row(self._key)
            self._last_call_at = float(row["last_call_at"])
            self._cooldown_until = float(row["cooldown_until"])

    def cooldown_remaining(self) -> float:
        """Số giây còn lại trước khi được gọi API lại (0 = sẵn sàng)."""
        with _GUARD_LOCK:
            until = float(_guard_row(self._key)["cooldown_until"])
        self._cooldown_until = until
        return max(0.0, until - time.time())

    def reserve_block_reason(self) -> str | None:
        """Hỏi status/kênh/suất phải dừng khi phần còn lại đã chạm mức giữ cho đăng bài."""
        with _GUARD_LOCK:
            row = _guard_row(self._key)
            limit = row["limit"]
            remaining = row["remaining"]
        if limit is None or remaining is None or int(limit) <= 0:
            return None
        floor = int(int(limit) * POST_RESERVE_RATIO)
        if int(remaining) <= floor:
            return (
                f"Giữ {int(POST_RESERVE_RATIO * 100)}% suất API cho đăng bài "
                f"(còn {remaining}/{limit}, ngưỡng giữ {floor})."
            )
        return None

    def allows(self, purpose: str = "background") -> bool:
        if self.cooldown_remaining() > 0:
            return False
        if purpose != "publish" and self.reserve_block_reason():
            return False
        return True

    def mark_rate_limited(self, retry_after: int | None = None) -> int:
        """Ghi nhận 429 / tự khóa key. Trả về số giây cooldown đã áp. Khóa dùng chung mọi client cùng key."""
        raw = int(retry_after or 0)
        if raw < 1:
            raw = MIN_429_COOLDOWN_SEC
        cd = max(MIN_429_COOLDOWN_SEC, raw)
        cd = min(cd, MAX_429_COOLDOWN_SEC)
        until = time.time() + cd
        with _GUARD_LOCK:
            row = _guard_row(self._key)
            row["cooldown_until"] = max(float(row["cooldown_until"]), until)
            row["remaining"] = 0
            self._cooldown_until = float(row["cooldown_until"])
        logger.warning(
            "[Buffer] Key vào cooldown %ss (retry_after=%s, floor=%ss, cap=%ss)",
            cd,
            retry_after,
            MIN_429_COOLDOWN_SEC,
            MAX_429_COOLDOWN_SEC,
        )
        return cd

    def _note_budget(self, response, *, consumed: bool) -> None:
        def _header_int(headers, name: str):
            value = headers.get(name) if hasattr(headers, "get") else None
            if isinstance(value, bool) or not isinstance(value, (int, str)):
                return None
            try:
                return int(value)
            except (TypeError, ValueError):
                return None

        headers = getattr(response, "headers", None) or {}
        limit = _header_int(headers, "x-ratelimit-limit")
        remaining = _header_int(headers, "x-ratelimit-remaining")
        with _GUARD_LOCK:
            row = _guard_row(self._key)
            if limit is not None:
                row["limit"] = limit
            if remaining is not None:
                row["remaining"] = remaining
            elif consumed and row["remaining"] is not None:
                row["remaining"] = max(0, int(row["remaining"]) - 1)

    def _wait_for_slot(self) -> None:
        """Chặn gọi khi đang cooldown; giãn tối thiểu giữa 2 request cùng key."""
        with _GUARD_LOCK:
            row = _guard_row(self._key)
            now = time.time()
            remaining_cd = float(row["cooldown_until"]) - now
            if remaining_cd > 0:
                self._cooldown_until = float(row["cooldown_until"])
                wait_s = int(remaining_cd) + 1
                raise BufferError(
                    f"Buffer HTTP 429. Vui lòng thử lại sau {wait_s}s.",
                    status_code=429,
                    retry_after=wait_s,
                )
            gap = MIN_REQUEST_INTERVAL_SEC - (now - float(row["last_call_at"] or 0))
            # Giữ chỗ trước khi ngủ để client khác cùng key không chui vào.
            row["last_call_at"] = now + max(gap, 0)
            self._last_call_at = row["last_call_at"]
        if gap > 0:
            time.sleep(gap)

    def execute(
        self,
        query: str,
        variables: dict | None = None,
        *,
        partial: bool = False,
        purpose: str = "background",
    ) -> dict[str, Any]:
        if purpose != "publish":
            held = self.reserve_block_reason()
            if held:
                raise BufferError(held)
        self._wait_for_slot()

        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables
        try:
            response = requests.post(
                self._endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._key}",
                },
                json=payload,
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise BufferError(f"Khong goi duoc Buffer: {exc.__class__.__name__}") from exc

        self._note_budget(response, consumed=True)

        if response.status_code == 401:
            raise BufferError("Buffer tu choi key (401). Lay key o Settings → API.", status_code=401)
        if response.status_code == 429:
            retry_after_header = response.headers.get("Retry-After")
            retry_after = MIN_429_COOLDOWN_SEC
            if retry_after_header:
                try:
                    retry_after = int(retry_after_header)
                except (ValueError, TypeError):
                    pass
            cd = self.mark_rate_limited(retry_after)
            raise BufferError(
                f"Buffer HTTP 429. Vui lòng thử lại sau {cd}s.",
                status_code=429,
                retry_after=cd,
            )
        if response.status_code >= 400:
            raise BufferError(
                f"Buffer HTTP {response.status_code}.",
                status_code=response.status_code,
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise BufferError("Buffer tra ve khong phai JSON.") from exc

        errors = body.get("errors") or []
        data = body.get("data")
        if errors and not (partial and isinstance(data, dict)):
            message = "; ".join(
                str(item.get("message") or "GraphQL error") for item in errors if isinstance(item, dict)
            )
            raise BufferError((message or "GraphQL error")[:300])
        if not isinstance(data, dict):
            raise BufferError("Buffer khong tra data.")
        return data

    def organizations(self) -> list[dict]:
        data = self.execute(
            """
            query GetOrganizations {
              account {
                organizations { id }
              }
            }
            """
        )
        account = data.get("account") or {}
        orgs = account.get("organizations") or []
        return [item for item in orgs if isinstance(item, dict)]

    def channels(self, organization_id: str) -> list[dict]:
        org = _gql_string(organization_id)
        data = self.execute(
            f"""
            query GetChannels {{
              channels(input: {{ organizationId: {org} }}) {{
                id
                name
                displayName
                service
                isQueuePaused
              }}
            }}
            """
        )
        rows = data.get("channels") or []
        return [item for item in rows if isinstance(item, dict)]

    @staticmethod
    def infer_channel_service(channel_id: str) -> str:
        cid = str(channel_id or "").strip()
        if not cid:
            return "facebook"
        try:
            from app.core import settings as runtime_settings

            channels = runtime_settings.get_json("BUFFER_CHANNELS") or []
            for item in channels:
                if isinstance(item, dict) and str(item.get("id") or "").strip() == cid:
                    svc = str(item.get("service") or "").strip().lower()
                    if svc:
                        return svc
                    name = str(item.get("name") or "").lower()
                    if "tiktok" in name:
                        return "tiktok"
                    if "instagram" in name:
                        return "instagram"
                    if "threads" in name:
                        return "threads"
        except Exception:
            pass
        cid_lower = cid.lower()
        if "tiktok" in cid_lower:
            return "tiktok"
        if "instagram" in cid_lower or "ig_" in cid_lower:
            return "instagram"
        if "threads" in cid_lower:
            return "threads"
        return "facebook"

    def create_post(
        self,
        *,
        text: str,
        channel_id: str,
        mode: str = "addToQueue",
        media_url: str | None = None,
        due_at: str | None = None,
        service: str | None = None,
        first_comment: str | None = None,
        fb_type: str = "post",
    ) -> dict:
        if mode not in MODES:
            raise BufferError(f"Mode Buffer khong hop le: {mode}")
        if mode == "customScheduled" and not due_at:
            raise BufferError("customScheduled can dueAt.")

        fields = [
            f"text: {_gql_string(text)}",
            f"channelId: {_gql_string(channel_id)}",
            "schedulingType: automatic",
            f"mode: {mode}",
        ]
        if due_at:
            fields.append(f"dueAt: {_gql_string(due_at)}")
        if media_url:
            kind = asset_kind(media_url)
            url = _gql_string(media_url)
            fields.append(f"assets: [{{ {kind}: {{ url: {url} }} }}]")
        # Facebook bắt buộc type. Reel trên API Buffer vẫn khóa 1 phút 30 giây,
        # trong khi Facebook đã cho video dài hơn. Gửi type post thì video dài được nhận;
        # video dọc Facebook vẫn có thể hiện thành Reel lúc đăng.
        # TikTok và các nền tảng khác không dùng metadata facebook.
        # Instagram dùng metadata.instagram { firstComment }.
        # TikTok strictly omits metadata / firstComment to prevent 422 error.
        svc = (service or "").strip().lower() or self.infer_channel_service(channel_id)
        clean_fc = (first_comment or "").strip()

        if svc == "tiktok":
            # Strictly omit metadata / firstComment for TikTok to prevent GraphQL 422 error
            pass
        elif svc == "instagram":
            if clean_fc:
                fields.append(f"metadata: {{ instagram: {{ firstComment: {_gql_string(clean_fc)} }} }}")
        else:  # facebook or default
            fb_type_val = fb_type or "post"
            fb_meta = [f"type: {fb_type_val}"]
            if clean_fc:
                fb_meta.append(f"firstComment: {_gql_string(clean_fc)}")
            fields.append(f"metadata: {{ facebook: {{ {', '.join(fb_meta)} }} }}")

        data = self.execute(
            f"""
            mutation CreatePost {{
              createPost(input: {{ {", ".join(fields)} }}) {{
                ... on PostActionSuccess {{
                  post {{ id text dueAt }}
                }}
                ... on MutationError {{
                  message
                }}
              }}
            }}
            """,
            purpose="publish",
        )
        node = data.get("createPost") or {}
        post = node.get("post") if isinstance(node, dict) else None
        if isinstance(post, dict) and post.get("id"):
            return post
        message = ""
        if isinstance(node, dict):
            message = str(node.get("message") or "")
        raise BufferError((message or "Buffer khong tao duoc post.")[:300])

    def get_post(self, post_id: str) -> dict | None:
        pid = _gql_string(post_id)
        data = self.execute(
            f"""
            query GetPost {{
              post(input: {{ id: {pid} }}) {{
                id
                text
                channelId
              }}
            }}
            """
        )
        post = data.get("post")
        if isinstance(post, dict) and post.get("id"):
            return post
        return None

    def _take_action(self, query: str, name: str, *, purpose: str = "background") -> dict:
        data = self.execute(query, purpose=purpose)
        node = data.get(name) or {}
        if not isinstance(node, dict):
            raise BufferError("Buffer khong tra ket qua.")
        post = node.get("post")
        if isinstance(post, dict) and post.get("id"):
            return post
        if name == "deletePost" and node.get("id"):
            return node
        message = str(node.get("message") or "")
        raise BufferError((message or "Buffer tu choi.")[:300])

    def delete_post(self, post_id: str) -> None:
        pid = _gql_string(post_id)
        self._take_action(
            f"""
            mutation DeletePost {{
              deletePost(input: {{ id: {pid} }}) {{
                ... on DeletePostSuccess {{ id }}
                ... on MutationError {{ message }}
              }}
            }}
            """,
            "deletePost",
        )

    def edit_post(
        self,
        post_id: str,
        *,
        mode: str | None = None,
        save_to_draft: bool = False,
        due_at: str | None = None,
    ) -> dict:
        fields = [f"id: {_gql_string(post_id)}"]
        if mode:
            if mode not in MODES:
                raise BufferError(f"Mode Buffer khong hop le: {mode}")
            fields.append(f"mode: {mode}")
        if mode == "customScheduled" and not due_at:
            raise BufferError("customScheduled can dueAt.")
        if due_at:
            fields.append(f"dueAt: {_gql_string(due_at)}")
        if save_to_draft:
            fields.append("saveToDraft: true")
        # Đổi lịch mà không gửi lại chữ, video và type thì Buffer coi bài là rỗng.
        if mode or save_to_draft or due_at:
            fields.extend(self._kept_content_fields(post_id))
        return self._take_action(
            f"""
            mutation EditPost {{
              editPost(input: {{ {", ".join(fields)} }}) {{
                ... on PostActionSuccess {{ post {{ id dueAt status }} }}
                ... on MutationError {{ message }}
              }}
            }}
            """,
            "editPost",
            purpose="publish",
        )

    def publish_now(self, post_id: str) -> dict:
        """Đăng ngay. Nếu Buffer đã có bài gửi cùng video thì không gửi thêm."""
        twin = self.find_sent_twin(post_id)
        if twin:
            self._park_if_open(post_id)
            return twin
        result = self.edit_post(post_id, mode="shareNow")
        twin = self.find_sent_twin(post_id)
        if twin and str(twin.get("id") or "") != str(post_id):
            self._park_if_open(post_id)
            return twin
        return result

    def find_sent_twin(self, post_id: str) -> dict | None:
        snap = self.post_snapshot(post_id)
        channel = str(snap.get("channelId") or "").strip()
        if not channel:
            return None
        source = ""
        assets = snap.get("assets") or []
        if assets and isinstance(assets[0], dict):
            source = str(assets[0].get("source") or "").strip()
        text = " ".join(str(snap.get("text") or "").split())[:80]
        orgs = self.organizations()
        if not orgs or not orgs[0].get("id"):
            return None
        org = _gql_string(str(orgs[0]["id"]))
        cid = _gql_string(channel)
        data = self.execute(
            f"""
            query Twins {{
              posts(first: 15, input: {{
                organizationId: {org}
                filter: {{ channelIds: [{cid}], status: [sent] }}
              }}) {{
                edges {{
                  node {{ id text sentAt externalLink assets {{ source }} }}
                }}
              }}
            }}
            """
        )
        for edge in (data.get("posts") or {}).get("edges") or []:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not isinstance(node, dict) or not node.get("id"):
                continue
            if str(node["id"]) == str(post_id):
                return node
            urls = [
                str(item.get("source") or "").strip()
                for item in (node.get("assets") or [])
                if isinstance(item, dict)
            ]
            if source and source in urls:
                return node
            other = " ".join(str(node.get("text") or "").split())[:80]
            if text and other == text:
                return node
        return None

    def _park_if_open(self, post_id: str) -> None:
        """Xóa bài gốc đang mở. Sửa nội dung bài shareNow khiến Buffer gửi thêm một bản."""
        try:
            snap = self.post_snapshot(post_id)
        except BufferError:
            return
        if str(snap.get("status") or "") == "sent":
            return
        try:
            self.delete_post(post_id)
        except BufferError:
            return

    def move_post(self, post_id: str, position: str) -> dict:
        if position not in {"top", "bottom"}:
            raise BufferError("Vi tri hang cho khong hop le.")
        pid = _gql_string(post_id)
        return self._take_action(
            f"""
            mutation MovePost {{
              movePostInQueue(input: {{ id: {pid}, position: {position} }}) {{
                ... on PostActionSuccess {{ post {{ id dueAt }} }}
                ... on MutationError {{ message }}
              }}
            }}
            """,
            "movePostInQueue",
        )

    def post_snapshot(self, post_id: str) -> dict:
        pid = _gql_string(post_id)
        data = self.execute(
            f"""
            query PostSnap {{
              post(input: {{ id: {pid} }}) {{
                id
                text
                dueAt
                status
                shareMode
                channelId
                assets {{ source }}
                metadata {{
                  ... on FacebookPostMetadata {{ type }}
                }}
              }}
            }}
            """
        )
        post = data.get("post")
        if isinstance(post, dict) and post.get("id"):
            return post
        raise BufferError("Khong thay bai tren Buffer.")

    def post_statuses(self, post_ids: list[str]) -> dict[str, str]:
        """Đọc status nhiều bài trong một request. Tránh gọi từng bài rồi dính 429."""
        unique: list[str] = []
        seen: set[str] = set()
        for raw in post_ids:
            pid = str(raw or "").strip()
            if not pid or pid in seen:
                continue
            seen.add(pid)
            unique.append(pid)
        if not unique:
            return {}
        fields = [
            f"p{index}: post(input: {{ id: {_gql_string(pid)} }}) {{ id status }}"
            for index, pid in enumerate(unique)
        ]
        data = self.execute("query PostStatuses {\n" + "\n".join(fields) + "\n}", partial=True)
        out: dict[str, str] = {}
        for index, pid in enumerate(unique):
            node = data.get(f"p{index}")
            out[pid] = str(node.get("status") or "") if isinstance(node, dict) else ""
        return out

    def post_detail(self, post_id: str) -> dict:
        pid = _gql_string(post_id)
        data = self.execute(
            f"""
            query PostDetail {{
              post(input: {{ id: {pid} }}) {{
                id
                text
                dueAt
                sentAt
                status
                externalLink
                assets {{ source }}
                metrics {{ type value }}
              }}
            }}
            """
        )
        post = data.get("post")
        if isinstance(post, dict) and post.get("id"):
            return post
        raise BufferError("Khong thay bai tren Buffer.")

    def _kept_content_fields(self, post_id: str) -> list[str]:
        snap = self.post_snapshot(post_id)
        text = str(snap.get("text") or "")
        assets = snap.get("assets") or []
        source = ""
        if assets and isinstance(assets[0], dict):
            source = str(assets[0].get("source") or "").strip()
        if not text.strip() and not source:
            raise BufferError("Bai khong co chu hoac video de dang.")
        fields = [f"text: {_gql_string(text)}"]
        if source:
            kind = asset_kind(source)
            fields.append(f"assets: [{{ {kind}: {{ url: {_gql_string(source)} }} }}]")
        meta = snap.get("metadata") if isinstance(snap.get("metadata"), dict) else {}
        fb_type = str(meta.get("type") or "post")
        if fb_type not in {"post", "reel", "story"}:
            fb_type = "post"
        cid = str(snap.get("channelId") or "").strip()
        if self.infer_channel_service(cid) != "tiktok":
            fields.append(f"metadata: {{ facebook: {{ type: {fb_type} }} }}")
        return fields

    def duplicate_post(self, post_id: str) -> dict:
        snap = self.post_snapshot(post_id)
        text = str(snap.get("text") or "").strip()
        channel_id = str(snap.get("channelId") or "").strip()
        media = None
        assets = snap.get("assets") or []
        if assets and isinstance(assets[0], dict):
            media = str(assets[0].get("source") or "").strip() or None
        if not text or not channel_id:
            raise BufferError("Khong du noi dung de nhan ban.")
        return self.create_post(text=text, channel_id=channel_id, media_url=media)

    def schedule_block_reason(self, channel_id: str, when_ts: int) -> str | None:
        """Hết suất thì trả câu tiếng Việt. Không chặn khi không đọc được số tuần hay số ngày."""
        from datetime import datetime, timedelta, timezone

        from app.features.buffer.when import quota_block_reason

        ict = timezone(timedelta(hours=7))
        when = datetime.fromtimestamp(int(when_ts), ict)
        now = datetime.now(ict)
        orgs = self.organizations()
        if not orgs or not orgs[0].get("id"):
            raise BufferError("Khong thay to chuc Buffer.")
        org = _gql_string(str(orgs[0]["id"]))
        data = self.execute(
            f"""
            query Limits {{
              channels(input: {{ organizationId: {org} }}) {{
                id
                postingGoal {{
                  goal
                  scheduledCount
                  sentCount
                }}
              }}
            }}
            """
        )
        week_left = None
        for row in data.get("channels") or []:
            if not isinstance(row, dict) or str(row.get("id") or "") != channel_id:
                continue
            goal = row.get("postingGoal") if isinstance(row.get("postingGoal"), dict) else None
            if goal:
                week_left = (
                    int(goal.get("goal") or 0)
                    - int(goal.get("sentCount") or 0)
                    - int(goal.get("scheduledCount") or 0)
                )
            break
        day_limit = day_sent = day_scheduled = None
        if when.date() == now.date():
            cid = _gql_string(channel_id)
            daily = self.execute(
                f"""
                query Day {{
                  dailyPostingLimits(input: {{ channelIds: [{cid}] }}) {{
                    channelId
                    limit
                    scheduled
                    sent
                  }}
                }}
                """
            )
            for row in daily.get("dailyPostingLimits") or []:
                if isinstance(row, dict) and row.get("channelId") == channel_id:
                    day_limit = row.get("limit")
                    day_sent = row.get("sent")
                    day_scheduled = row.get("scheduled")
                    break
        return quota_block_reason(
            when=when,
            now=now,
            week_left=week_left,
            day_limit=day_limit,
            day_sent=day_sent,
            day_scheduled=day_scheduled,
        )

    def quota_overview(self) -> tuple[str, list[dict]]:
        """Hạn đăng theo page. Trả (đoạn chữ, các bài đang xếp kèm nhãn)."""
        from datetime import datetime, timedelta, timezone

        ict = timezone(timedelta(hours=7))
        now = datetime.now(ict)
        orgs = self.organizations()
        if not orgs or not orgs[0].get("id"):
            raise BufferError("Khong thay to chuc Buffer.")
        org = _gql_string(str(orgs[0]["id"]))
        data = self.execute(
            f"""
            query Limits {{
              channels(input: {{ organizationId: {org} }}) {{
                id
                displayName
                name
                postingGoal {{
                  goal
                  periodStart
                  periodEnd
                  scheduledCount
                  sentCount
                }}
              }}
            }}
            """
        )
        channels = [row for row in (data.get("channels") or []) if isinstance(row, dict) and row.get("id")]
        if not channels:
            raise BufferError("Chua co page Buffer.")
        ids = ", ".join(_gql_string(str(row["id"])) for row in channels)
        daily = self.execute(
            f"""
            query Day {{
              dailyPostingLimits(input: {{ channelIds: [{ids}] }}) {{
                channelId
                limit
                scheduled
                sent
              }}
            }}
            """
        )
        day_by_id = {
            row.get("channelId"): row
            for row in (daily.get("dailyPostingLimits") or [])
            if isinstance(row, dict)
        }
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            month_end = month_start.replace(year=now.year + 1, month=1)
        else:
            month_end = month_start.replace(month=now.month + 1)
        start_iso = _gql_string(month_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        end_iso = _gql_string(month_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        month_by_id: dict[str, int] = {}
        month_note = ""
        try:
            month = self.execute(
                f"""
                query Month {{
                  posts(first: 50, input: {{
                    organizationId: {org}
                    filter: {{ status: [sent], startDate: {start_iso}, endDate: {end_iso} }}
                  }}) {{
                    edges {{ node {{ channelId }} }}
                    pageInfo {{ hasNextPage }}
                  }}
                }}
                """
            )
            payload = month.get("posts") or {}
            for edge in payload.get("edges") or []:
                node = edge.get("node") if isinstance(edge, dict) else None
                cid = str((node or {}).get("channelId") or "")
                if cid:
                    month_by_id[cid] = month_by_id.get(cid, 0) + 1
            if (payload.get("pageInfo") or {}).get("hasNextPage"):
                month_note = " (ít nhất)"
        except BufferError:
            month_note = " (chưa đọc được)"

        scheduled = self.execute(
            f"""
            query Queue {{
              posts(first: 10, input: {{
                organizationId: {org}
                filter: {{ status: [scheduled, error] }}
              }}) {{
                edges {{ node {{ id text dueAt status channelId }} }}
              }}
            }}
            """
        )
        from html import escape

        names = {str(row["id"]): str(row.get("displayName") or row.get("name") or row["id"]) for row in channels}
        lines = ["<b>Hạn đăng</b>", "Tuần là mục tiêu. Hôm nay mới là trần."]
        for row in channels:
            cid = str(row["id"])
            name = escape(names[cid])
            goal = row.get("postingGoal") if isinstance(row.get("postingGoal"), dict) else None
            day = day_by_id.get(cid) or {}
            limit = day.get("limit")
            sent_day = int(day.get("sent") or 0)
            queued_day = int(day.get("scheduled") or 0)
            if limit is None:
                day_bit = "hôm nay không thấy trần"
            else:
                day_bit = f"hôm nay còn {int(limit) - sent_day - queued_day}"
            month_bit = month_by_id.get(cid, 0)
            if goal:
                sent = int(goal.get("sentCount") or 0)
                queued = int(goal.get("scheduledCount") or 0)
                target = int(goal.get("goal") or 0)
                left = target - sent - queued
                week = f"tuần còn {left}/{target}" if left > 0 else f"tuần đủ {target}/{target}"
                if queued:
                    week += f", đã xếp {queued}"
            else:
                week = "tuần chưa đặt mục tiêu"
            lines.append(f"<b>{name}</b>\n{week} · {day_bit} · tháng {month_bit} bài{month_note}")
        posts = []
        for edge in (scheduled.get("posts") or {}).get("edges") or []:
            node = edge.get("node") if isinstance(edge, dict) else None
            if not isinstance(node, dict) or not node.get("id"):
                continue
            from html import escape

            title = escape(str(node.get("text") or "").strip().split("\n", 1)[0][:60] or "(không chữ)")
            when = _ict_when(node.get("dueAt"))
            page = escape(names.get(str(node.get("channelId") or ""), ""))
            failed = str(node.get("status") or "") == "error"
            head = f"<b>Lỗi</b> · {page}" if failed else f"<b>{when}</b> · {page}"
            posts.append({"id": str(node["id"]), "label": f"{head}\n{title}", "retry": failed})
        return "\n".join(lines), posts

    def insights_overview(self) -> str:
        """Chỉ số tháng này. Buffer không trả view riêng cho Facebook."""
        text, _channels = self.insights_menu()
        return text

    def insights_menu(self) -> tuple[str, list[tuple[str, str]]]:
        """Tóm tắt từng kênh và danh sách nút để xem riêng."""
        month, names, rows, truncated = self._month_sent()
        if not rows:
            return f"Tháng {month} chưa có bài đã đăng để lấy chỉ số.", []
        return self._insights_text(month, names, rows, truncated, posts=False)

    def insights_channel(self, channel_id: str) -> str:
        month, names, rows, _truncated = self._month_sent()
        name = names.get(channel_id, "")
        if not name:
            raise BufferError("Khong thay kenh.")
        items = [row for row in rows if str(row.get("channelId") or "") == channel_id]
        from html import escape

        if not items:
            return f"<b>{escape(name)}</b>\nTháng {month} chưa có bài đã đăng."
        groups = group_sent_posts(items)
        copies = sum(int(group["count"]) for group in groups)
        reps = [group["representative"] for group in groups]
        lines = [
            f"<b>{escape(name)}</b> · tháng {month} · {content_count_line(len(groups), copies)}",
            _stat_line(_sum_metrics(reps)),
        ]
        for group in groups:
            block = describe_post(group["representative"])
            if int(group["count"]) > 1:
                block = f"{int(group['count'])} bản lịch sử\n{block}"
            lines.append(block)
        return "\n\n".join(lines)

    def _month_sent(self) -> tuple[int, dict[str, str], list[dict], bool]:
        from datetime import datetime, timedelta, timezone

        ict = timezone(timedelta(hours=7))
        now = datetime.now(ict)
        orgs = self.organizations()
        if not orgs or not orgs[0].get("id"):
            raise BufferError("Khong thay to chuc Buffer.")
        org = _gql_string(str(orgs[0]["id"]))
        data = self.execute(
            f"""
            query Names {{
              channels(input: {{ organizationId: {org} }}) {{
                id
                displayName
                name
              }}
            }}
            """
        )
        names = {
            str(row["id"]): str(row.get("displayName") or row.get("name") or row["id"])
            for row in (data.get("channels") or [])
            if isinstance(row, dict) and row.get("id")
        }
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if now.month == 12:
            month_end = month_start.replace(year=now.year + 1, month=1)
        else:
            month_end = month_start.replace(month=now.month + 1)
        start_iso = _gql_string(month_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        end_iso = _gql_string(month_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        packed = self.execute(
            f"""
            query Insights {{
              posts(first: 50, input: {{
                organizationId: {org}
                filter: {{ status: [sent], startDate: {start_iso}, endDate: {end_iso} }}
              }}) {{
                edges {{
                  node {{
                    id
                    text
                    sentAt
                    status
                    externalLink
                    channelId
                    assets {{ source }}
                    metrics {{ type value }}
                  }}
                }}
                pageInfo {{ hasNextPage }}
              }}
            }}
            """
        )
        payload = packed.get("posts") or {}
        rows = []
        for edge in payload.get("edges") or []:
            node = edge.get("node") if isinstance(edge, dict) else None
            if isinstance(node, dict) and node.get("id"):
                rows.append(node)
        truncated = bool((payload.get("pageInfo") or {}).get("hasNextPage"))
        return now.month, names, rows, truncated

    def _insights_text(
        self,
        month: int,
        names: dict[str, str],
        rows: list[dict],
        truncated: bool,
        *,
        posts: bool = True,
    ) -> tuple[str, list[tuple[str, str]]]:
        by_channel: dict[str, list[dict]] = {}
        for row in rows:
            by_channel.setdefault(str(row.get("channelId") or ""), []).append(row)
        from html import escape

        lines = [f"<b>Tháng {month}</b>", "Chưa có số view. Số dưới là lượt hiện."]
        if truncated:
            lines.append("Đang hiện 50 bài mới nhất.")
        ranked = []
        for cid, items in by_channel.items():
            groups = group_sent_posts(items)
            reps = [group["representative"] for group in groups]
            copies = sum(int(group["count"]) for group in groups)
            name = escape(names.get(cid, cid or "Page"))
            lines.append(
                f"<b>{name}</b> · {content_count_line(len(groups), copies)}\n{_stat_line(_sum_metrics(reps))}"
            )
            ranked.extend(reps)
        ranked.sort(key=lambda row: str(row.get("sentAt") or ""), reverse=True)
        channels = [(cid, names.get(cid, cid or "Page")) for cid in by_channel]
        if posts:
            lines.append("<b>Từng bài</b>")
            for row in ranked:
                page = names.get(str(row.get("channelId") or ""), "")
                lines.append(describe_post(row, page=page))
        return "\n\n".join(lines), channels


def _caption_key(text: str) -> str:
    """Cả đoạn chữ, khoảng trắng và xuống dòng gộp thành một dấu cách."""
    return " ".join(str(text or "").split())


def _sent_day(raw) -> str | None:
    """Ngày giờ Việt Nam. Thiếu hoặc sai thời điểm thì không có ngày để gộp."""
    from datetime import datetime, timedelta, timezone

    text = str(raw or "").strip()
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=7)))
    except ValueError:
        return None
    return dt.strftime("%Y-%m-%d")


def group_sent_posts(rows: list[dict]) -> list[dict]:
    """Gộp bản cùng kênh, cùng chữ, cùng ngày. Không xóa bản."""
    buckets: dict[tuple[str, str, str], list[dict]] = {}
    undated: list[dict] = []
    for row in rows:
        day = _sent_day(row.get("sentAt"))
        if day is None:
            undated.append(row)
            continue
        key = (str(row.get("channelId") or ""), _caption_key(row.get("text")), day)
        buckets.setdefault(key, []).append(row)
    groups = []
    for members in buckets.values():
        members.sort(key=lambda item: str(item.get("sentAt") or ""))
        groups.append({"count": len(members), "representative": members[-1], "copies": members})
    for row in undated:
        groups.append({"count": 1, "representative": row, "copies": [row]})
    groups.sort(key=lambda item: str(item["representative"].get("sentAt") or ""), reverse=True)
    return groups


def content_count_line(content_count: int, copy_count: int) -> str:
    if copy_count > content_count:
        return f"{content_count} nội dung · {copy_count} bản lịch sử"
    return f"{content_count} nội dung"


def describe_post(post: dict, *, page: str = "") -> str:
    """Số của một bài. Ảnh, chữ và video dùng cùng bộ chỉ số."""
    from html import escape

    kind = _media_kind(post)
    title = escape(str(post.get("text") or "").strip().split("\n", 1)[0][:80] or "(không chữ)")
    where = f" · {escape(page)}" if page else ""
    when = _ict_when(post.get("sentAt") or post.get("dueAt"))
    stats = _metric_map(post)
    sent = str(post.get("status") or "") == "sent" or bool(post.get("sentAt"))
    numbers = _stat_line(stats, full=True) if sent or stats else "Chưa có số. Bài chưa lên."
    lines = [f"<b>{escape(kind)}</b>{where} · {when}", title, numbers]
    link = str(post.get("externalLink") or "").strip()
    if link:
        lines.append(escape(link))
    return "\n".join(lines)


def _media_kind(post: dict) -> str:
    assets = post.get("assets") or []
    source = ""
    if assets and isinstance(assets[0], dict):
        source = str(assets[0].get("source") or "").strip()
    if not source:
        return "Chữ"
    if asset_kind(source) == "image":
        return "Ảnh"
    return "Video"


def _metric_map(post: dict) -> dict[str, float]:
    out = {}
    for item in post.get("metrics") or []:
        if isinstance(item, dict) and item.get("type"):
            try:
                out[str(item["type"])] = float(item.get("value") or 0)
            except (TypeError, ValueError):
                continue
    return out


def _sum_metrics(posts: list[dict]) -> dict[str, float]:
    total: dict[str, float] = {}
    for post in posts:
        for key, value in _metric_map(post).items():
            if key == "engagementRate":
                continue
            total[key] = total.get(key, 0) + value
    return total


def _num(value) -> str:
    return f"{int(value or 0):,}"


def _stat_line(total: dict[str, float], *, full: bool = False) -> str:
    parts = [f"{_num(total.get('impressions'))} hiện"]
    for key, label in (("reactions", "cảm xúc"), ("comments", "bình luận"), ("shares", "chia sẻ"), ("clicks", "bấm")):
        value = total.get(key) or 0
        if full or value:
            parts.append(f"{_num(value)} {label}")
    if full or total.get("impressions"):
        parts.append(_rate(total))
    return " · ".join(parts)


def _rate(total: dict[str, float]) -> str:
    shown = total.get("impressions") or 0
    if shown <= 0:
        return "0%"
    engaged = (
        total.get("reactions", 0)
        + total.get("comments", 0)
        + total.get("shares", 0)
        + total.get("clicks", 0)
    )
    return f"{engaged / shown * 100:.2f}%"


def _ict_when(raw) -> str:
    from datetime import datetime, timedelta, timezone

    text = str(raw or "").strip()
    if not text:
        return "chưa có giờ"
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=7)))
    except ValueError:
        return text[:16]
    return dt.strftime("%H:%M %d/%m")


def _ict_span(start, end) -> str:
    left = _ict_when(start)
    right = _ict_when(end)
    return f"{left[-5:]}–{right[-5:]}"
